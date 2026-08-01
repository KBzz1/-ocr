# 批量 Excel 导出（一键全部导出到同一张表）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增按记录模板一键把全部 `review`/`done` 任务导出到同一张 Excel 表（固定可见列 + 隐藏任务编号列）的能力，生成接口与下载接口分离，每次导出生成唯一不可变文件。

**Architecture:** 后端 `ExportService` 新增 `export_batch_excel(document_type)`：按 `int(task_id)` 稳定排序筛选候选任务，字段级规则只写已确认字段，目标模块全无确认字段才跳过任务；每次导出用 uuid export_id 生成唯一文件路径，先写临时文件再 `os.replace` 原子重命名；xlsx 继续用标准库原始 XML 写入（新增最小 styles.xml 支持 wrapText 与隐藏列）。前端任务列表页新增"全部导出 Excel"按钮 + 单选模板弹窗，生成后按 `download_url` 二次下载。

**Tech Stack:** Python 3 / Flask / 标准库 zipfile（无第三方 Excel 依赖）；React + TypeScript + Vitest/MSW 组件测试；pytest 契约测试。

## Global Constraints

- 系统离线运行；xlsx 写入只能使用标准库（zipfile + XML 字符串），不引入 openpyxl 等第三方依赖。
- 复用现有错误码：`INVALID_REQUEST_PARAMS` / `EXPORT_VALIDATION_FAILED` / `EXPORT_FAILED`，不新增错误码。
- 不发明新字段状态：`FieldStatus` 只有 `UNREVIEWED` / `CONFIRMED` / `MODIFIED` 三种（`app/backend/enums.py`）。
- 已确认字段 = `status ∈ {CONFIRMED, MODIFIED}` 且 `final_value` 非空（空白 trim 后非空）。
- 导出内容只来自人工审核后的最终值；不从前端拼 Excel；不写回审核数据。
- 批量导出文件名固定格式 `batch-<export_id>.xlsx`，位于 `exports/batch/`，每次导出新文件，不覆盖旧文件。
- Python 测试命令：`conda run -n manzufei_ocr python -m pytest <path> -q`；前端命令：`npm --prefix app/frontend run <typecheck|test -- --run|build>`。
- Git commit message 使用中文；不提交 `data/`、`exports/`、`logs/` 真实数据。

---

### Task 1: DocumentProfile 增加批量 Excel 启用标记与注册表查询

**Files:**
- Modify: `app/backend/services/document_profiles.py`（DocumentProfile dataclass 加字段；DocumentProfileRegistry 加查询方法）
- Modify: `app/backend/__init__.py:197-205`（active_profile 构造传 `batch_excel_enabled=True`）
- Test: `app/backend/tests/test_document_profiles.py`

**Interfaces:**
- Produces: `DocumentProfile.batch_excel_enabled: bool = False`（frozen dataclass 新字段，默认 False，老构造不受影响）；`DocumentProfileRegistry.get_batch_excel_available_document_types() -> list[dict]` 返回 `[{"document_type": str, "label": str}]`，只含 `is_available` 且 `batch_excel_enabled` 的 profile，按注册顺序。

- [ ] **Step 1: 写失败测试**（`app/backend/tests/test_document_profiles.py` 追加）

```python
from app.backend.services.document_profiles import DocumentProfile, DocumentProfileRegistry


def _profile(document_type, enabled=False, complete=True):
    return DocumentProfile(
        document_type=document_type,
        label=f"模板{document_type}",
        schema={"version": "1.0.0", "field_groups": []},
        prompt_version="prompt.v1",
        field_port=object() if complete else None,
        batch_excel_enabled=enabled,
    )


def test_batch_excel_templates_only_returns_enabled_available_profiles(tmp_path):
    store = JsonStore(str(tmp_path))
    registry = DocumentProfileRegistry(
        store=store,
        profiles=[
            _profile("admission", enabled=True),
            _profile("disabled", enabled=False),
            _profile("incomplete", enabled=True, complete=False),
        ],
        default_document_type="admission",
    )

    templates = registry.get_batch_excel_available_document_types()

    assert templates == [{"document_type": "admission", "label": "模板admission"}]


def test_batch_excel_enabled_defaults_to_false():
    profile = DocumentProfile(
        document_type="admission",
        label="入院记录",
        schema={"version": "1.0.0", "field_groups": []},
        prompt_version="prompt.v1",
        field_port=object(),
    )
    assert profile.batch_excel_enabled is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_document_profiles.py -q`
Expected: FAIL（`TypeError`，`batch_excel_enabled` 不是合法参数 / `get_batch_excel_available_document_types` 不存在）

- [ ] **Step 3: 实现**（`app/backend/services/document_profiles.py`）

dataclass 字段追加到 `quality_rule_profile` 之后：

```python
@dataclass(frozen=True)
class DocumentProfile:
    document_type: str
    label: str
    schema: dict
    prompt_version: str
    field_port: Any
    quality_rule_profile: str | None = None
    batch_excel_enabled: bool = False
```

`DocumentProfileRegistry` 增加方法：

```python
def get_batch_excel_available_document_types(self) -> list[dict]:
    """仅返回显式启用批量 Excel 且已完整接入的模板。"""
    return [
        {"document_type": profile.document_type, "label": profile.label}
        for profile in self._profiles.values()
        if profile.is_available and profile.batch_excel_enabled
    ]
```

`app/backend/__init__.py` active_profile 构造追加参数（在 `quality_rule_profile=...` 行之后）：

```python
        batch_excel_enabled=True,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_document_profiles.py -q`
Expected: PASS（新用例 + 原有用例）

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/document_profiles.py app/backend/__init__.py app/backend/tests/test_document_profiles.py
git commit -m "feat:记录模板新增批量Excel导出显式启用标记"
```

---

### Task 2: ExportService 批量行构建与模板查询（纯逻辑，不写文件）

**Files:**
- Modify: `app/backend/services/export_service.py`
- Test: `app/backend/tests/test_export_service.py`

**Interfaces:**
- Consumes: Task 1 的 `DocumentProfile.batch_excel_enabled`、`get_batch_excel_available_document_types`；`TaskService.list_tasks()`（summary 含 `task_id/status/document_type`，已按字符串排序）、`_build_schema_view(review, schema)`、`_patient_metadata(task)`（均已在 export_service.py 存在）。
- Produces:
  - `_BATCH_MODULE_COLUMNS` 类常量：`[("chief_complaint", "主诉"), ("history_of_present_illness", "新病史"), ("past_history", "既往史"), ("personal_history", "个人史"), ("family_history", "家族史"), ("physical_exam", "体格检查")]`
  - `_candidate_tasks(document_type: str) -> list[dict]`：`status ∈ {review, done}` 且 `document_type` 匹配，按 `_task_sort_key` 稳定升序
  - `_task_sort_key(task) -> tuple`：task_id 数字升序优先，非数字回退字符串升序
  - `_build_batch_excel_rows(candidate_tasks: list[dict], schema: dict) -> tuple[list[dict], list[dict]]`：rows 为 `{"serial": int, "patient_name": str, "cells": {group_key: str}, "task_id": str}`，skipped 为 `[{"task_id": str, "reason": str}]`；serial 只对成功行连续递增
  - `batch_excel_templates() -> list[dict]`：`self._document_profiles is None` 时返回 `[]`，否则委托 registry 方法

- [ ] **Step 1: 写失败测试**（`app/backend/tests/test_export_service.py` 追加 fixture 与用例）

测试 fixture 用 `document_profiles` 参数构造（多分组 schema，覆盖 6 个固定模块 + 一个无关分组）：

```python
from app.backend.services.document_profiles import DocumentProfile

BATCH_SCHEMA = {
    "version": "2.0.0",
    "document_type": "qwen_batch_admission_record",
    "field_groups": [
        {"group_key": "chief_complaint", "group_label": "主诉",
         "fields": [{"field_key": "chief_complaint", "label": "主诉"}]},
        {"group_key": "history_of_present_illness", "group_label": "现病史",
         "fields": [
             {"field_key": "hpi_initial_onset", "label": "初次发病情况"},
             {"field_key": "hpi_stool", "label": "大便情况"},
         ]},
        {"group_key": "past_history", "group_label": "既往史",
         "fields": [{"field_key": "pmh_hypertension", "label": "高血压"}]},
        {"group_key": "personal_history", "group_label": "个人史",
         "fields": [{"field_key": "personal_smoking_history", "label": "吸烟史"}]},
        {"group_key": "family_history", "group_label": "家族史",
         "fields": [{"field_key": "family_history", "label": "家族史"}]},
        {"group_key": "physical_exam", "group_label": "体格检查",
         "fields": [{"field_key": "pe_temperature", "label": "体温"}]},
        {"group_key": "diagnosis", "group_label": "诊断",
         "fields": [{"field_key": "diagnosis_initial", "label": "初步诊断"}]},
    ],
}


def make_batch_export_service(tmp_path):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    profile = DocumentProfile(
        document_type="qwen_batch_admission_record",
        label="入院记录",
        schema=BATCH_SCHEMA,
        prompt_version="prompt.v1",
        field_port=object(),
        batch_excel_enabled=True,
    )
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        document_profiles=DocumentProfileRegistry(
            store=store, profiles=[profile], default_document_type="qwen_batch_admission_record"
        ),
    )
    return export_service, task_service


def write_batch_task(store, task_id, status="review", document_type="qwen_batch_admission_record", patient_name="张三"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "display_name": task_id,
            "status": status,
            "created_at": "2026-07-01T10:00:00+00:00",
            "updated_at": "2026-07-01T10:00:00+00:00",
            "upload_token": "token",
            "images": [],
            "page_count": 1,
            "error_code": None,
            "error_message": None,
            "failed_at": None,
            "review_summary": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "document_type": document_type,
            "document_type_label": "入院记录",
            "schema_version": "2.0.0",
            "prompt_version": "prompt.v1",
            "patient_id": "p1",
            "patient_snapshot": {"patient_id": "p1", "name": patient_name},
            "record_date": "2026-07-01",
            "record_time": None,
            "deleted_at": None,
            "metadata_history": [],
            "status_history": [],
        },
    )


def write_batch_review(store, task_id, fields):
    store.write(
        f"results/{task_id}/review_result.json",
        {"task_id": task_id, "schema_version": "2.0.0",
         "document_type": "qwen_batch_admission_record", "fields": fields},
    )


def confirmed_field(field_key, label, value):
    return {"field_key": field_key, "field_name": label, "final_value": value,
            "status": FieldStatus.CONFIRMED.value}


def unreviewed_field(field_key, label, value):
    return {"field_key": field_key, "field_name": label, "final_value": value,
            "status": FieldStatus.UNREVIEWED.value}
```

用例：

```python
def test_build_batch_excel_rows_field_level_rule(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    write_batch_review(export_service._store, "1", [
        confirmed_field("chief_complaint", "主诉", "反复咳嗽"),
        unreviewed_field("hpi_initial_onset", "初次发病情况", "三个月前"),   # 未确认有值 → 不写入
        confirmed_field("hpi_stool", "大便情况", "正常"),
        confirmed_field("pmh_hypertension", "高血压", "有"),
        confirmed_field("family_history", "家族史", "父亲慢阻肺"),
    ])

    rows, skipped = export_service._build_batch_excel_rows(
        export_service._candidate_tasks("qwen_batch_admission_record"), BATCH_SCHEMA
    )

    assert len(rows) == 1 and skipped == []
    row = rows[0]
    assert row["serial"] == 1
    assert row["patient_name"] == "张三"
    assert row["task_id"] == "1"
    assert row["cells"]["chief_complaint"] == "反复咳嗽"          # 单字段组只写值
    assert row["cells"]["history_of_present_illness"] == "大便情况：正常"   # 未确认字段不出现
    assert row["cells"]["past_history"] == "高血压：有"
    assert row["cells"]["family_history"] == "父亲慢阻肺"
    assert row["cells"]["personal_history"] == ""               # 无确认字段 → 留空
    assert row["cells"]["physical_exam"] == ""


def test_build_batch_excel_rows_skips_when_no_confirmed_field(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    write_batch_review(export_service._store, "1", [
        unreviewed_field("chief_complaint", "主诉", "反复咳嗽"),   # 未确认有值也不写入
    ])

    rows, skipped = export_service._build_batch_excel_rows(
        export_service._candidate_tasks("qwen_batch_admission_record"), BATCH_SCHEMA
    )

    assert rows == []
    assert skipped == [{"task_id": "1", "reason": "目标模块中没有任何已确认字段，未生成导出行"}]


def test_build_batch_excel_rows_skips_corrupted_review(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    export_service._store.write(f"results/1/review_result.json", {"fields": "not-a-list"})

    rows, skipped = export_service._build_batch_excel_rows(
        export_service._candidate_tasks("qwen_batch_admission_record"), BATCH_SCHEMA
    )

    assert rows == []
    assert skipped[0]["task_id"] == "1"
    assert skipped[0]["reason"]


def test_build_batch_excel_rows_missing_review_file(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")

    rows, skipped = export_service._build_batch_excel_rows(
        export_service._candidate_tasks("qwen_batch_admission_record"), BATCH_SCHEMA
    )

    assert rows == []
    assert skipped[0]["task_id"] == "1"


def test_candidate_tasks_filters_status_and_document_type_and_sorts(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "2", status="done")
    write_batch_task(export_service._store, "1", status="review")
    write_batch_task(export_service._store, "3", status="failed")
    write_batch_task(export_service._store, "4", status="review", document_type="other_template")

    candidates = export_service._candidate_tasks("qwen_batch_admission_record")

    assert [t["task_id"] for t in candidates] == ["1", "2"]   # 数字升序、排除 failed 与异模板


def test_batch_excel_templates_returns_enabled_profiles(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    assert export_service.batch_excel_templates() == [
        {"document_type": "qwen_batch_admission_record", "label": "入院记录"}
    ]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q`
Expected: FAIL（`_BATCH_MODULE_COLUMNS` / `_candidate_tasks` / `_build_batch_excel_rows` / `batch_excel_templates` 不存在）

- [ ] **Step 3: 实现**（`app/backend/services/export_service.py`）

模块常量（放在 `_HEADERS` 附近）：

```python
    _BATCH_MODULE_COLUMNS = [
        ("chief_complaint", "主诉"),
        ("history_of_present_illness", "新病史"),
        ("past_history", "既往史"),
        ("personal_history", "个人史"),
        ("family_history", "家族史"),
        ("physical_exam", "体格检查"),
    ]
```

方法（放在 `_build_batch_export_models` 之后）：

```python
    def batch_excel_templates(self) -> list[dict]:
        if self._document_profiles is None:
            return []
        return self._document_profiles.get_batch_excel_available_document_types()

    @staticmethod
    def _task_sort_key(task: dict) -> tuple:
        raw = task.get("task_id")
        try:
            return (0, int(raw))
        except (TypeError, ValueError):
            return (1, str(raw))

    def _candidate_tasks(self, document_type: str) -> list[dict]:
        tasks = self._task_service.list_tasks()
        candidates = [
            task
            for task in tasks
            if task.get("status") in (TaskStatus.REVIEW.value, TaskStatus.DONE.value)
            and task.get("document_type") == document_type
        ]
        candidates.sort(key=self._task_sort_key)
        return candidates

    def _build_batch_excel_rows(self, candidate_tasks: list[dict], schema: dict) -> tuple[list[dict], list[dict]]:
        module_group_keys = [group_key for group_key, _ in self._BATCH_MODULE_COLUMNS]
        schema_group_fields = {
            group.get("group_key"): list(group.get("fields") or [])
            for group in (schema.get("field_groups") or [])
        }
        rows: list[dict] = []
        skipped: list[dict] = []
        serial = 0
        for task in candidate_tasks:
            task_id = task["task_id"]
            try:
                review = self._store.read(f"results/{task_id}/review_result.json")
                if review is None or not isinstance(review.get("fields"), list) or not review["fields"]:
                    raise AppError(
                        ErrorCode.EXPORT_VALIDATION_FAILED,
                        message="审核结果缺失或字段为空",
                    )
                schema_view = self._build_schema_view(review, schema)
            except AppError as exc:
                skipped.append({"task_id": task_id, "reason": exc.message})
                continue
            except (ValueError, OSError):
                skipped.append({"task_id": task_id, "reason": "审核结果缺失或损坏"})
                continue

            confirmed_by_group = {group_key: [] for group_key in module_group_keys}
            for field in schema_view:
                group_key = field.get("group_key")
                if group_key not in confirmed_by_group:
                    continue
                if field.get("status") not in (FieldStatus.CONFIRMED.value, FieldStatus.MODIFIED.value):
                    continue
                final_value = str(field.get("final_value") or "")
                if not final_value.strip():
                    continue
                confirmed_by_group[group_key].append(field)

            cells: dict[str, str] = {}
            for group_key, _ in self._BATCH_MODULE_COLUMNS:
                confirmed_fields = confirmed_by_group[group_key]
                if not confirmed_fields:
                    cells[group_key] = ""
                    continue
                group_fields = schema_group_fields.get(group_key, [])
                if len(group_fields) == 1:
                    cells[group_key] = str(confirmed_fields[0]["final_value"])
                else:
                    cells[group_key] = "\n".join(
                        f"{field.get('field_name') or field['field_key']}：{field['final_value']}"
                        for field in confirmed_fields
                    )

            if not any(cells.values()):
                skipped.append({"task_id": task_id, "reason": "目标模块中没有任何已确认字段，未生成导出行"})
                continue

            serial += 1
            patient = self._patient_metadata(task)
            rows.append({
                "serial": serial,
                "patient_name": (patient or {}).get("name") or "",
                "cells": cells,
                "task_id": task_id,
            })
        return rows, skipped
```

- [ ] **Step 4: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q`
Expected: PASS（新用例 + 原有用例）

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat:批量Excel导出字段级行构建与模板查询"
```

---

### Task 3: xlsx 批量写入器与 export_batch_excel 组装（唯一文件原子写）

**Files:**
- Modify: `app/backend/services/export_service.py`
- Test: `app/backend/tests/test_export_service.py`

**Interfaces:**
- Consumes: Task 2 的 `_candidate_tasks` / `_build_batch_excel_rows` / `_BATCH_MODULE_COLUMNS`；现有 `_content_types_xml` / `_rels_xml` / `_workbook_xml` / `_workbook_rels_xml` / `_build_sheet_names`。
- Produces:
  - `_BATCH_HEADERS` 类常量：`["序号", "姓名", "主诉", "新病史", "既往史", "个人史", "家族史", "体格检查", "任务编号"]`
  - `_BATCH_COL_LETTERS` 类常量：`["A", "B", "C", "D", "E", "F", "G", "H", "I"]`
  - `export_batch_excel(document_type: str) -> dict`：返回 `{"format": "batch_excel", "export_id": str, "filename": str, "download_url": str, "candidate_count": int, "exported_count": int, "skipped_count": int, "skipped": list[dict]}`；对每个成功行 `record_export(task_id, format="batch_excel", relative_path="batch/batch-<export_id>.xlsx")`
  - `batch_excel_download_path(export_id: str) -> str | None`：校验 32 位字母数字 export_id，文件存在返回绝对路径，否则 `None`
  - `_styles_xml()` / `_batch_sheet_xml(rows)` / `_write_batch_xlsx(path, rows)`：单 sheet、表头 + 数据行、第 9 列隐藏、值列（B–I）带 wrapText 样式（`s="1"`）

- [ ] **Step 1: 写失败测试**

```python
def _read_xlsx_parts(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        styles_xml = archive.read("xl/styles.xml").decode("utf-8")
        return names, sheet_xml, styles_xml


def test_export_batch_excel_writes_unique_file_and_report(tmp_path):
    export_service, task_service = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "2")
    write_batch_task(export_service._store, "1")
    write_batch_review(export_service._store, "1", [confirmed_field("chief_complaint", "主诉", "反复咳嗽")])
    write_batch_review(export_service._store, "2", [confirmed_field("family_history", "家族史", "父亲慢阻肺")])

    report = export_service.export_batch_excel("qwen_batch_admission_record")

    assert report["candidate_count"] == 2
    assert report["exported_count"] == 2
    assert report["skipped_count"] == 0
    assert report["skipped"] == []
    assert len(report["export_id"]) == 32
    assert report["filename"] == f"batch-{report['export_id']}.xlsx"
    assert report["download_url"] == f"/api/tasks/export/batch-excel/{report['export_id']}"

    filepath = export_service.batch_excel_download_path(report["export_id"])
    assert filepath is not None
    assert export_service.batch_excel_download_path("deadbeef") is None

    names, sheet_xml, styles_xml = _read_xlsx_parts(filepath)
    assert "xl/styles.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "任务编号" in sheet_xml
    assert "反复咳嗽" in sheet_xml
    assert "父亲慢阻肺" in sheet_xml
    assert 'hidden="1"' in sheet_xml
    assert "wrapText" in styles_xml
    # 表头 1 行 + 数据 2 行
    assert sheet_xml.count('<row r="') == 3

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q`
Expected: FAIL（`export_batch_excel` 不存在 / `_write_batch_xlsx` 不存在）

- [ ] **Step 3: 实现**（`app/backend/services/export_service.py`）

文件顶部 `import uuid`（在 `import zipfile` 后追加）。

常量（放在 `_HEADERS` / `_COL_LETTERS` 附近）：

```python
    _BATCH_SHEET_NAME = "批量导出"
    _BATCH_HEADERS = ["序号", "姓名", "主诉", "新病史", "既往史", "个人史", "家族史", "体格检查", "任务编号"]
    _BATCH_COL_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]
```

`_content_types_xml` 增加 `include_styles` 参数（现有调用不传，行为不变）：

```python
    @staticmethod
    def _content_types_xml(sheet_count: int, include_styles: bool = False) -> str:
        types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        if include_styles:
            types.append(
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            )
        for i in range(1, sheet_count + 1):
            types.append(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        types.append("</Types>")
        return "\n".join(types)
```

新增 xlsx 批量写入器（放在 `_metadata_sheet_xml` 之后）：

```python
    @staticmethod
    def _styles_xml() -> str:
        """最小样式表:index 0 默认,index 1 wrapText + 顶端对齐(批量导出值列用)。"""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>\n'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>\n'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>\n'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>\n'
            '<cellXfs count="2">\n'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>\n'
            '</cellXfs>\n'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>\n'
            '</styleSheet>'
        )

    @classmethod
    def _batch_sheet_xml(cls, rows: list[dict]) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            # 第 9 列"任务编号"隐藏,便于结果回查且不干扰医生
            '<cols><col min="9" max="9" width="0" hidden="1"/></cols>',
            "<sheetData>",
        ]
        lines.append('<row r="1">')
        for i, header in enumerate(cls._BATCH_HEADERS):
            escaped = escape(header)
            lines.append(f'<c r="{cls._BATCH_COL_LETTERS[i]}1" t="inlineStr"><is><t>{escaped}</t></is></c>')
        lines.append("</row>")

        for row_idx, row in enumerate(rows, start=2):
            lines.append(f'<row r="{row_idx}">')
            values = [
                str(row["serial"]),
                row.get("patient_name", ""),
            ]
            for group_key, _ in cls._BATCH_MODULE_COLUMNS:
                values.append(row.get("cells", {}).get(group_key, ""))
            values.append(row["task_id"])
            for i, val in enumerate(values):
                letter = cls._BATCH_COL_LETTERS[i]
                style = "" if i == 0 else ' s="1"'
                escaped = escape(val)
                lines.append(f'<c r="{letter}{row_idx}"{style} t="inlineStr"><is><t>{escaped}</t></is></c>')
            lines.append("</row>")

        lines.append("</sheetData>")
        lines.append("</worksheet>")
        return "\n".join(lines)

    def _write_batch_xlsx(self, path: str, rows: list[dict]) -> None:
        sheet_name = self._build_sheet_names([self._BATCH_SHEET_NAME])[0]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types_xml(1, include_styles=True))
            z.writestr("_rels/.rels", self._rels_xml())
            z.writestr("xl/workbook.xml", self._workbook_xml([sheet_name]))
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml([sheet_name]))
            z.writestr("xl/styles.xml", self._styles_xml())
            z.writestr("xl/worksheets/sheet1.xml", self._batch_sheet_xml(rows))
```

新增导出与下载方法（放在 `_build_batch_manifest` 之后）：

```python
    def batch_excel_download_path(self, export_id: str) -> str | None:
        if not isinstance(export_id, str) or len(export_id) != 32 or not export_id.isalnum():
            return None
        filepath = os.path.join(self._export_dir, "batch", f"batch-{export_id}.xlsx")
        return filepath if os.path.isfile(filepath) else None

    def export_batch_excel(self, document_type: str) -> dict:
        if not isinstance(document_type, str) or not document_type.strip():
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="document_type 必须为非空字符串")
        if self._document_profiles is None:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未注册或未完成接入，无法导出",
                details={"document_type": document_type},
            )
        try:
            profile = self._document_profiles.get_profile(document_type)
        except AppError as exc:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未注册或未完成接入，无法导出",
                details={"document_type": document_type, "error_code": exc.code},
            )
        if not getattr(profile, "batch_excel_enabled", False):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未启用批量 Excel 导出",
                details={"document_type": document_type},
            )

        candidates = self._candidate_tasks(document_type)
        if not candidates:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="没有可导出的记录",
                details={"document_type": document_type},
            )

        rows, skipped = self._build_batch_excel_rows(candidates, profile.schema)
        if not rows:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="没有可导出的记录",
                details={"document_type": document_type, "skipped": skipped},
            )

        export_id = uuid.uuid4().hex
        filename = f"batch-{export_id}.xlsx"
        relative_path = f"batch/{filename}"
        filepath = os.path.join(self._export_dir, relative_path)
        tmp_path = f"{filepath}.tmp"
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            self._write_batch_xlsx(tmp_path, rows)
            os.replace(tmp_path, filepath)
        except OSError as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="导出文件写入失败",
                details={"format": "batch_excel", "reason": str(exc)},
            )

        for row in rows:
            self._task_service.record_export(row["task_id"], format="batch_excel", relative_path=relative_path)

        return {
            "format": "batch_excel",
            "export_id": export_id,
            "filename": filename,
            "download_url": f"/api/tasks/export/batch-excel/{export_id}",
            "candidate_count": len(candidates),
            "exported_count": len(rows),
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q`
Expected: PASS（Task 3 Step 1 用例 + 现有全部用例）

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat:批量Excel导出生成唯一文件与报告"
```

- [ ] **Step 6: 补充边界用例并通过**

```python
def test_export_batch_excel_all_skipped_raises(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    write_batch_review(export_service._store, "1", [unreviewed_field("chief_complaint", "主诉", "反复咳嗽")])

    with pytest.raises(AppError) as exc_info:
        export_service.export_batch_excel("qwen_batch_admission_record")
    assert exc_info.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.value


def test_export_batch_excel_no_candidates_raises(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1", status="failed")

    with pytest.raises(AppError) as exc_info:
        export_service.export_batch_excel("qwen_batch_admission_record")
    assert exc_info.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.value


def test_export_batch_excel_disabled_template_raises(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    disabled_profile = DocumentProfile(
        document_type="other",
        label="其他",
        schema=BATCH_SCHEMA,
        prompt_version="prompt.v1",
        field_port=object(),
        batch_excel_enabled=False,
    )
    export_service._document_profiles = DocumentProfileRegistry(
        store=export_service._store,
        profiles=[disabled_profile],
        default_document_type="other",
    )

    with pytest.raises(AppError) as exc_info:
        export_service.export_batch_excel("other")
    assert exc_info.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.value


def test_export_batch_excel_twice_does_not_overwrite(tmp_path):
    export_service, _ = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    write_batch_review(export_service._store, "1", [confirmed_field("chief_complaint", "主诉", "反复咳嗽")])

    first = export_service.export_batch_excel("qwen_batch_admission_record")
    second = export_service.export_batch_excel("qwen_batch_admission_record")

    assert first["export_id"] != second["export_id"]
    path1 = export_service.batch_excel_download_path(first["export_id"])
    path2 = export_service.batch_excel_download_path(second["export_id"])
    assert path1 != path2
    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        assert f1.read() == f2.read()   # 内容一致
    # 两次导出都对任务记录 export_summary,最新指向第二次
    task = export_service._task_service.get_task("1")
    files = task["export_summary"]["files"]
    assert [f for f in files if f["format"] == "batch_excel"][0]["relative_path"] == f"batch/batch-{second['export_id']}.xlsx"


def test_export_batch_excel_records_export_for_each_task(tmp_path):
    export_service, task_service = make_batch_export_service(tmp_path)
    write_batch_task(export_service._store, "1")
    write_batch_task(export_service._store, "2")
    write_batch_review(export_service._store, "1", [confirmed_field("chief_complaint", "主诉", "反复咳嗽")])
    write_batch_review(export_service._store, "2", [confirmed_field("family_history", "家族史", "父亲慢阻肺")])

    report = export_service.export_batch_excel("qwen_batch_admission_record")

    for task_id in ("1", "2"):
        summary = task_service.get_task(task_id)["export_summary"]
        assert "batch_excel" in summary["formats"]
        assert [f for f in summary["files"] if f["format"] == "batch_excel"][0]["relative_path"] == f"batch/batch-{report['export_id']}.xlsx"
```

实现要点（`export_service.py`）：

1. `_BATCH_HEADERS` / `_BATCH_COL_LETTERS` 常量。
2. `_content_types_xml(sheet_count, include_styles=False)`：加参数，`include_styles=True` 时插入 styles.xml 的 `<Override>`。
3. `_styles_xml()` 静态方法：最小 styleSheet（见 spec：fonts/fills/borders/cellStyleXfs/cellXfs 两项，index 1 为 `wrapText="1" vertical="top"`）。
4. `_batch_sheet_xml(rows)`：`<cols>` 隐藏第 9 列（`<col min="9" max="9" width="0" hidden="1"/>`）放在 `<sheetData>` 之前；表头行；数据行 A 列 `s="0"`（默认样式），B–I 列 `s="1"`（wrapText）。
5. `_write_batch_xlsx(path, rows)`：zip 组装（Content_Types 含 styles / rels / workbook / workbook.rels / styles.xml / sheet1.xml），复用 `_build_sheet_names([self._BATCH_SHEET_NAME])`。
6. `export_batch_excel(document_type)`：参数校验 → profile 校验（未注册/未启用 → `EXPORT_VALIDATION_FAILED`）→ 候选为空 → 报错 → 行构建 → 全跳过 → 报错 → uuid4().hex 生成 export_id → 写临时文件 `batch-<export_id>.xlsx.tmp` → `os.replace` → 失败删临时文件并抛 `EXPORT_FAILED` → 逐任务 `record_export` → 返回报告。
7. `batch_excel_download_path(export_id)`：32 位字母数字校验 + `os.path.join(self._export_dir, "batch", f"batch-{export_id}.xlsx")` 存在性检查。

注意 `import uuid`（文件顶部）。异常顺序：`export_batch_excel` 里 `AppError` 直接上抛（调用方捕获并记录事件），写入失败转 `EXPORT_FAILED`。

- [ ] **Step 7: 提交**

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat:批量Excel导出生成唯一文件与报告"
```

---

### Task 4: 批量 Excel 路由与契约测试

**Files:**
- Modify: `app/backend/routes/export.py`
- Test: `app/backend/tests/test_api_contracts.py`

**Interfaces:**
- Consumes: Task 2/3 的 `ExportService.batch_excel_templates()`、`export_batch_excel(document_type)`、`batch_excel_download_path(export_id)`；`app.backend.routes._get_export_service`、`_safe_event`；`app.backend.errors.abort`。
- Produces: 三个端点：
  - `GET /api/tasks/export/batch-excel/templates` → `success(data={"templates": [...]})`
  - `POST /api/tasks/export/batch-excel`（body `{"document_type": str}`）→ 校验后调服务，成功 `success(data=report)`；失败 `_safe_event("export_failed", ...)` 后抛 AppError
  - `GET /api/tasks/export/batch-excel/<export_id>` → `send_file(...)`；未知 export_id → `abort(ErrorCode.REQUEST_NOT_FOUND, message="导出文件不存在或已失效")`

- [ ] **Step 1: 写失败契约测试**（`test_api_contracts.py` 追加；复用 `make_client` 与 `JsonStore` 直写任务/审核结果）

```python
from app.backend.enums import FieldStatus
from app.backend.storage.json_store import JsonStore


def _write_batch_excel_seed(tmp_path):
    store = JsonStore(str(tmp_path))
    task = {
        "task_id": "1",
        "display_name": "1",
        "status": "review",
        "created_at": "2026-07-01T10:00:00+00:00",
        "updated_at": "2026-07-01T10:00:00+00:00",
        "upload_token": "token",
        "images": [],
        "page_count": 1,
        "error_code": None,
        "error_message": None,
        "failed_at": None,
        "review_summary": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        "document_type": "copd_admission_record",
        "document_type_label": "入院记录",
        "schema_version": "1.0.0",
        "prompt_version": "prompt.v1",
        "patient_id": "p1",
        "patient_snapshot": {"patient_id": "p1", "name": "张三"},
        "record_date": "2026-07-01",
        "record_time": None,
        "deleted_at": None,
        "metadata_history": [],
        "status_history": [],
    }
    store.write("tasks/1.json", task)
    store.write("results/1/review_result.json", {
        "task_id": "1",
        "schema_version": "1.0.0",
        "document_type": "copd_admission_record",
        "fields": [{"field_key": "chief_complaint", "field_name": "主诉",
                    "final_value": "反复咳嗽", "status": FieldStatus.CONFIRMED.value}],
    })
    return store


def test_batch_excel_templates_endpoint(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    response = client.get("/api/tasks/export/batch-excel/templates")

    assert response.status_code == 200
    templates = response.get_json()["data"]["templates"]
    assert len(templates) >= 1
    assert {"document_type", "label"} <= set(templates[0].keys())


def test_batch_excel_generate_and_download(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)
    _write_batch_excel_seed(tmp_path)

    response = client.post("/api/tasks/export/batch-excel", json={"document_type": "copd_admission_record"})

    assert response.status_code == 200
    report = response.get_json()["data"]
    assert report["exported_count"] == 1
    assert report["skipped_count"] == 0
    download_url = report["download_url"]

    download = client.get(download_url)
    assert download.status_code == 200
    assert download.data[:2] == b"PK"
    assert download.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_batch_excel_missing_document_type(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    response = client.post("/api/tasks/export/batch-excel", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_batch_excel_unknown_template(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    response = client.post("/api/tasks/export/batch-excel", json={"document_type": "not_registered"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.EXPORT_VALIDATION_FAILED.code


def test_batch_excel_download_unknown_export_id(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch)

    response = client.get("/api/tasks/export/batch-excel/0123456789abcdef0123456789abcdef")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.REQUEST_NOT_FOUND.code
```

注意：契约测试 app 默认引擎的 active_profile 由 Task 1 开启 `batch_excel_enabled=True`，其 `document_type` 为 `copd_admission_record`（legacy 引擎默认）；如测试环境实际走 `qwen_batch` 引擎则从 templates 响应动态取第一个 document_type 构造 seed。

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 实现**（`app/backend/routes/export.py` 追加三个端点）

```python
@export_bp.route("/api/tasks/export/batch-excel/templates")
def batch_excel_templates():
    svc = _get_export_service()
    return success(data={"templates": svc.batch_excel_templates()})


@export_bp.route("/api/tasks/export/batch-excel", methods=["POST"])
def export_batch_excel():
    payload = request.get_json(silent=True) or {}
    document_type = payload.get("document_type")
    if not isinstance(document_type, str) or not document_type.strip():
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="document_type 必须为非空字符串")

    svc = _get_export_service()
    try:
        report = svc.export_batch_excel(document_type)
    except AppError as exc:
        _safe_event("export_failed", level="ERROR", format="batch_excel", error_code=exc.code, document_type=document_type)
        raise
    _safe_event(
        "export_succeeded",
        format="batch_excel",
        export_id=report["export_id"],
        exported_count=report["exported_count"],
        skipped_count=report["skipped_count"],
    )
    return success(data=report)


@export_bp.route("/api/tasks/export/batch-excel/<export_id>")
def download_batch_excel(export_id: str):
    svc = _get_export_service()
    filepath = svc.batch_excel_download_path(export_id)
    if filepath is None:
        abort(ErrorCode.REQUEST_NOT_FOUND, message="导出文件不存在或已失效")
    return send_file(
        filepath,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"batch-{export_id}.xlsx",
    )
```

文件顶部 import 补 `abort`：`from ..errors import AppError, ErrorCode, abort`。

- [ ] **Step 4: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py -q`
Expected: PASS（新用例 + 原有用例，含 batch-zip 现有契约）

- [ ] **Step 5: 提交**

```bash
git add app/backend/routes/export.py app/backend/tests/test_api_contracts.py
git commit -m "feat:批量Excel导出生成/下载/模板列表接口"
```

---

### Task 5: 前端任务页"全部导出 Excel"交互

**Files:**
- Modify: `app/frontend/src/api/export.ts`
- Create: `app/frontend/src/components/tasks/BatchExcelExportDialog.tsx`
- Modify: `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`
- Modify: `app/frontend/src/components/tasks/tasks.css`
- Test: `app/frontend/src/pages/tasks/TasksPage.test.tsx`

**Interfaces:**
- Consumes: 现有 `triggerBlobDownload`（TasksPlaceholder 内）、`getApiErrorMessage`（api/client）、`parseBlobError`（api/export.ts 内）。
- Produces:
  - `fetchBatchExcelTemplates(): Promise<BatchExcelTemplate[]>`、`exportTasksBatchExcel(documentType): Promise<BatchExcelReport>`、`downloadBatchExcel(exportId): Promise<Blob>`（api/export.ts）
  - `BatchExcelExportDialog` 组件（props: `isOpen / templates / selectedDocumentType / isExporting / onSelectTemplate / onConfirm / onClose`）
  - TasksPlaceholder 新增：按钮"全部导出 Excel"、模板弹窗、导出摘要（"已导出 N 条，跳过 M 条" + 跳过明细展开）

- [ ] **Step 1: 写失败测试**（`TasksPage.test.tsx` 追加）

```tsx
const batchExcelTemplateFixture = {
  document_type: 'qwen_batch_admission_record',
  label: '入院记录'
};
const batchExcelReportFixture = {
  format: 'batch_excel',
  export_id: 'a'.repeat(32),
  filename: `batch-${'a'.repeat(32)}.xlsx`,
  download_url: `/api/tasks/export/batch-excel/${'a'.repeat(32)}`,
  candidate_count: 3,
  exported_count: 2,
  skipped_count: 1,
  skipped: [{ task_id: '3', reason: '目标模块中没有任何已确认字段，未生成导出行' }]
};

const mockBatchExcelTemplates = () =>
  http.get('*/api/tasks/export/batch-excel/templates', () =>
    HttpResponse.json({ success: true, data: { templates: [batchExcelTemplateFixture] } })
  );
const mockBatchExcelGenerate = () =>
  http.post('*/api/tasks/export/batch-excel', () =>
    HttpResponse.json({ success: true, data: batchExcelReportFixture })
  );
const mockBatchExcelDownload = () =>
  http.get(`*/api/tasks/export/batch-excel/${'a'.repeat(32)}`, () =>
    new HttpResponse(new Blob(['fake-xlsx']), {
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
    })
  );

function mockCreateObjectURL() {
  return vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:fake');
}
```

用例：

```tsx
it('exports all records to one excel via template dialog', async () => {
  const user = userEvent.setup();
  mockCreateObjectURL();
  server.use(
    mockTasks(),
    mockBatchExcelTemplates(),
    mockBatchExcelGenerate(),
    mockBatchExcelDownload()
  );
  render(<TasksPage />);
  await screen.findByRole('table', { name: '任务列表' });

  await user.click(screen.getByRole('button', { name: '全部导出 Excel' }));

  const dialog = await screen.findByRole('dialog', { name: '全部导出 Excel' });
  expect(within(dialog).getByText('入院记录')).toBeTruthy();
  await user.click(within(dialog).getByRole('button', { name: '确认导出' }));

  expect(await screen.findByText(/已导出 2 条，跳过 1 条/)).toBeTruthy();
  expect(URL.createObjectURL).toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: '查看跳过明细' }));
  expect(screen.getByText(/任务 3：目标模块中没有任何已确认字段/)).toBeTruthy();
  expect(screen.queryByRole('dialog', { name: '全部导出 Excel' })).toBeNull();
});

it('shows error message when batch excel generation fails', async () => {
  const user = userEvent.setup();
  server.use(
    mockTasks(),
    mockBatchExcelTemplates(),
    http.post('*/api/tasks/export/batch-excel', () =>
      HttpResponse.json(
        { success: false, error: { code: 'EXPORT_VALIDATION_FAILED', message: '没有可导出的记录', details: {} } },
        { status: 400 }
      )
    )
  );
  render(<TasksPage />);
  await screen.findByRole('table', { name: '任务列表' });

  await user.click(screen.getByRole('button', { name: '全部导出 Excel' }));
  await screen.findByRole('dialog', { name: '全部导出 Excel' });
  await user.click(screen.getByRole('button', { name: '确认导出' }));

  expect(await screen.findByText(/没有可导出的记录/)).toBeTruthy();
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm --prefix app/frontend run test -- --run`
Expected: FAIL（按钮 / dialog 不存在）

- [ ] **Step 3: 实现 api client**（`app/frontend/src/api/export.ts` 追加）

```ts
export type BatchExcelTemplate = {
  document_type: string;
  label: string;
};

export type BatchExcelSkippedItem = {
  task_id: string;
  reason: string;
};

export type BatchExcelReport = {
  format: 'batch_excel';
  export_id: string;
  filename: string;
  download_url: string;
  candidate_count: number;
  exported_count: number;
  skipped_count: number;
  skipped: BatchExcelSkippedItem[];
};

export async function fetchBatchExcelTemplates(): Promise<BatchExcelTemplate[]> {
  const response = await fetch(new URL('/api/tasks/export/batch-excel/templates', window.location.origin).toString());
  if (!response.ok) {
    throw await parseBlobError(response, '获取导出模板失败');
  }
  const body = (await response.json()) as { data: { templates: BatchExcelTemplate[] } };
  return body.data.templates;
}

export async function exportTasksBatchExcel(documentType: string): Promise<BatchExcelReport> {
  const response = await fetch(new URL('/api/tasks/export/batch-excel', window.location.origin).toString(), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ document_type: documentType })
  });
  if (!response.ok) {
    throw await parseBlobError(response, '批量导出失败');
  }
  const body = (await response.json()) as { data: BatchExcelReport };
  return body.data;
}

export async function downloadBatchExcel(exportId: string): Promise<Blob> {
  const response = await fetch(
    new URL(`/api/tasks/export/batch-excel/${encodeURIComponent(exportId)}`, window.location.origin).toString()
  );
  if (!response.ok) {
    throw await parseBlobError(response, '下载导出文件失败');
  }
  return response.blob();
}
```

- [ ] **Step 4: 实现弹窗组件**（新建 `BatchExcelExportDialog.tsx`，参考 CaptureQrDialog 的 div 覆盖层模式）

```tsx
import type { BatchExcelTemplate } from '../../api/export';

type BatchExcelExportDialogProps = {
  isOpen: boolean;
  templates: BatchExcelTemplate[];
  selectedDocumentType: string;
  isExporting: boolean;
  onSelectTemplate: (documentType: string) => void;
  onConfirm: () => void;
  onClose: () => void;
};

export function BatchExcelExportDialog({
  isOpen,
  templates,
  selectedDocumentType,
  isExporting,
  onSelectTemplate,
  onConfirm,
  onClose
}: BatchExcelExportDialogProps) {
  if (!isOpen) return null;
  return (
    <div
      className="batch-excel-dialog-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="batch-excel-dialog" role="dialog" aria-modal="true" aria-label="全部导出 Excel">
        <h2 className="batch-excel-dialog__title">全部导出 Excel</h2>
        <p className="batch-excel-dialog__hint">选择记录模板，该模板全部已完成记录将导出到同一张表</p>
        {templates.length === 0 ? (
          <p className="batch-excel-dialog__empty">暂无可导出的记录模板</p>
        ) : (
          <div className="batch-excel-dialog__templates" role="radiogroup" aria-label="记录模板">
            {templates.map((template) => (
              <label key={template.document_type} className="batch-excel-dialog__template">
                <input
                  type="radio"
                  name="batch-excel-template"
                  value={template.document_type}
                  checked={selectedDocumentType === template.document_type}
                  onChange={() => onSelectTemplate(template.document_type)}
                />
                {template.label}
              </label>
            ))}
          </div>
        )}
        <div className="batch-excel-dialog__actions">
          <button type="button" className="batch-excel-dialog__cancel" onClick={onClose} disabled={isExporting}>
            取消
          </button>
          <button
            type="button"
            className="batch-excel-dialog__confirm"
            disabled={isExporting || templates.length === 0 || !selectedDocumentType}
            onClick={onConfirm}
          >
            {isExporting ? '导出中' : '确认导出'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: 实现页面集成**（`TasksPlaceholder.tsx`）

import 追加：

```tsx
import {
  downloadBatchExcel,
  exportTasksBatchExcel,
  fetchBatchExcelTemplates,
  type BatchExcelReport,
  type BatchExcelTemplate
} from '../../api/export';
import { BatchExcelExportDialog } from '../../components/tasks/BatchExcelExportDialog';
```

state 追加（现有 `lastBatchExport` 附近）：

```tsx
  const [isBatchExcelDialogOpen, setIsBatchExcelDialogOpen] = useState(false);
  const [batchExcelTemplates, setBatchExcelTemplates] = useState<BatchExcelTemplate[]>([]);
  const [selectedBatchTemplate, setSelectedBatchTemplate] = useState('');
  const [isBatchExcelExporting, setIsBatchExcelExporting] = useState(false);
  const [batchExcelReport, setBatchExcelReport] = useState<BatchExcelReport | null>(null);
  const [showBatchExcelSkipped, setShowBatchExcelSkipped] = useState(false);
```

处理函数（`handleBatchExport` 之后）：

```tsx
  async function handleOpenBatchExcelDialog() {
    setError(null);
    try {
      const templates = await fetchBatchExcelTemplates();
      setBatchExcelTemplates(templates);
      setSelectedBatchTemplate(templates[0]?.document_type ?? '');
      setBatchExcelReport(null);
      setShowBatchExcelSkipped(false);
      setIsBatchExcelDialogOpen(true);
    } catch (templateError: unknown) {
      setError(getApiErrorMessage(templateError, '获取导出模板失败，请稍后重试'));
    }
  }

  function handleCloseBatchExcelDialog() {
    if (isBatchExcelExporting) return;
    setIsBatchExcelDialogOpen(false);
  }

  async function handleConfirmBatchExcelExport() {
    if (isBatchExcelExporting || !selectedBatchTemplate) return;
    setIsBatchExcelExporting(true);
    try {
      const report = await exportTasksBatchExcel(selectedBatchTemplate);
      const blob = await downloadBatchExcel(report.export_id);
      triggerBlobDownload(blob, report.filename);
      setBatchExcelReport(report);
      setShowBatchExcelSkipped(false);
      setIsBatchExcelDialogOpen(false);
      setError(null);
    } catch (exportError: unknown) {
      setError(getApiErrorMessage(exportError, '批量导出失败，请稍后重试'));
    } finally {
      setIsBatchExcelExporting(false);
    }
  }

  function handleDismissBatchExcelSummary() {
    setBatchExcelReport(null);
    setShowBatchExcelSkipped(false);
  }
```

工具栏（`tasks-batch-toolbar` 内，批量 zip 按钮旁）加按钮：

```tsx
          <button
            type="button"
            className="tasks-batch-excel-export"
            disabled={isBatchExcelExporting}
            onClick={() => void handleOpenBatchExcelDialog()}
          >
            全部导出 Excel
          </button>
```

批量 zip 摘要条之后追加批量 Excel 摘要与跳过明细：

```tsx
            {batchExcelReport ? (
              <div className="tasks-batch-summary" role="status">
                <span>
                  已导出 {batchExcelReport.exported_count} 条
                  {batchExcelReport.skipped_count > 0 ? `，跳过 ${batchExcelReport.skipped_count} 条` : ''}
                </span>
                {batchExcelReport.skipped_count > 0 ? (
                  <button
                    type="button"
                    className="tasks-batch-summary__detail"
                    onClick={() => setShowBatchExcelSkipped((current) => !current)}
                  >
                    {showBatchExcelSkipped ? '收起跳过明细' : '查看跳过明细'}
                  </button>
                ) : null}
                <button
                  type="button"
                  aria-label="关闭批量导出摘要"
                  className="tasks-batch-summary__close"
                  onClick={handleDismissBatchExcelSummary}
                >
                  ×
                </button>
              </div>
            ) : null}
            {showBatchExcelSkipped && batchExcelReport ? (
              <ul className="tasks-batch-skipped" aria-label="跳过明细">
                {batchExcelReport.skipped.map((item) => (
                  <li key={item.task_id}>
                    任务 {item.task_id}：{item.reason}
                  </li>
                ))}
              </ul>
            ) : null}
```

组件末尾（`CaptureQrDialog` 旁）挂载弹窗：

```tsx
      <BatchExcelExportDialog
        isOpen={isBatchExcelDialogOpen}
        templates={batchExcelTemplates}
        selectedDocumentType={selectedBatchTemplate}
        isExporting={isBatchExcelExporting}
        onSelectTemplate={setSelectedBatchTemplate}
        onConfirm={() => void handleConfirmBatchExcelExport()}
        onClose={handleCloseBatchExcelDialog}
      />
```

`app/frontend/src/components/tasks/tasks.css` 追加样式（在文件末尾，复用现有 CSS 变量的命名风格）：

```css
.batch-excel-dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.batch-excel-dialog {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}

.batch-excel-dialog__title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
}

.batch-excel-dialog__hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: #666;
}

.batch-excel-dialog__empty {
  margin: 0 0 16px;
  font-size: 13px;
  color: #999;
}

.batch-excel-dialog__templates {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.batch-excel-dialog__template {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.batch-excel-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.batch-excel-dialog__cancel,
.batch-excel-dialog__confirm {
  padding: 6px 16px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
}

.batch-excel-dialog__cancel {
  background: #fff;
  border: 1px solid #ccc;
}

.batch-excel-dialog__confirm {
  background: #1677ff;
  border: 1px solid #1677ff;
  color: #fff;
}

.batch-excel-dialog__confirm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tasks-batch-excel-export {
  padding: 6px 12px;
  border-radius: 4px;
  background: #fff;
  border: 1px solid #1677ff;
  color: #1677ff;
  font-size: 14px;
  cursor: pointer;
}

.tasks-batch-excel-export:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.tasks-batch-skipped {
  margin: 4px 0 0;
  padding: 8px 12px;
  border: 1px solid #f0c36d;
  background: #fffbe6;
  border-radius: 4px;
  list-style: none;
  font-size: 13px;
  color: #8a6d3b;
}
```

- [ ] **Step 6: 运行测试与类型检查**

Run: `npm --prefix app/frontend run typecheck && npm --prefix app/frontend run test -- --run`
Expected: PASS（新用例 + 原有用例）

- [ ] **Step 7: 提交**

```bash
git add app/frontend/src/api/export.ts app/frontend/src/components/tasks/BatchExcelExportDialog.tsx app/frontend/src/pages/tasks/TasksPlaceholder.tsx app/frontend/src/components/tasks/tasks.css app/frontend/src/pages/tasks/TasksPage.test.tsx
git commit -m "feat:任务列表页一键全部导出Excel(模板选择与跳过明细)"
```

---

### Task 6: 回归与文档同步

**Files:**
- Modify: `docs/Shared/error-codes.md`（如 EXPORT 错误码描述有缺口）
- Modify: `docs/PRD文档/PRD任务清单.md`（增补批量 Excel 条目）
- 验证全量测试

- [ ] **Step 1: 检查错误码文档**

Read: `docs/Shared/error-codes.md` 中 `EXPORT_VALIDATION_FAILED` / `EXPORT_FAILED` 描述。
如果描述仅覆盖单任务场景（如"导出请求非法或任务状态不允许导出"），补充一句覆盖批量场景（模板未启用批量导出、无记录可导出）的说明，同步 `app/backend/errors.py` 中对应 `default_message` 保持基本一致即可，不新增错误码。

- [ ] **Step 2: 更新 PRD 任务清单**

在 `docs/PRD文档/PRD任务清单.md` 的 BE-MVP-05 系列（或 BE-MVP-07 附近）追加已完成条目，说明：批量 Excel 导出（按模板一键导出全部 review/done 任务到同一张表；字段级只写已确认字段；生成/下载接口分离；唯一文件原子写；模板显式启用 batch_excel），对应文件 `app/backend/services/export_service.py`、`app/backend/routes/export.py`、`app/frontend/src/pages/tasks/TasksPlaceholder.tsx`。

- [ ] **Step 3: 全量后端测试**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests -q`
Expected: 全部通过（新增用例 + 原有 JSON zip / 单任务 Excel 契约）

- [ ] **Step 4: 全量前端验证**

Run: `npm --prefix app/frontend run typecheck && npm --prefix app/frontend run test -- --run && npm --prefix app/frontend run build`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add docs/Shared/error-codes.md docs/PRD文档/PRD任务清单.md
git commit -m "docs:同步批量Excel导出错误码描述与PRD任务清单"
```
