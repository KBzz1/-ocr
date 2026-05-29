# 后端批量导出与重抽取 P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐后端批量 zip 导出 manifest、失败报告、`section_groups` OCR 风险 prompt，并用回归测试固定重抽取元数据契约。

**Architecture:** 批量导出继续复用 `ExportService._build_export_model()` 生成单任务 JSON 模型，但新增预校验汇总和 manifest 构造，所有任务校验通过后才写 zip。重抽取服务保持现有 `ocr_text_only` 候选保存逻辑，只补强审计字段测试。COPD prompt 只修改 `build_section_group_extraction_prompt()` 的提示文本，不改变字段输出契约。

**Tech Stack:** Flask、pytest、JsonStore、zipfile、React API client 已存在但本计划先不改前端。测试命令默认使用 `conda run -n manzufei_ocr python -m pytest ...`。

---

## Spec Review

审查对象：`docs/superpowers/specs/2026-05-29-backend-batch-export-reextract-p2-design.md`

结论：spec 可执行，无需拆分。它覆盖三个后端点：批量导出 manifest/失败报告、`section_groups` prompt OCR 风险提示、重抽取元数据回归。前端内容只是后续接入边界，本计划不实现前端 UI。

执行注意：

- 当前工作区已有未提交的 Excel 导出修复，涉及 `app/backend/services/export_service.py` 和 `app/backend/tests/test_export_service.py`。实施时保留这些改动，只追加本计划所需代码。
- 批量导出失败路径必须先完成所有任务校验，再写 zip。失败时不要覆盖 `exports/batch/batch-review-export.zip`。
- 成功 zip 内 `failed_tasks` 保持空数组；不可导出任务通过错误响应 `details.failed_tasks` 返回。

## File Map

- Modify: `app/backend/services/export_service.py`
  - 新增批量导出预校验、manifest 构造和失败 details 汇总。
- Modify: `app/backend/tests/test_export_service.py`
  - 增加 manifest 内容测试和批量失败 details 测试。
- Modify: `app/backend/tests/test_export_routes.py`
  - 增加路由下载 zip 内 manifest 的断言。
- Modify: `app/backend/services/copd_extraction/prompts.py`
  - 补齐 `build_section_group_extraction_prompt()` 的 OCR 风险提示和矛盾数值约束。
- Modify: `app/backend/tests/test_copd_prompts.py`
  - 增加 section_groups prompt 风险关键词测试。
- Modify: `app/backend/tests/test_reextraction_service.py`
  - 明确 run 审计记录包含前端需要的版本元数据和 `source=ocr_text_only`。
- Docs after implementation: `docs/PRD任务清单.md`
  - 若所有测试通过，把 `BE-MVP-05-07` 标为已完成。

---

### Task 1: 批量 zip manifest 服务测试

**Files:**
- Modify: `app/backend/tests/test_export_service.py`

- [ ] **Step 1: Write failing manifest test**

Append this test after `test_batch_zip_exports_json_files_for_multiple_tasks`:

```python
def test_batch_zip_writes_manifest_with_export_summary(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="done")
    write_review_result(export_service._store, task_id="task_002")

    info = export_service.export_batch_zip(["task_001", "task_002"])

    with zipfile.ZipFile(info["path"]) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert names == [
        "manifest.json",
        "task_001/task_001.review.json",
        "task_002/task_002.review.json",
    ]
    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2
    assert manifest["success_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["failed_tasks"] == []
    assert [item["task_id"] for item in manifest["success_tasks"]] == ["task_001", "task_002"]
    assert manifest["success_tasks"][0]["status"] == "review"
    assert manifest["success_tasks"][0]["json_path"] == "task_001/task_001.review.json"
    assert manifest["success_tasks"][0]["field_count"] == 1
    assert manifest["success_tasks"][0]["schema_version"] == "1.0.0"
    assert manifest["success_tasks"][0]["document_type"] == "general_medical_record"
    assert manifest["generated_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py::test_batch_zip_writes_manifest_with_export_summary -q
```

Expected: FAIL because `manifest.json` is not in the zip.

- [ ] **Step 3: Write failing batch validation details test**

Append this test after `test_batch_zip_rejects_non_exportable_task`:

```python
def test_batch_zip_reports_all_non_exportable_tasks_without_writing_new_zip(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="uploading")
    write_review_result(export_service._store, task_id="task_002")
    write_task(export_service._store, task_id="task_003", status="failed")
    write_review_result(export_service._store, task_id="task_003")

    with pytest.raises(AppError) as exc:
        export_service.export_batch_zip(["task_001", "task_002", "task_003"])

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code
    assert exc.value.details["format"] == "batch_zip"
    assert exc.value.details["task_count"] == 3
    assert exc.value.details["failed_tasks"] == [
        {
            "task_id": "task_002",
            "error_code": "EXPORT_VALIDATION_FAILED",
            "reason": "只有待审核或已完成任务可以导出",
            "status": "uploading",
        },
        {
            "task_id": "task_003",
            "error_code": "EXPORT_VALIDATION_FAILED",
            "reason": "只有待审核或已完成任务可以导出",
            "status": "failed",
        },
    ]
    assert "batch_zip" not in task_service.get_task("task_001")["export_summary"]["formats"]
    assert not (tmp_path / "exports" / "batch" / "batch-review-export.zip").exists()
```

- [ ] **Step 4: Run validation details test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py::test_batch_zip_reports_all_non_exportable_tasks_without_writing_new_zip -q
```

Expected: FAIL because current service raises on the first invalid task and does not include `details.format` or `failed_tasks`.

---

### Task 2: Implement batch manifest and validation summary

**Files:**
- Modify: `app/backend/services/export_service.py`

- [ ] **Step 1: Add batch export helpers**

In `ExportService`, replace `export_batch_zip()` with this implementation and add the helper methods below it:

```python
    def export_batch_zip(self, task_ids: list[str]) -> dict:
        models, failed_tasks = self._build_batch_export_models(task_ids)
        if failed_tasks:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="批量导出存在不可导出任务",
                details={
                    "format": "batch_zip",
                    "task_count": len(task_ids),
                    "failed_tasks": failed_tasks,
                },
            )

        filename = "batch-review-export.zip"
        relative_path = f"batch/{filename}"
        batch_dir = os.path.join(self._export_dir, "batch")
        filepath = os.path.join(batch_dir, filename)

        try:
            os.makedirs(batch_dir, exist_ok=True)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as archive:
                manifest = self._build_batch_manifest(models)
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                for item in models:
                    archive.writestr(
                        item["json_path"],
                        json.dumps(item["model"], ensure_ascii=False, indent=2),
                    )
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="批量导出文件写入失败",
                details={"format": "batch_zip", "reason": str(e)},
            )

        for item in models:
            self._task_service.record_export(item["task_id"], format="batch_zip", relative_path=relative_path)

        return {
            "format": "batch_zip",
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    def _build_batch_export_models(self, task_ids: list[str]) -> tuple[list[dict], list[dict]]:
        models = []
        failed_tasks = []
        for task_id in task_ids:
            try:
                task = self._task_service.get_task(task_id)
                model = self._build_export_model(task_id, task=task)
            except AppError as exc:
                failed_tasks.append({
                    "task_id": task_id,
                    "error_code": exc.code,
                    "reason": exc.message,
                    "status": self._get_task_status_for_error(task_id),
                })
                continue

            models.append({
                "task_id": task_id,
                "status": task["status"],
                "json_path": f"{task_id}/{task_id}.review.json",
                "model": model,
            })
        return models, failed_tasks

    def _get_task_status_for_error(self, task_id: str) -> str | None:
        try:
            task = self._task_service.get_task(task_id)
        except AppError:
            return None
        return task.get("status")

    def _build_batch_manifest(self, models: list[dict]) -> dict:
        success_tasks = []
        for item in models:
            model = item["model"]
            success_tasks.append({
                "task_id": item["task_id"],
                "status": item["status"],
                "json_path": item["json_path"],
                "field_count": len(model.get("fields", [])),
                "schema_version": model.get("schema_version", ""),
                "document_type": model.get("document_type", ""),
            })

        return {
            "format": "batch_zip",
            "generated_at": self._now(),
            "task_count": len(models),
            "success_count": len(success_tasks),
            "failed_count": 0,
            "success_tasks": success_tasks,
            "failed_tasks": [],
        }
```

- [ ] **Step 2: Run service tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q
```

Expected before updating the existing zip-name assertion: FAIL in `test_batch_zip_exports_json_files_for_multiple_tasks` because it still expects only two files.

- [ ] **Step 3: Update existing batch zip file-list assertion**

In `test_batch_zip_exports_json_files_for_multiple_tasks`, replace:

```python
        assert sorted(archive.namelist()) == [
            "task_001/task_001.review.json",
            "task_002/task_002.review.json",
        ]
```

with:

```python
        assert sorted(archive.namelist()) == [
            "manifest.json",
            "task_001/task_001.review.json",
            "task_002/task_002.review.json",
        ]
```

- [ ] **Step 4: Run service tests again**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q
```

Expected: PASS for export service tests.

- [ ] **Step 5: Commit service implementation**

Run:

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "补齐批量导出清单和失败报告"
```

Expected: commit succeeds and includes only export service/test changes from this task plus any pre-existing export-service edits intentionally kept in the same files.

---

### Task 3: Batch zip route manifest regression

**Files:**
- Modify: `app/backend/tests/test_export_routes.py`

- [ ] **Step 1: Extend route test to read manifest**

In `test_batch_zip_route_returns_zip_download`, replace the zip assertion block with:

```python
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "task_001/task_001.review.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2
    assert manifest["success_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["success_tasks"][0]["json_path"] == "task_001/task_001.review.json"
```

- [ ] **Step 2: Add route failure details test**

Append this test after `test_batch_zip_route_rejects_empty_task_ids`:

```python
def test_batch_zip_route_returns_failed_task_report(client, app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    seed_exportable_task_with_id(store, "task_001", status="review")
    seed_exportable_task_with_id(store, "task_002", status="processing")

    response = client.post(
        "/api/tasks/export/batch-zip",
        json={"task_ids": ["task_001", "task_002"]},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]["code"] == "EXPORT_VALIDATION_FAILED"
    assert payload["error"]["details"]["format"] == "batch_zip"
    assert payload["error"]["details"]["failed_tasks"] == [
        {
            "task_id": "task_002",
            "error_code": "EXPORT_VALIDATION_FAILED",
            "reason": "只有待审核或已完成任务可以导出",
            "status": "processing",
        }
    ]
```

- [ ] **Step 3: Run route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_routes.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit route regression**

Run:

```bash
git add app/backend/tests/test_export_routes.py
git commit -m "补充批量导出路由清单测试"
```

Expected: commit succeeds.

---

### Task 4: section_groups prompt OCR risk coverage

**Files:**
- Modify: `app/backend/tests/test_copd_prompts.py`
- Modify: `app/backend/services/copd_extraction/prompts.py`

- [ ] **Step 1: Write failing prompt coverage test**

Append this test after `test_section_group_prompt_asks_for_short_evidence_and_ocr_audit`:

```python
def test_section_group_prompt_contains_full_ocr_risk_warnings():
    from app.backend.services.copd_extraction.prompts import build_section_group_extraction_prompt

    prompt = build_section_group_extraction_prompt("auxiliary_exam", "血气：P02 80mmHg。", ["pao2"])

    assert "1/I/l" in prompt
    assert "0/O/o" in prompt
    assert "BHI/BMI" in prompt
    assert "cT/CT/Ct" in prompt
    assert "P62/P02/PC02/PCO2/PO2/PaO2/PaCO2" in prompt
    assert "噻托溴铵" in prompt
    assert "二羟丙茶碱" in prompt
    assert "+10^9/L" in prompt
    assert "×10^9/L" in prompt
    assert "表格错位" in prompt
    assert "冒号和空格丢失" in prompt
    assert "常见错别字" in prompt
    assert "前后矛盾数值" in prompt
    assert "不得静默选值" in prompt
    assert "不得改写数值" in prompt
```

- [ ] **Step 2: Run prompt test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py::test_section_group_prompt_contains_full_ocr_risk_warnings -q
```

Expected: FAIL because current section group prompt does not mention every listed risk.

- [ ] **Step 3: Update section group prompt text**

In `app/backend/services/copd_extraction/prompts.py`, replace the current `OCR 风险提示` and immediate correction guidance inside `build_section_group_extraction_prompt()` with:

```python
OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、药名和医学词近形/同音/缺字错读（例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱）、单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason；没有纠偏时 applied=false。
如果把 P62、P02、PC02 等疑似错读标签理解为 PO2/PaO2/PCO2/PaCO2，必须保留原始 evidence_phrase，并在 ocr_correction 中记录原始标签和标准标签；没有把握时降低 confidence。
如果把嗜托溴铵理解为噻托溴铵、二程丙苯碱理解为二羟丙茶碱等药名纠偏，必须记录 ocr_correction。
如果同一字段在证据中出现前后矛盾数值，例如脉搏：9次/分但后文心率99次/分，属于前后矛盾数值，不得静默选值，应降低 confidence 并保留原始 evidence_phrase。
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit prompt change**

Run:

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "补齐分组抽取OCR风险提示"
```

Expected: commit succeeds.

---

### Task 5: Reextraction metadata regression

**Files:**
- Modify: `app/backend/tests/test_reextraction_service.py`

- [ ] **Step 1: Strengthen existing reextract version test**

In `test_reextract_uses_saved_document_text_and_records_versions`, replace the last assertion:

```python
    assert store.read(f"results/task_001/reextract_runs/{result['run_id']}.json")["candidate_count"] == 1
```

with:

```python
    run = store.read(f"results/task_001/reextract_runs/{result['run_id']}.json")
    assert run["task_id"] == "task_001"
    assert run["run_id"] == result["run_id"]
    assert run["source"] == "ocr_text_only"
    assert run["schema_version"] == "copd.v1"
    assert run["prompt_version"] == "copd.prompt.v1"
    assert run["candidate_count"] == 1
    assert run["created_at"]
```

- [ ] **Step 2: Run reextraction tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_reextraction_service.py -q
```

Expected: PASS with current implementation.

- [ ] **Step 3: Commit reextract regression if file changed**

Run:

```bash
git add app/backend/tests/test_reextraction_service.py app/backend/services/reextraction_service.py
git commit -m "固定重抽取审计元数据契约"
```

Expected: commit succeeds if there were changes. If `git diff --cached --quiet` shows nothing staged, skip this commit.

---

### Task 6: Documentation status update

**Files:**
- Modify: `docs/PRD任务清单.md`

- [ ] **Step 1: Update BE-MVP-05-07 status**

If Tasks 1-5 pass, change this section in `docs/PRD任务清单.md`:

```markdown
- [ ] **BE-MVP-05-07 批量导出清单与失败报告**
```

to:

```markdown
- [x] **BE-MVP-05-07 批量导出清单与失败报告**
```

Update its range text to:

```markdown
  - 范围：批量 zip 内增加 `manifest.json` 导出摘要，记录任务数、成功任务、失败任务、字段数、schema/document 元数据和生成时间；批量失败响应返回失败任务原因。
  - 边界：不引入独立 `exported` 状态；导出失败不修改审核数据；当前仍保持全成功才生成 zip，不做部分成功下载。
```

- [ ] **Step 2: Add P2 prompt note under BE-MVP-04-04**

Under `BE-MVP-04-04 慢阻肺专病字段抽取`, add:

```markdown
  - P2：默认 `section_groups` prompt 已补齐 OCR 风险提示，覆盖单位符号、表格错位、冒号/空格丢失、药名纠偏和前后矛盾数值。
```

- [ ] **Step 3: Commit docs status**

Run:

```bash
git add docs/PRD任务清单.md
git commit -m "更新批量导出清单进度"
```

Expected: commit succeeds.

---

### Task 7: Final verification

**Files:**
- No edits unless verification finds a failure.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_reextraction_service.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run broader backend smoke**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: all backend tests pass. If this is too slow or blocked by local OCR/GPU dependencies, capture the exact failure and run the targeted command from Step 1 again before reporting.

- [ ] **Step 3: Review git status**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing files remain dirty, or the tree is clean. Do not revert unrelated user changes.

---

## Plan Self-Review

- Spec coverage: manifest success zip is covered by Tasks 1-3; failed batch report and no export recording are covered by Tasks 1-3; section_groups prompt OCR risk coverage is covered by Task 4; reextract audit metadata is covered by Task 5; PRD progress is covered by Task 6.
- Placeholder scan: no placeholder markers or unspecified “add tests” steps remain.
- Type consistency: plan uses existing `ExportService`, `AppError`, `ErrorCode`, `TaskService.record_export()`, `build_section_group_extraction_prompt()`, and `ReextractionService.reextract()` names.
