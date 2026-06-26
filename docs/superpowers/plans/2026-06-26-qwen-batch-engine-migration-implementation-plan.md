# Qwen Batch Engine Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将师弟 `aufgh/qwen` 的 Qwen OCR/LLM 批处理架构作为独立算法引擎接入当前离线工作站，并让后端、前端、审核和导出默认面向 Qwen 中文嵌套字段契约演进。

**Architecture:** 采用 `algorithms/qwen_batch_engine/upstream + overlay + adapter` 隔离算法代码，后端只通过 `app/backend/services/algorithm_ports/qwen_batch_adapter.py` 和批处理 orchestrator 依赖稳定 job/result 契约。第一阶段默认不启用新引擎，完成契约测试、前端审核、导出、离线配置和回滚开关后，再通过配置切换默认路径。

**Tech Stack:** Python 3.10+/pytest/PyYAML/OpenAI-compatible vLLM subprocess adapter, Flask backend JSON store, React/TypeScript/Vitest, standard-library XLSX writer, local offline Docker packaging.

---

## Source Artifacts

- Spec: `docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md`
- Upstream snapshot source: `/tmp/aufgh-qwen`
- Upstream commit: `a746ba9d061d2af8878485f1f837e4d10e2bd755`
- Current backend algorithm boundary: `app/backend/services/algorithm_ports/`
- Current frontend review boundary: `app/frontend/src/components/review/`

## Subagent-Driven Execution Protocol

Use Claude Code goal mode for execution and keep this plan as the loop contract. The controller agent must not implement tasks itself when using subagent-driven mode. For each task:

1. Dispatch one fresh implementer subagent with the task text, relevant spec excerpts, file paths, and verification command.
2. Require the implementer to run the task's focused tests and commit with the task's Chinese commit message.
3. Dispatch a spec-compliance reviewer subagent. It reviews only whether the task matches the spec and this plan.
4. If the spec reviewer finds issues, dispatch the same implementer context to fix them, then rerun the spec reviewer.
5. Dispatch a code-quality reviewer subagent. It reviews modularity, privacy, failure semantics, tests, and maintainability.
6. If the quality reviewer finds issues, dispatch the same implementer context to fix them, then rerun the quality reviewer.
7. Mark the task complete only after both reviews approve.

Do not run two implementation subagents in parallel. The backend and frontend files touched here share contracts and must move in a controlled sequence.

Per-task review angles:

- Spec reviewer: algorithm boundary, field contract, failure semantics, no silent fallback, no frontend inference.
- Quality reviewer: small files, stable interfaces, typed contracts, no patient data logs, no unrelated refactors.

Final review wave after all tasks:

- Architecture reviewer: checks `upstream/overlay/adapter/app/backend` boundaries and old-path rollback.
- Field-contract reviewer: checks Qwen schema, `qwen_path`, `qwen_type`, T/J semantics, export fields.
- Evidence reviewer: checks anchors, offsets, highlighter behavior, missing evidence warnings.
- Backend failure/privacy reviewer: checks failed-task semantics, logs, subprocess errors, no raw OCR/full model output in ordinary event logs.
- Frontend UX reviewer: checks T/J controls, review completion, read-only mode, mobile/desktop layout.
- Offline deployment reviewer: checks no runtime network dependency, no `latest` default for production path, no model/data/cache commits.
- Test reviewer: checks focused tests, full backend tests, frontend typecheck/build/tests, and documented unable-to-run items.

## Files And Responsibilities

### New Algorithm Module

- Create `algorithms/qwen_batch_engine/upstream/`: synced upstream files, excluding `.git`, `.env`, `__pycache__`, real input/output/log/cache/model files.
- Create `algorithms/qwen_batch_engine/overlay/`: productization config and prompt records.
- Create `algorithms/qwen_batch_engine/adapter/normalize_result.py`: pure normalization from Qwen structured output and anchors to workstation result/candidates.
- Create `algorithms/qwen_batch_engine/adapter/run_job.py`: stable command entry for `python algorithms/qwen_batch_engine/adapter/run_job.py --job-dir data/algorithm_jobs/{task_id}`.
- Create `algorithms/qwen_batch_engine/snapshots/2026-06-26-a746ba9/`: local snapshot of schema, prompts, model/runtime config, and contract smoke note.
- Create `algorithms/qwen_batch_engine/VERSION`: upstream commit and adapter schema metadata.

### Backend

- Modify `app/backend/config.py`: add qwen batch config keys with safe defaults.
- Modify `app/config/default.yaml`: expose safe, disabled-by-default qwen batch settings.
- Modify `app/backend/__init__.py`: register Qwen batch schema/profile/orchestrator behind config flag.
- Modify `app/backend/services/schema_loader.py`: preserve schema metadata such as `qwen_path`, `qwen_type`, `review_control`, `options`.
- Modify `app/backend/services/document_profiles.py`: allow an all-in-one algorithm profile without forcing `field_port` to be a legacy field-only port.
- Create `app/backend/services/algorithm_ports/qwen_batch_adapter.py`: creates job directories, manifest, calls `run_job.py`, reads `result.json`.
- Create `app/backend/services/algorithm_ports/qwen_batch_orchestrator.py`: product backend orchestration around the batch adapter.
- Modify `app/backend/services/_review_field_factory.py`: preserve Qwen metadata in review fields.
- Modify `app/backend/services/review_service.py`: hydrate/schema-order Qwen metadata and accept J-field status values as strings.
- Modify `app/backend/services/export_service.py`: export `qwen_type`, `qwen_path`, J status, and anchor metadata.

### Frontend

- Modify `app/frontend/src/api/review.ts`: type Qwen metadata and preserve it through normalization.
- Modify `app/frontend/src/components/review/FieldList.tsx`: render `T` fields as text and `J` fields as status segmented controls.
- Modify `app/frontend/src/pages/review/ReviewPage.tsx`: keep evidence selection compatible with anchor metadata.
- Modify `app/frontend/src/pages/review/demoReviewSample.ts`: add a Qwen T/J fixture for local demo and component tests.
- Modify `app/frontend/src/pages/review/review.css`: compact segmented control styling that fits desktop and mobile widths.

### Tests

- Create `app/backend/tests/test_qwen_batch_engine_layout.py`
- Create `app/backend/tests/test_qwen_batch_normalize_result.py`
- Create `app/backend/tests/test_qwen_batch_run_job.py`
- Create `app/backend/tests/test_qwen_batch_adapter.py`
- Create `app/backend/tests/test_qwen_batch_orchestrator.py`
- Modify `app/backend/tests/test_schema_loader.py`
- Modify `app/backend/tests/test_config.py`
- Modify `app/backend/tests/test_review_service.py`
- Modify `app/backend/tests/test_export_service.py`
- Modify `app/frontend/src/components/review/FieldList.test.tsx`
- Modify `app/frontend/src/api/shared-contracts.test.ts`
- Modify `app/frontend/src/pages/review/ReviewPage.test.tsx`

---

### Task 1: Update Backend Contract Docs For Qwen Batch Path

**Files:**
- Modify: `docs/Backend/Backend_TDD/02-algorithm-ports.md`
- Modify: `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`
- Verify: `docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md`

- [ ] **Step 1: Add a Qwen batch contract section to `02-algorithm-ports.md`**

Add a section named `Qwen 批处理算法引擎端口` after the current local LLM adapter section. It must state:

```markdown
## Qwen 批处理算法引擎端口

`qwen_batch_engine` 是 OCR、图片预处理、并发调度、OCR 合并、全局结构化抽取和锚点证据生成的一体化算法子系统。后端主流程不得 import `algorithms/qwen_batch_engine/upstream/scripts/process.py` 内部函数，只能调用稳定入口：

```text
python algorithms/qwen_batch_engine/adapter/run_job.py --job-dir data/algorithm_jobs/{task_id}
```

批处理 job 输入：

- `data/algorithm_jobs/{task_id}/manifest.json`
- `data/algorithm_jobs/{task_id}/input/page_001.jpg`

批处理 job 标准输出：

- `output/merged_ocr.txt`
- `output/merged_structured.json`
- `output/anchors.json`
- `output/summary.json`
- `result.json`
- `error.json`，仅失败时存在

后端只读取 `result.json` 并写入：

- `results/{task_id}/document_result.json`
- `results/{task_id}/field_candidates.json`

Qwen 字段以 `qwen_batch_admission_record.v1` schema 为准。`T` 字段保存原文截取值，`J` 字段保存 `正常 / 异常 / 未提及 / 不确定` 状态文本。前端和导出使用 schema 中的 `qwen_type`、`qwen_path` 和 `field_key`，不得把 Qwen 字段强行映射回旧 61 字段作为默认路径。
```

- [ ] **Step 2: Add failure rows to `07-algorithm-failure-contracts.md`**

Add rows for:

```markdown
| BE-QWEN-BATCH-001 | 契约 | job 目录或 manifest 创建失败时，任务进入 `failed`，错误码为 `ALGORITHM_MODULE_FAILED` | 空 job 被当成成功 |
| BE-QWEN-BATCH-002 | 契约 | `run_job.py` 非 0 退出、超时、未生成 `result.json` 或生成非法 JSON 时，任务进入 `failed` | 子进程失败被吞掉 |
| BE-QWEN-BATCH-003 | 契约 | `merged_ocr.txt` 为空、`merged_structured.json` 缺失或结构非法时，任务进入 `failed` | OCR/抽取全空仍进入审核 |
| BE-QWEN-BATCH-004 | 契约 | Qwen 输出字段整体为空时，任务进入 `failed`；单字段锚点缺失只标重点核验 | 字段全空进入审核或单字段问题阻断整单 |
| BE-QWEN-BATCH-005 | 隐私 | 事件日志只记录 job_id、engine、耗时、文件数量、错误类型，不记录 OCR 全文、患者姓名、图片 base64、完整 prompt 或完整模型输出 | 敏感原文进入普通日志 |
```

- [ ] **Step 3: Verify docs reference the spec**

Run:

```bash
rg "qwen_batch_engine|BE-QWEN-BATCH|run_job.py --job-dir" docs/Backend/Backend_TDD docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md
```

Expected: output includes the new Qwen batch section, all five `BE-QWEN-BATCH-*` rows, and the stable `run_job.py --job-dir` command.

- [ ] **Step 4: Commit**

```bash
git add docs/Backend/Backend_TDD/02-algorithm-ports.md docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md
git commit -m "补充Qwen批处理端口契约"
```

**Review Gate:** Spec reviewer checks the docs match the migration spec and do not weaken failed-task semantics. Quality reviewer checks the docs do not describe implementation internals as product behavior.

---

### Task 2: Add Algorithm Module Layout, Upstream Snapshot, And Safety Ignores

**Files:**
- Create: `algorithms/qwen_batch_engine/upstream/`
- Create: `algorithms/qwen_batch_engine/overlay/CHANGELOG.md`
- Create: `algorithms/qwen_batch_engine/overlay/config/qwen_batch_config.yaml`
- Create: `algorithms/qwen_batch_engine/overlay/prompts/extraction_system_prompt.txt`
- Create: `algorithms/qwen_batch_engine/overlay/prompts/extraction_user_prompt_template.txt`
- Create: `algorithms/qwen_batch_engine/adapter/README.md`
- Create: `algorithms/qwen_batch_engine/snapshots/2026-06-26-a746ba9/`
- Create: `algorithms/qwen_batch_engine/VERSION`
- Modify: `.gitignore`
- Test: `app/backend/tests/test_qwen_batch_engine_layout.py`

- [ ] **Step 1: Write the failing layout test**

Create `app/backend/tests/test_qwen_batch_engine_layout.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = ROOT / "algorithms" / "qwen_batch_engine"


def test_qwen_batch_engine_layout_exists():
    assert (ENGINE_ROOT / "upstream" / "scripts" / "process.py").is_file()
    assert (ENGINE_ROOT / "upstream" / "config.yaml").is_file()
    assert (ENGINE_ROOT / "overlay" / "CHANGELOG.md").is_file()
    assert (ENGINE_ROOT / "adapter" / "README.md").is_file()
    assert (ENGINE_ROOT / "VERSION").is_file()


def test_qwen_batch_engine_version_records_upstream_commit():
    version_text = (ENGINE_ROOT / "VERSION").read_text(encoding="utf-8")
    assert "upstream_commit=a746ba9d061d2af8878485f1f837e4d10e2bd755" in version_text
    assert "schema_version=qwen_batch_admission_record.v1" in version_text


def test_qwen_batch_engine_does_not_commit_runtime_or_secret_files():
    forbidden = [
        ENGINE_ROOT / "upstream" / ".git",
        ENGINE_ROOT / "upstream" / ".env",
        ENGINE_ROOT / "upstream" / "scripts" / "__pycache__",
    ]
    for path in forbidden:
        assert not path.exists(), f"forbidden upstream artifact committed: {path}"


def test_qwen_batch_snapshot_contains_minimum_audit_files():
    snapshot = ENGINE_ROOT / "snapshots" / "2026-06-26-a746ba9"
    expected = [
        "upstream_commit.txt",
        "schema_template.yaml",
        "prompt_system.txt",
        "prompt_user_template.txt",
        "model_config.yaml",
        "runtime_config.yaml",
        "smoke_result.md",
    ]
    for filename in expected:
        assert (snapshot / filename).is_file(), f"missing snapshot file: {filename}"
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_engine_layout.py -q
```

Expected: FAIL because `algorithms/qwen_batch_engine/` does not exist.

- [ ] **Step 3: Copy upstream files into the isolated upstream directory**

Copy only these upstream files from `/tmp/aufgh-qwen`:

```text
config.yaml
Dockerfile.qwen-client
docker-compose.yaml
scripts/process.py
start.bat
stop.bat
input/.gitkeep
output/.gitkeep
logs/.gitkeep
model/.gitkeep
vllm_cache/.gitkeep
```

Do not copy:

```text
.git/
.env
scripts/__pycache__/
input/* except .gitkeep
output/* except .gitkeep
logs/* except .gitkeep
model/* except .gitkeep
vllm_cache/* except .gitkeep
```

- [ ] **Step 4: Add `.gitignore` safety rules**

Append these rules to `.gitignore`:

```gitignore

# Qwen batch engine runtime data
data/algorithm_jobs/*
!data/algorithm_jobs/README.md
algorithms/qwen_batch_engine/upstream/.env
algorithms/qwen_batch_engine/upstream/input/*
algorithms/qwen_batch_engine/upstream/output/*
algorithms/qwen_batch_engine/upstream/logs/*
algorithms/qwen_batch_engine/upstream/model/*
algorithms/qwen_batch_engine/upstream/vllm_cache/*
algorithms/qwen_batch_engine/upstream/scripts/__pycache__/
!algorithms/qwen_batch_engine/upstream/input/.gitkeep
!algorithms/qwen_batch_engine/upstream/output/.gitkeep
!algorithms/qwen_batch_engine/upstream/logs/.gitkeep
!algorithms/qwen_batch_engine/upstream/model/.gitkeep
!algorithms/qwen_batch_engine/upstream/vllm_cache/.gitkeep
```

- [ ] **Step 5: Add version, overlay, adapter docs, and snapshot files**

Create `algorithms/qwen_batch_engine/VERSION`:

```text
engine=qwen_batch_engine
upstream_repo=https://github.com/aufgh/qwen
upstream_commit=a746ba9d061d2af8878485f1f837e4d10e2bd755
schema_version=qwen_batch_admission_record.v1
adapter_contract=job_result.v1
synced_at=2026-06-26
```

Create `algorithms/qwen_batch_engine/overlay/CHANGELOG.md`:

```markdown
# Qwen Batch Engine Overlay Changelog

## 2026-06-26

- 同步上游 `aufgh/qwen` commit `a746ba9d061d2af8878485f1f837e4d10e2bd755`。
- 新增工作站适配目标：job manifest、标准 `result.json`、`anchors.json` offset 回填、离线配置约束。
- 未改变上游字段含义、T/J 语义、核心 prompt 流程或并发算法。
- 当前回归：contract tests only；真实模型 smoke 由本地离线环境执行后补写 `snapshots/2026-06-26-a746ba9/smoke_result.md`。
```

Create `algorithms/qwen_batch_engine/adapter/README.md`:

```markdown
# Qwen Batch Engine Adapter

This adapter is the only stable interface between the workstation backend and the synced upstream batch pipeline.

Allowed responsibilities:

- validate `manifest.json`
- prepare job directories
- call the configured upstream runner
- normalize `merged_ocr.txt`, `merged_structured.json`, `anchors.json`, and `summary.json`
- write `result.json` or `error.json`

Forbidden responsibilities:

- infer medical field values from OCR text
- remap Qwen Chinese nested fields back to the legacy 61-field schema as the default path
- swallow upstream errors and return empty success
- log OCR full text, image base64, prompt full text, patient names, or full model output in ordinary logs
```

Create `algorithms/qwen_batch_engine/overlay/config/qwen_batch_config.yaml` by copying the safe model/inference/processing keys from upstream `config.yaml`, preserving `temperature: 0.0`, `thinking_enabled: false`, `max_workers: 8`, and schema template.

Create prompt snapshot files:

```text
algorithms/qwen_batch_engine/overlay/prompts/extraction_system_prompt.txt
algorithms/qwen_batch_engine/overlay/prompts/extraction_user_prompt_template.txt
algorithms/qwen_batch_engine/snapshots/2026-06-26-a746ba9/prompt_system.txt
algorithms/qwen_batch_engine/snapshots/2026-06-26-a746ba9/prompt_user_template.txt
```

Use the exact prompt text from `/tmp/aufgh-qwen/config.yaml` `extraction.system_prompt` and `extraction.user_prompt_template`.

Create `snapshots/2026-06-26-a746ba9/upstream_commit.txt`:

```text
a746ba9d061d2af8878485f1f837e4d10e2bd755
```

Create `snapshots/2026-06-26-a746ba9/smoke_result.md`:

```markdown
# Smoke Result

- Date: 2026-06-26
- Upstream commit: `a746ba9d061d2af8878485f1f837e4d10e2bd755`
- Model smoke: not run in this contract-only migration task.
- Reason: implementation plan is adding the stable module boundary before enabling real local vLLM execution.
- Completed verification: layout and contract tests must pass before switching `algorithm_engine` to `qwen_batch`.
```

- [ ] **Step 6: Run focused test**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_engine_layout.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .gitignore algorithms/qwen_batch_engine app/backend/tests/test_qwen_batch_engine_layout.py
git commit -m "落仓Qwen批处理算法快照"
```

**Review Gate:** Spec reviewer checks upstream isolation and snapshot minimums. Quality reviewer checks no secret/runtime/model data is committed.

---

### Task 3: Add Qwen Schema And Preserve Schema Metadata

**Files:**
- Create: `app/config/schemas/qwen_batch_admission_record.v1.yaml`
- Modify: `app/backend/services/schema_loader.py`
- Modify: `app/backend/tests/test_schema_loader.py`

- [ ] **Step 1: Add failing schema metadata tests**

Append to `app/backend/tests/test_schema_loader.py`:

```python
def test_schema_loader_preserves_qwen_field_metadata(tmp_path):
    from app.backend.services.schema_loader import load_schema

    path = _write_yaml(
        tmp_path,
        "schema.yaml",
        {
            "version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "field_groups": [
                {
                    "group_key": "chief_complaint",
                    "group_label": "主诉",
                    "fields": [
                        {
                            "field_key": "chief_complaint",
                            "label": "主诉",
                            "type": "string",
                            "qwen_path": ["主诉"],
                            "qwen_type": "T",
                            "review_control": "text",
                        }
                    ],
                },
                {
                    "group_key": "history_of_present_illness",
                    "group_label": "现病史",
                    "fields": [
                        {
                            "field_key": "hpi_mental_sleep_appetite",
                            "label": "精神睡眠食欲",
                            "type": "string",
                            "qwen_path": ["现病史", "精神睡眠食欲"],
                            "qwen_type": "J",
                            "review_control": "judgement",
                            "options": ["正常", "异常", "未提及", "不确定"],
                        }
                    ],
                },
            ],
        },
    )

    schema = load_schema(str(path))
    first = schema["field_groups"][0]["fields"][0]
    second = schema["field_groups"][1]["fields"][0]
    assert first["qwen_path"] == ["主诉"]
    assert first["qwen_type"] == "T"
    assert first["review_control"] == "text"
    assert second["qwen_path"] == ["现病史", "精神睡眠食欲"]
    assert second["qwen_type"] == "J"
    assert second["options"] == ["正常", "异常", "未提及", "不确定"]


def test_load_qwen_batch_admission_record_schema_from_repo():
    from app.backend.config import PROJECT_ROOT
    from app.backend.services.schema_loader import load_schema
    import os

    path = os.path.join(
        PROJECT_ROOT,
        "app",
        "config",
        "schemas",
        "qwen_batch_admission_record.v1.yaml",
    )

    schema = load_schema(path)
    assert schema["version"] == "qwen_batch_admission_record.v1"
    assert schema["document_type"] == "qwen_batch_admission_record"

    fields = [
        field
        for group in schema["field_groups"]
        for field in group["fields"]
    ]
    keys = [field["field_key"] for field in fields]
    assert len(keys) == 51
    assert len(keys) == len(set(keys))
    assert "aux_crp" in keys
    assert "aux_blood_gas" in keys
    assert "aux_blood_gas_ph" not in keys
    assert "pe_vital_signs" in keys
    assert "pe_temperature" not in keys
    assert all(field["qwen_type"] in {"T", "J"} for field in fields)
    assert all(isinstance(field["qwen_path"], list) and field["qwen_path"] for field in fields)
```

- [ ] **Step 2: Run test and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py::test_schema_loader_preserves_qwen_field_metadata app/backend/tests/test_schema_loader.py::test_load_qwen_batch_admission_record_schema_from_repo -q
```

Expected: FAIL because metadata is dropped and schema file does not exist.

- [ ] **Step 3: Modify schema loader to preserve whitelisted metadata**

In `app/backend/services/schema_loader.py`, add:

```python
OPTIONAL_FIELD_METADATA_KEYS = {
    "qwen_path",
    "qwen_type",
    "review_control",
    "options",
    "export_label",
}
```

Inside the normalized field construction, validate:

```python
            metadata = {}
            qwen_path = field.get("qwen_path")
            if qwen_path is not None:
                if (
                    not isinstance(qwen_path, list)
                    or not qwen_path
                    or not all(isinstance(item, str) and item.strip() for item in qwen_path)
                ):
                    raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                                   message="field qwen_path 必须为非空 string list",
                                   details={"reason": "qwen_path 非法",
                                            "group_key": group_key,
                                            "field_key": field_key})
                metadata["qwen_path"] = qwen_path

            qwen_type = field.get("qwen_type")
            if qwen_type is not None:
                if qwen_type not in {"T", "J"}:
                    raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                                   message="field qwen_type 非法",
                                   details={"reason": "qwen_type 非法",
                                            "group_key": group_key,
                                            "field_key": field_key,
                                            "qwen_type": qwen_type})
                metadata["qwen_type"] = qwen_type

            review_control = field.get("review_control")
            if review_control is not None:
                if review_control not in {"text", "judgement"}:
                    raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                                   message="field review_control 非法",
                                   details={"reason": "review_control 非法",
                                            "group_key": group_key,
                                            "field_key": field_key})
                metadata["review_control"] = review_control

            options = field.get("options")
            if options is not None:
                if (
                    not isinstance(options, list)
                    or not options
                    or not all(isinstance(item, str) and item.strip() for item in options)
                ):
                    raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                                   message="field options 必须为非空 string list",
                                   details={"reason": "options 非法",
                                            "group_key": group_key,
                                            "field_key": field_key})
                metadata["options"] = options

            export_label = field.get("export_label")
            if export_label is not None:
                if not isinstance(export_label, str):
                    raise AppError(ErrorCode.INTERNAL_SERVER_ERROR,
                                   message="field export_label 必须为 string",
                                   details={"reason": "export_label 非法",
                                            "group_key": group_key,
                                            "field_key": field_key})
                metadata["export_label"] = export_label
```

Change `normalized_fields.append({...})` to:

```python
            normalized_field = {
                "field_key": field_key,
                "label": label,
                "type": field_type,
                "required": required,
                "hint": hint,
            }
            normalized_field.update(metadata)
            normalized_fields.append(normalized_field)
```

- [ ] **Step 4: Create Qwen schema**

Create `app/config/schemas/qwen_batch_admission_record.v1.yaml` with:

```yaml
version: "qwen_batch_admission_record.v1"
document_type: "qwen_batch_admission_record"
field_groups:
  - group_key: chief_complaint
    group_label: 主诉
    fields:
      - field_key: chief_complaint
        label: 主诉
        type: string
        qwen_path: ["主诉"]
        qwen_type: T
        review_control: text
  - group_key: history_of_present_illness
    group_label: 现病史
    fields:
      - field_key: hpi_initial_onset
        label: 初次发病情况
        type: string
        qwen_path: ["现病史", "初次发病情况"]
        qwen_type: T
        review_control: text
      - field_key: hpi_subsequent_onset
        label: 后续发病情况
        type: string
        qwen_path: ["现病史", "后续发病情况"]
        qwen_type: T
        review_control: text
      - field_key: hpi_in_hospital_diagnosis
        label: 院内诊断情况
        type: string
        qwen_path: ["现病史", "院内诊断情况"]
        qwen_type: T
        review_control: text
      - field_key: hpi_medications
        label: 治疗药物
        type: string
        qwen_path: ["现病史", "治疗药物"]
        qwen_type: T
        review_control: text
      - field_key: hpi_recent_symptoms
        label: 近期症状
        type: string
        qwen_path: ["现病史", "近期症状"]
        qwen_type: T
        review_control: text
      - field_key: hpi_mental_sleep_appetite
        label: 精神睡眠食欲
        type: string
        qwen_path: ["现病史", "精神睡眠食欲"]
        qwen_type: J
        review_control: judgement
        options: ["正常", "异常", "未提及", "不确定"]
      - field_key: hpi_stool
        label: 大便情况
        type: string
        qwen_path: ["现病史", "大便情况"]
        qwen_type: T
        review_control: text
      - field_key: hpi_urination
        label: 小便情况
        type: string
        qwen_path: ["现病史", "小便情况"]
        qwen_type: J
        review_control: judgement
        options: ["正常", "异常", "未提及", "不确定"]
      - field_key: hpi_weight_change
        label: 体重变化
        type: string
        qwen_path: ["现病史", "体重变化"]
        qwen_type: T
        review_control: text
  - group_key: past_history
    group_label: 既往史
    fields:
      - {field_key: pmh_heart_disease, label: 心脏病, type: string, qwen_path: ["既往史", "心脏病"], qwen_type: T, review_control: text}
      - {field_key: pmh_hypertension, label: 高血压, type: string, qwen_path: ["既往史", "高血压"], qwen_type: T, review_control: text}
      - {field_key: pmh_diabetes, label: 糖尿病, type: string, qwen_path: ["既往史", "糖尿病"], qwen_type: T, review_control: text}
      - {field_key: pmh_hepatitis_b, label: 乙肝, type: string, qwen_path: ["既往史", "乙肝"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_bloody_stool, label: 便血, type: string, qwen_path: ["既往史", "便血"], qwen_type: T, review_control: text}
      - {field_key: pmh_nephritis, label: 肾炎, type: string, qwen_path: ["既往史", "肾炎"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_blood_disease, label: 血液病, type: string, qwen_path: ["既往史", "血液病"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_coronary_heart_disease, label: 冠心病, type: string, qwen_path: ["既往史", "冠心病"], qwen_type: T, review_control: text}
      - {field_key: pmh_cerebral_infarction, label: 脑梗塞, type: string, qwen_path: ["既往史", "脑梗塞"], qwen_type: T, review_control: text}
      - {field_key: pmh_surgery_history, label: 手术史, type: string, qwen_path: ["既往史", "手术史"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_transfusion_history, label: 输血史, type: string, qwen_path: ["既往史", "输血史"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_blood_product_history, label: 血制品史, type: string, qwen_path: ["既往史", "血制品史"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pmh_allergy_history, label: 过敏史, type: string, qwen_path: ["既往史", "过敏史"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
  - group_key: personal_history
    group_label: 个人史
    fields:
      - {field_key: personal_work, label: 工作, type: string, qwen_path: ["个人史", "工作"], qwen_type: T, review_control: text}
      - {field_key: personal_smoking_history, label: 吸烟史, type: string, qwen_path: ["个人史", "吸烟史"], qwen_type: T, review_control: text}
      - {field_key: personal_drinking_history, label: 饮酒史, type: string, qwen_path: ["个人史", "饮酒史"], qwen_type: T, review_control: text}
  - group_key: family_history
    group_label: 家族史
    fields:
      - {field_key: family_history, label: 家族史, type: string, qwen_path: ["家族史"], qwen_type: T, review_control: text}
  - group_key: physical_exam
    group_label: 体格检查
    fields:
      - {field_key: pe_vital_signs, label: 生命体征, type: string, qwen_path: ["体格检查", "生命体征"], qwen_type: T, review_control: text}
      - {field_key: pe_height_weight_bmi, label: 身高体重BMI, type: string, qwen_path: ["体格检查", "身高体重BMI"], qwen_type: T, review_control: text}
      - {field_key: pe_skin, label: 皮肤, type: string, qwen_path: ["体格检查", "皮肤"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_eyes, label: 眼部, type: string, qwen_path: ["体格检查", "眼部"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_ears, label: 耳部, type: string, qwen_path: ["体格检查", "耳部"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_nose, label: 鼻部, type: string, qwen_path: ["体格检查", "鼻部"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_oral_cavity, label: 口腔, type: string, qwen_path: ["体格检查", "口腔"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_neck, label: 颈部, type: string, qwen_path: ["体格检查", "颈部"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_chest, label: 胸部, type: string, qwen_path: ["体格检查", "胸部"], qwen_type: T, review_control: text}
      - {field_key: pe_respiration, label: 呼吸, type: string, qwen_path: ["体格检查", "呼吸"], qwen_type: T, review_control: text}
      - {field_key: pe_heart_rhythm, label: 心律, type: string, qwen_path: ["体格检查", "心律"], qwen_type: T, review_control: text}
      - {field_key: pe_abdomen, label: 腹部, type: string, qwen_path: ["体格检查", "腹部"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_limbs, label: 四肢, type: string, qwen_path: ["体格检查", "四肢"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: pe_neurological, label: 神经, type: string, qwen_path: ["体格检查", "神经"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
  - group_key: auxiliary_exam
    group_label: 辅助检查
    fields:
      - {field_key: aux_chest_ct, label: 胸部CT, type: string, qwen_path: ["辅助检查", "胸部CT"], qwen_type: T, review_control: text}
      - {field_key: aux_echocardiography, label: 心脏超声, type: string, qwen_path: ["辅助检查", "心脏超声"], qwen_type: T, review_control: text}
      - {field_key: aux_blood_gas, label: 血气, type: string, qwen_path: ["辅助检查", "血气"], qwen_type: T, review_control: text}
      - {field_key: aux_crp, label: CRP, type: string, qwen_path: ["辅助检查", "CRP"], qwen_type: T, review_control: text}
      - {field_key: aux_blood_routine, label: 血常规, type: string, qwen_path: ["辅助检查", "血常规"], qwen_type: T, review_control: text}
      - {field_key: aux_electrolytes, label: 电解质, type: string, qwen_path: ["辅助检查", "电解质"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: aux_renal_function, label: 肾功, type: string, qwen_path: ["辅助检查", "肾功"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
      - {field_key: aux_d_dimer, label: D2聚体, type: string, qwen_path: ["辅助检查", "D2聚体"], qwen_type: J, review_control: judgement, options: ["正常", "异常", "未提及", "不确定"]}
  - group_key: diagnosis
    group_label: 诊断
    fields:
      - {field_key: diagnosis_initial, label: 初步诊断, type: string, qwen_path: ["初步诊断"], qwen_type: T, review_control: text}
      - {field_key: diagnosis_final, label: 最终诊断, type: string, qwen_path: ["最终诊断"], qwen_type: T, review_control: text}
```

- [ ] **Step 5: Run focused tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/schema_loader.py app/backend/tests/test_schema_loader.py app/config/schemas/qwen_batch_admission_record.v1.yaml
git commit -m "新增Qwen批处理字段Schema"
```

**Review Gate:** Spec reviewer checks fields align with upstream Chinese nested schema and do not re-expand old split fields. Quality reviewer checks schema metadata validation is explicit and backwards compatible.

---

### Task 4: Implement Pure Qwen Result Normalization

**Files:**
- Create: `algorithms/qwen_batch_engine/adapter/__init__.py`
- Create: `algorithms/qwen_batch_engine/adapter/normalize_result.py`
- Create: `app/backend/tests/test_qwen_batch_normalize_result.py`

- [ ] **Step 1: Write failing normalization tests**

Create `app/backend/tests/test_qwen_batch_normalize_result.py`:

```python
from pathlib import Path

from algorithms.qwen_batch_engine.adapter.normalize_result import (
    normalize_qwen_outputs,
    resolve_anchor_range,
)


def _schema():
    return {
        "version": "qwen_batch_admission_record.v1",
        "document_type": "qwen_batch_admission_record",
        "field_groups": [
            {
                "group_key": "chief_complaint",
                "group_label": "主诉",
                "fields": [
                    {
                        "field_key": "chief_complaint",
                        "label": "主诉",
                        "qwen_path": ["主诉"],
                        "qwen_type": "T",
                    }
                ],
            },
            {
                "group_key": "history_of_present_illness",
                "group_label": "现病史",
                "fields": [
                    {
                        "field_key": "hpi_mental_sleep_appetite",
                        "label": "精神睡眠食欲",
                        "qwen_path": ["现病史", "精神睡眠食欲"],
                        "qwen_type": "J",
                    },
                    {
                        "field_key": "hpi_urination",
                        "label": "小便情况",
                        "qwen_path": ["现病史", "小便情况"],
                        "qwen_type": "J",
                    },
                ],
            },
        ],
    }


def test_resolve_anchor_range_combines_offsets_and_text():
    anchors = {
        "<s1>": {"id": "s1", "text": "主诉：反复咳嗽。", "start_offset": 0, "end_offset": 9, "page_no": 1, "source_file": "page_001.jpg"},
        "<s2>": {"id": "s2", "text": "精神睡眠食欲差。", "start_offset": 9, "end_offset": 18, "page_no": 1, "source_file": "page_001.jpg"},
    }

    evidence = resolve_anchor_range(["<s1>", "<s2>"], anchors)

    assert evidence == {
        "id": "s1-s2",
        "text": "主诉：反复咳嗽。精神睡眠食欲差。",
        "start_offset": 0,
        "end_offset": 18,
        "page_no": 1,
        "source_file": "page_001.jpg",
        "anchor_start": "<s1>",
        "anchor_end": "<s2>",
    }


def test_normalize_compact_t_and_j_fields_to_candidates(tmp_path):
    structured = {
        "主诉": {"v": "反复咳嗽15年", "p": ["<s1>", "<s1>"]},
        "现病史": {
            "精神睡眠食欲": {"s": 1, "p": ["<s2>", "<s2>"]},
            "小便情况": {"s": 2, "p": None},
        },
    }
    anchors = {
        "<s1>": {"id": "s1", "text": "主诉：反复咳嗽15年。", "start_offset": 0, "end_offset": 13, "page_no": 1},
        "<s2>": {"id": "s2", "text": "精神睡眠食欲差。", "start_offset": 13, "end_offset": 22, "page_no": 1},
    }

    result = normalize_qwen_outputs(
        job_id="task_001",
        schema=_schema(),
        merged_text="主诉：反复咳嗽15年。精神睡眠食欲差。",
        pages=[{"page_id": "p1", "page_no": 1, "text": "主诉：反复咳嗽15年。精神睡眠食欲差。", "status": "success"}],
        structured=structured,
        anchors=anchors,
        engine={"name": "qwen_batch_engine", "upstream_commit": "a746ba9"},
    )

    fields = {item["field_key"]: item for item in result["review_fields"]}
    assert result["status"] == "success"
    assert result["schema_version"] == "qwen_batch_admission_record.v1"
    assert fields["chief_complaint"]["original_value"] == "反复咳嗽15年"
    assert fields["chief_complaint"]["qwen_type"] == "T"
    assert fields["chief_complaint"]["extraction_status"] == "extracted"
    assert fields["chief_complaint"]["evidence"][0]["start_offset"] == 0
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "异常"
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "abnormal"
    assert fields["hpi_mental_sleep_appetite"]["qwen_type"] == "J"
    assert fields["hpi_urination"]["original_value"] == ""
    assert fields["hpi_urination"]["qwen_status"] == "not_mentioned"
    assert fields["hpi_urination"]["extraction_status"] == "not_found"


def test_missing_anchor_marks_field_attention_without_inference():
    structured = {
        "主诉": {"v": "反复咳嗽15年", "p": ["<s404>", "<s404>"]},
        "现病史": {
            "精神睡眠食欲": {"s": 2, "p": None},
            "小便情况": {"s": 2, "p": None},
        },
    }

    result = normalize_qwen_outputs(
        job_id="task_001",
        schema=_schema(),
        merged_text="主诉：反复咳嗽15年。",
        pages=[{"page_id": "p1", "page_no": 1, "text": "主诉：反复咳嗽15年。", "status": "success"}],
        structured=structured,
        anchors={},
        engine={"name": "qwen_batch_engine"},
    )

    chief = next(item for item in result["review_fields"] if item["field_key"] == "chief_complaint")
    assert chief["original_value"] == "反复咳嗽15年"
    assert chief["evidence"] == []
    assert chief["attention_required"] is True
    assert chief["attention_message"] == "来源证据定位失败，请核对原文"
    assert "反复咳嗽15年。" not in chief["attention_message"]


def test_all_empty_qwen_fields_raise_contract_error():
    structured = {
        "主诉": {"v": None, "p": None},
        "现病史": {
            "精神睡眠食欲": {"s": 2, "p": None},
            "小便情况": {"s": 2, "p": None},
        },
    }

    result = normalize_qwen_outputs(
        job_id="task_001",
        schema=_schema(),
        merged_text="主诉：",
        pages=[{"page_id": "p1", "page_no": 1, "text": "主诉：", "status": "success"}],
        structured=structured,
        anchors={},
        engine={"name": "qwen_batch_engine"},
    )

    assert result["status"] == "failed"
    assert result["error"]["reason"] == "empty_field_results"
```

- [ ] **Step 2: Run test and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_normalize_result.py -q
```

Expected: FAIL because `normalize_result.py` does not exist.

- [ ] **Step 3: Implement `normalize_result.py`**

Implement these functions with pure dict/list logic:

```python
QWEN_J_STATUS_TO_VALUE = {
    0: ("normal", "正常"),
    1: ("abnormal", "异常"),
    2: ("not_mentioned", ""),
    "0": ("normal", "正常"),
    "1": ("abnormal", "异常"),
    "2": ("not_mentioned", ""),
    "正常": ("normal", "正常"),
    "异常": ("abnormal", "异常"),
    "未提及": ("not_mentioned", ""),
    "不确定": ("uncertain", "不确定"),
}
```

Required behavior:

- `iter_schema_fields(schema)` yields `(group, field)` in schema order.
- `get_by_path(structured, qwen_path)` walks Chinese nested keys.
- `resolve_anchor_range(position, anchors)` accepts `["<s3>", "<s5>"]`, sorts numeric ranges, requires all anchors to exist, concatenates text in range, returns `None` if invalid.
- T field:
  - value comes from compact `v` or restored `值`.
  - `None` or blank becomes `not_found`.
  - nonblank becomes `extracted`.
- J field:
  - status comes from compact `s` or restored `状态`.
  - `normal` maps to final value `正常`.
  - `abnormal` maps to final value `异常`.
  - `not_mentioned` maps to blank final value and `extraction_status=not_found`.
  - unknown status maps to `uncertain` and final value `不确定`.
- Each candidate includes:

```python
{
    "field_key": field_key,
    "field_label": label,
    "section_key": group_key,
    "section_label": group_label,
    "original_value": value,
    "evidence": evidence_list,
    "confidence": None,
    "extraction_status": "extracted" | "not_found" | "uncertain",
    "verification_status": "not_checked" | "suspicious",
    "attention_required": bool,
    "attention_message": str,
    "quality_flags": list,
    "source_section": group_label,
    "source_hint": " / ".join(qwen_path),
    "source_text": first_evidence_text_or_none,
    "source_group_id": group_key,
    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    "qwen_type": "T" | "J",
    "qwen_path": qwen_path,
    "qwen_status": "normal" | "abnormal" | "not_mentioned" | "uncertain" | None,
}
```

- `normalize_qwen_outputs(...)` returns standard result:

```python
{
    "job_id": job_id,
    "status": "success",
    "schema_version": schema["version"],
    "engine": engine,
    "document_result": {"merged_text": merged_text, "pages": pages},
    "structured_result": structured,
    "review_fields": candidates,
    "warnings": warnings,
}
```

- If merged text is blank, return `status=failed` and `error.reason="empty_ocr_text"`.
- If every candidate is blank/not-mentioned, return `status=failed` and `error.reason="empty_field_results"`.

- [ ] **Step 4: Run focused test**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_normalize_result.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add algorithms/qwen_batch_engine/adapter/__init__.py algorithms/qwen_batch_engine/adapter/normalize_result.py app/backend/tests/test_qwen_batch_normalize_result.py
git commit -m "实现Qwen批处理结果归一化"
```

**Review Gate:** Spec reviewer checks no medical inference or old-field remapping. Quality reviewer checks pure functions, deterministic mapping, and no sensitive logging.

---

### Task 5: Add Stable `run_job.py` Entry And Error Contract

**Files:**
- Create: `algorithms/qwen_batch_engine/adapter/run_job.py`
- Create: `app/backend/tests/test_qwen_batch_run_job.py`

- [ ] **Step 1: Write failing runner tests**

Create `app/backend/tests/test_qwen_batch_run_job.py`:

```python
import json
from pathlib import Path

from algorithms.qwen_batch_engine.adapter.run_job import run_job


def _write_schema(path: Path):
    path.write_text(
        """
version: qwen_batch_admission_record.v1
document_type: qwen_batch_admission_record
field_groups:
  - group_key: chief_complaint
    group_label: 主诉
    fields:
      - field_key: chief_complaint
        label: 主诉
        type: string
        qwen_path: ["主诉"]
        qwen_type: T
        review_control: text
""",
        encoding="utf-8",
    )


def _job_dir(tmp_path):
    job = tmp_path / "job"
    (job / "input").mkdir(parents=True)
    (job / "output").mkdir()
    (job / "input" / "page_001.jpg").write_bytes(b"fake-image")
    (job / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "task_001",
                "task_id": "task_001",
                "schema_version": "qwen_batch_admission_record.v1",
                "input_files": [
                    {
                        "page_id": "p1",
                        "page_no": 1,
                        "filename": "page_001.jpg",
                        "original_path": "/data/tasks/task_001/page_001.jpg",
                    }
                ],
                "engine": {
                    "name": "qwen_batch_engine",
                    "upstream_commit": "a746ba9",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return job


def test_run_job_normalize_only_writes_result_json(tmp_path):
    job = _job_dir(tmp_path)
    schema_path = tmp_path / "schema.yaml"
    _write_schema(schema_path)
    (job / "output" / "merged_ocr.txt").write_text("主诉：反复咳嗽15年。", encoding="utf-8")
    (job / "output" / "merged_structured.json").write_text(
        json.dumps({"主诉": {"v": "反复咳嗽15年", "p": ["<s1>", "<s1>"]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (job / "output" / "anchors.json").write_text(
        json.dumps({"<s1>": {"id": "s1", "text": "主诉：反复咳嗽15年。", "start_offset": 0, "end_offset": 13, "page_no": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = run_job(str(job), schema_path=str(schema_path), normalize_only=True)

    assert exit_code == 0
    result = json.loads((job / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["review_fields"][0]["field_key"] == "chief_complaint"
    assert not (job / "error.json").exists()


def test_run_job_writes_error_json_for_invalid_structured_json(tmp_path):
    job = _job_dir(tmp_path)
    schema_path = tmp_path / "schema.yaml"
    _write_schema(schema_path)
    (job / "output" / "merged_ocr.txt").write_text("主诉：反复咳嗽15年。", encoding="utf-8")
    (job / "output" / "merged_structured.json").write_text("{bad json", encoding="utf-8")
    (job / "output" / "anchors.json").write_text("{}", encoding="utf-8")

    exit_code = run_job(str(job), schema_path=str(schema_path), normalize_only=True)

    assert exit_code == 2
    error = json.loads((job / "error.json").read_text(encoding="utf-8"))
    assert error["status"] == "failed"
    assert error["reason"] == "invalid_structured_json"
    assert "主诉" not in json.dumps(error, ensure_ascii=False)


def test_run_job_rejects_manifest_without_input_files(tmp_path):
    job = tmp_path / "job"
    (job / "input").mkdir(parents=True)
    (job / "output").mkdir()
    (job / "manifest.json").write_text(
        json.dumps({"job_id": "task_001", "input_files": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    schema_path = tmp_path / "schema.yaml"
    _write_schema(schema_path)

    exit_code = run_job(str(job), schema_path=str(schema_path), normalize_only=True)

    assert exit_code == 2
    error = json.loads((job / "error.json").read_text(encoding="utf-8"))
    assert error["reason"] == "invalid_manifest"
```

- [ ] **Step 2: Run test and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_run_job.py -q
```

Expected: FAIL because `run_job.py` does not exist.

- [ ] **Step 3: Implement runner**

Implement `run_job.py` with:

- CLI args:

```text
--job-dir
--schema-path
--normalize-only
--upstream-command
--timeout-seconds
```

- `run_job(job_dir, schema_path, normalize_only=False, upstream_command=None, timeout_seconds=1800) -> int`
- `manifest.json` validation requires nonblank `job_id`, nonempty `input_files`, each file has `filename`, `page_id`, `page_no`.
- If `normalize_only` is false, call `subprocess.run(upstream_command, cwd=engine_root, timeout=timeout_seconds, check=False)`.
- If subprocess return code is nonzero, write `error.json` with `reason="upstream_failed"` and return `1`.
- Read only these output files:

```text
output/merged_ocr.txt
output/merged_structured.json
output/anchors.json
output/summary.json
```

- Write `result.json` on success and `error.json` on failure.
- Error JSON must include `job_id`, `status`, `reason`, `message`, `engine`, and no OCR text/full model output.
- `main()` exits with the `run_job` return code.

- [ ] **Step 4: Run focused test**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_run_job.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add algorithms/qwen_batch_engine/adapter/run_job.py app/backend/tests/test_qwen_batch_run_job.py
git commit -m "新增Qwen批处理稳定Job入口"
```

**Review Gate:** Spec reviewer checks `run_job.py --job-dir` is the stable entry and failures are explicit. Quality reviewer checks subprocess handling, timeout behavior, and privacy of `error.json`.

---

### Task 6: Add Backend Qwen Batch Adapter And Orchestrator

**Files:**
- Create: `app/backend/services/algorithm_ports/qwen_batch_adapter.py`
- Create: `app/backend/services/algorithm_ports/qwen_batch_orchestrator.py`
- Modify: `app/backend/services/algorithm_ports/results.py`
- Create: `app/backend/tests/test_qwen_batch_adapter.py`
- Create: `app/backend/tests/test_qwen_batch_orchestrator.py`

- [ ] **Step 1: Write failing adapter tests**

Create `app/backend/tests/test_qwen_batch_adapter.py`:

```python
import json
from pathlib import Path

from app.backend.services.algorithm_ports.qwen_batch_adapter import QwenBatchAlgorithmPort


def test_qwen_batch_adapter_creates_manifest_and_reads_result(tmp_path):
    job_root = tmp_path / "jobs"
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text("version: qwen_batch_admission_record.v1\ndocument_type: qwen_batch_admission_record\nfield_groups: []\n", encoding="utf-8")
    source = tmp_path / "page.jpg"
    source.write_bytes(b"image")

    def fake_runner(job_dir: str, schema_path: str, timeout_seconds: int):
        job = Path(job_dir)
        result = {
            "job_id": "task_001",
            "status": "success",
            "engine": {"name": "qwen_batch_engine"},
            "document_result": {
                "merged_text": "主诉：咳嗽",
                "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}],
            },
            "review_fields": [
                {
                    "field_key": "chief_complaint",
                    "original_value": "咳嗽",
                    "evidence": [{"id": "s1-s1", "text": "主诉：咳嗽", "start_offset": 0, "end_offset": 5}],
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                }
            ],
            "warnings": [],
        }
        (job / "result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return 0

    port = QwenBatchAlgorithmPort(
        job_root=str(job_root),
        schema_path=str(schema_path),
        runner=fake_runner,
        timeout_seconds=30,
    )

    result = port.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(source)}],
            "schema_version": "qwen_batch_admission_record.v1",
        }
    )

    manifest = json.loads((job_root / "task_001" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["job_id"] == "task_001"
    assert manifest["input_files"][0]["filename"] == "page_001.jpg"
    assert (job_root / "task_001" / "input" / "page_001.jpg").read_bytes() == b"image"
    assert result["status"] == "success"
    assert result["review_fields"][0]["field_key"] == "chief_complaint"


def test_qwen_batch_adapter_returns_failed_result_when_runner_fails(tmp_path):
    source = tmp_path / "page.jpg"
    source.write_bytes(b"image")
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text("version: qwen_batch_admission_record.v1\n", encoding="utf-8")

    def failing_runner(job_dir: str, schema_path: str, timeout_seconds: int):
        Path(job_dir, "error.json").write_text(
            json.dumps({"status": "failed", "reason": "upstream_failed", "message": "runner failed"}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 1

    port = QwenBatchAlgorithmPort(
        job_root=str(tmp_path / "jobs"),
        schema_path=str(schema_path),
        runner=failing_runner,
        timeout_seconds=30,
    )

    result = port.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(source)}],
            "schema_version": "qwen_batch_admission_record.v1",
        }
    )

    assert result["status"] == "failed"
    assert result["error"]["reason"] == "upstream_failed"
```

- [ ] **Step 2: Write failing orchestrator tests**

Create `app/backend/tests/test_qwen_batch_orchestrator.py`:

```python
from app.backend.services.algorithm_ports.qwen_batch_orchestrator import QwenBatchProcessingOrchestrator
from app.backend.storage.json_store import JsonStore


class TaskService:
    def __init__(self):
        self.failed = None
        self.ready = False
        self.stages = []

    def mark_processing_stage(self, task_id, stage, status, page_count=None):
        self.stages.append((stage, status, page_count))

    def mark_ready(self, task_id):
        self.ready = True
        return {"task_id": task_id, "status": "review"}

    def mark_failed(self, task_id, code, message, stage=None, details=None):
        self.failed = {"code": code, "message": message, "stage": stage, "details": details}
        return {"task_id": task_id, "status": "failed", "error_code": code}

    def is_processing_cancelled(self, task_id):
        return False


def _candidate():
    return {
        "field_key": "chief_complaint",
        "original_value": "咳嗽",
        "evidence": [{"id": "s1-s1", "text": "主诉：咳嗽", "start_offset": 0, "end_offset": 5}],
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    }


def test_qwen_batch_orchestrator_persists_document_and_fields(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {
                "status": "success",
                "document_result": {
                    "merged_text": "主诉：咳嗽",
                    "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}],
                },
                "review_fields": [_candidate()],
            }

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run(
        {"task_id": "task_001", "images": [{"page_id": "p1", "page_no": 1, "original_image_path": "/tmp/p1.jpg"}]},
        service,
        schema={"version": "qwen_batch_admission_record.v1"},
    )

    assert result["status"] == "review"
    assert store.read("results/task_001/document_result.json")["merged_text"] == "主诉：咳嗽"
    assert store.read("results/task_001/field_candidates.json")["candidates"][0]["field_key"] == "chief_complaint"


def test_qwen_batch_orchestrator_marks_failed_for_empty_ocr(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {
                "status": "success",
                "document_result": {"merged_text": "", "pages": []},
                "review_fields": [_candidate()],
            }

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run({"task_id": "task_001", "images": []}, service, schema={})

    assert result["status"] == "failed"
    assert service.failed["details"]["reason"] == "empty_ocr_text"


def test_qwen_batch_orchestrator_marks_failed_for_batch_error(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {"status": "failed", "error": {"reason": "upstream_failed", "message": "runner failed"}}

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run({"task_id": "task_001", "images": []}, service, schema={})

    assert result["status"] == "failed"
    assert service.failed["details"]["reason"] == "upstream_failed"
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_adapter.py app/backend/tests/test_qwen_batch_orchestrator.py -q
```

Expected: FAIL because adapter and orchestrator do not exist.

- [ ] **Step 4: Implement backend adapter**

`QwenBatchAlgorithmPort` requirements:

- Constructor args: `job_root`, `schema_path`, `runner`, `timeout_seconds`, `engine_root=None`.
- `run(task: dict) -> dict`
- Create `data/algorithm_jobs/{task_id}/input` and `output`.
- Copy task images sorted by `page_no` to `input/page_001.ext`, `input/page_002.ext`.
- Write `manifest.json` exactly with:

```python
{
    "job_id": task_id,
    "task_id": task_id,
    "schema_version": task.get("schema_version"),
    "created_at": datetime.now(timezone.utc).isoformat(),
    "input_files": [
        {
            "page_id": page_id,
            "page_no": page_no,
            "filename": filename,
            "original_path": original_path,
        }
    ],
    "engine": {
        "name": "qwen_batch_engine",
        "upstream_commit": read_upstream_commit_from_version(),
    },
}
```

- Default runner calls `python algorithms/qwen_batch_engine/adapter/run_job.py --job-dir <job_dir> --schema-path <schema_path> --timeout-seconds <timeout>`.
- If runner returns nonzero, read `error.json` and return `{"status": "failed", "error": error}`.
- If `result.json` missing or invalid, return failed with `reason="missing_result_json"` or `reason="invalid_result_json"`.

- [ ] **Step 5: Implement batch orchestrator**

`QwenBatchProcessingOrchestrator.run(task, task_service, schema)` requirements:

- If cancelled, return `task_service.get_task(task_id)` when available.
- Mark processing stage `qwen_batch_engine` running.
- Hold GPU stage `qwen_batch_engine` if queue injected.
- Call batch port.
- On failed result, mark task failed with `ErrorCode.ALGORITHM_MODULE_FAILED.code`.
- On blank `document_result.merged_text`, mark failed with `reason="empty_ocr_text"`.
- On non-list or empty `review_fields`, mark failed with `reason="empty_field_results"`.
- Validate candidates with `validate_field_candidates`.
- Validate schema through injected validator.
- Persist document result through `AlgorithmResultStore.write_document_result`.
- Persist candidates through `AlgorithmResultStore.write_field_candidates`.
- Return `task_service.mark_ready(task_id)`.

Add `AlgorithmResultStore.write_qwen_batch_result(task_id, result)` only if needed for raw audit. If added, store it at `results/{task_id}/qwen_batch_result.json` and ensure ordinary logs do not include OCR text.

- [ ] **Step 6: Run focused tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_adapter.py app/backend/tests/test_qwen_batch_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/algorithm_ports/qwen_batch_adapter.py app/backend/services/algorithm_ports/qwen_batch_orchestrator.py app/backend/services/algorithm_ports/results.py app/backend/tests/test_qwen_batch_adapter.py app/backend/tests/test_qwen_batch_orchestrator.py
git commit -m "接入Qwen批处理后端端口"
```

**Review Gate:** Spec reviewer checks backend does not import upstream internals and batch failures mark task failed. Quality reviewer checks adapter/orchestrator split, copy semantics, and no sensitive logs.

---

### Task 7: Add Disabled-By-Default Config And App Factory Integration

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/services/document_profiles.py`
- Modify: `app/backend/tests/test_config.py`
- Modify: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Add failing config tests**

Append to `app/backend/tests/test_config.py`:

```python
def test_load_config_defaults_to_legacy_algorithm_engine(tmp_path):
    from app.backend.config import load_config

    config = load_config(str(tmp_path / "nonexistent"))

    assert config["algorithm_engine"] == "legacy"
    assert config["qwen_batch_job_dir"].endswith("data/algorithm_jobs")
    assert config["qwen_batch_runner_timeout_seconds"] == 1800


def test_load_config_supports_qwen_batch_algorithm_engine(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  algorithm_engine: qwen_batch
  qwen_batch_runner_timeout_seconds: 600
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["algorithm_engine"] == "qwen_batch"
    assert config["qwen_batch_runner_timeout_seconds"] == 600


def test_algorithm_engine_rejects_unknown_value(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "algorithms:\n  algorithm_engine: unknown\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="algorithm_engine"):
        load_config(str(config_dir))
```

- [ ] **Step 2: Run config tests and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_defaults_to_legacy_algorithm_engine app/backend/tests/test_config.py::test_load_config_supports_qwen_batch_algorithm_engine app/backend/tests/test_config.py::test_algorithm_engine_rejects_unknown_value -q
```

Expected: FAIL because new config keys do not exist.

- [ ] **Step 3: Implement config keys**

Add to `DEFAULT_CONFIG`:

```python
"algorithm_engine": "legacy",
"qwen_batch_job_dir": "./data/algorithm_jobs",
"qwen_batch_runner_timeout_seconds": 1800,
"qwen_batch_schema_path": "./app/config/schemas/qwen_batch_admission_record.v1.yaml",
```

In `_flatten_config`, read these from `algorithms`:

```python
    if "algorithm_engine" in algorithms_config:
        flattened["algorithm_engine"] = algorithms_config["algorithm_engine"]
    if "qwen_batch_job_dir" in algorithms_config:
        flattened["qwen_batch_job_dir"] = algorithms_config["qwen_batch_job_dir"]
    if "qwen_batch_runner_timeout_seconds" in algorithms_config:
        flattened["qwen_batch_runner_timeout_seconds"] = algorithms_config["qwen_batch_runner_timeout_seconds"]
    if "qwen_batch_schema_path" in algorithms_config:
        flattened["qwen_batch_schema_path"] = algorithms_config["qwen_batch_schema_path"]
```

In `_normalize_paths`, include:

```python
"qwen_batch_job_dir",
"qwen_batch_schema_path",
```

In `_validate_config`, validate:

```python
    algorithm_engine = config.get("algorithm_engine")
    if algorithm_engine not in {"legacy", "qwen_batch"}:
        raise ValueError(f"algorithm_engine 必须是 legacy 或 qwen_batch，当前值: {algorithm_engine}")

    qwen_batch_timeout = config.get("qwen_batch_runner_timeout_seconds")
    if not isinstance(qwen_batch_timeout, int) or isinstance(qwen_batch_timeout, bool) or qwen_batch_timeout <= 0:
        raise ValueError(f"qwen_batch_runner_timeout_seconds 必须为正整数，当前值: {qwen_batch_timeout}")
```

Add safe defaults to `app/config/default.yaml`:

```yaml
algorithms:
  algorithm_engine: legacy
  qwen_batch_job_dir: "./data/algorithm_jobs"
  qwen_batch_runner_timeout_seconds: 1800
  qwen_batch_schema_path: "./app/config/schemas/qwen_batch_admission_record.v1.yaml"
```

- [ ] **Step 4: Modify document profile availability**

In `app/backend/services/document_profiles.py`, extend `DocumentProfile`:

```python
    algorithm_engine: str = "legacy"
```

Change `is_available`:

```python
    @property
    def is_available(self) -> bool:
        if self.algorithm_engine == "qwen_batch":
            return bool(self.document_type and self.label and self.schema_version and self.prompt_version)
        return bool(self.document_type and self.label and self.schema_version and self.prompt_version and self.field_port is not None)
```

- [ ] **Step 5: Integrate app factory behind config flag**

In `app/backend/__init__.py`:

- Load both schemas:

```python
legacy_schema_path = os.path.join(PROJECT_ROOT, "app", "config", "schemas", "admission_record_structured_fields.v1.yaml")
qwen_batch_schema_path = config["qwen_batch_schema_path"]
schema_path = qwen_batch_schema_path if config["algorithm_engine"] == "qwen_batch" else legacy_schema_path
schema_service = SchemaService(schema_path)
```

- If `algorithm_engine == "qwen_batch"`, create:

```python
from .services.algorithm_ports.qwen_batch_adapter import QwenBatchAlgorithmPort
from .services.algorithm_ports.qwen_batch_orchestrator import QwenBatchProcessingOrchestrator

batch_port = QwenBatchAlgorithmPort(
    job_root=config["qwen_batch_job_dir"],
    schema_path=config["qwen_batch_schema_path"],
    timeout_seconds=int(config["qwen_batch_runner_timeout_seconds"]),
)
orchestrator = QwenBatchProcessingOrchestrator(
    store=store,
    batch_port=batch_port,
    schema_validator=schema_service.build_validator(),
    gpu_stage_queue=gpu_stage_queue,
)
```

- Else keep existing legacy orchestrator construction unchanged.
- Register profile:

```python
DocumentProfile(
    document_type=schema_service.get_current()["document_type"],
    label="入院记录",
    schema=schema_service.get_current(),
    prompt_version="qwen_batch_prompt.v1" if config["algorithm_engine"] == "qwen_batch" else ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION,
    field_port=field_port,
    quality_rule_profile="qwen_batch_admission_record" if config["algorithm_engine"] == "qwen_batch" else "copd_admission_record",
    algorithm_engine=config["algorithm_engine"],
)
```

- Use default document type from the selected schema.

- [ ] **Step 6: Add e2e app factory smoke test**

Add to `app/backend/tests/test_backend_e2e.py`:

```python
def test_create_backend_app_with_qwen_batch_engine_config(tmp_path):
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    export_dir = tmp_path / "exports"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
server:
  port: 18081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
algorithms:
  algorithm_engine: qwen_batch
  qwen_batch_job_dir: "{tmp_path / "jobs"}"
  qwen_batch_schema_path: "./app/config/schemas/qwen_batch_admission_record.v1.yaml"
""",
        encoding="utf-8",
    )

    app = create_backend_app(str(config_dir))

    config = app.config["BACKEND_CONFIG"]
    assert config["algorithm_engine"] == "qwen_batch"
    schema = app.config["SCHEMA_SERVICE"].get_current()
    assert schema["version"] == "qwen_batch_admission_record.v1"
    assert app.config["DOCUMENT_PROFILE_REGISTRY"].get_default_document_type() == "qwen_batch_admission_record"
```

- [ ] **Step 7: Run focused tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py app/backend/tests/test_backend_e2e.py::test_create_backend_app_with_qwen_batch_engine_config -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/backend/config.py app/config/default.yaml app/backend/__init__.py app/backend/services/document_profiles.py app/backend/tests/test_config.py app/backend/tests/test_backend_e2e.py
git commit -m "增加Qwen批处理引擎配置开关"
```

**Review Gate:** Spec reviewer checks new engine is disabled by default and rollback remains config-driven. Quality reviewer checks app factory branching is explicit and does not break legacy path.

---

### Task 8: Preserve Qwen Metadata In Review Results

**Files:**
- Modify: `app/backend/services/_review_field_factory.py`
- Modify: `app/backend/services/review_service.py`
- Modify: `app/backend/tests/test_review_service.py`

- [ ] **Step 1: Add failing review metadata tests**

Append to `app/backend/tests/test_review_service.py`:

```python
def test_review_field_preserves_qwen_metadata_from_candidate():
    candidate = {
        "field_key": "hpi_mental_sleep_appetite",
        "original_value": "异常",
        "evidence": [{"id": "s2-s2", "text": "精神睡眠食欲差。", "start_offset": 10, "end_offset": 19}],
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
        "qwen_type": "J",
        "qwen_path": ["现病史", "精神睡眠食欲"],
        "qwen_status": "abnormal",
    }

    field = build_field_from_candidate("hpi_mental_sleep_appetite", "精神睡眠食欲", candidate)

    assert field["qwen_type"] == "J"
    assert field["qwen_path"] == ["现病史", "精神睡眠食欲"]
    assert field["qwen_status"] == "abnormal"
    assert field["final_value"] == "异常"


def test_review_hydrates_qwen_metadata_from_schema_for_existing_fields(tmp_path):
    store = JsonStore(str(tmp_path))

    class _TaskSvc:
        def get_task(self, task_id):
            return {"task_id": task_id, "status": "review", "schema_version": "qwen_batch_admission_record.v1", "document_type": "qwen_batch_admission_record"}

        def update_review_summary(self, task_id, summary):
            store.write(f"tasks/{task_id}.json", {"task_id": task_id, "status": "review", "review_summary": summary})

    schema = {
        "version": "qwen_batch_admission_record.v1",
        "document_type": "qwen_batch_admission_record",
        "field_groups": [
            {
                "group_key": "history_of_present_illness",
                "group_label": "现病史",
                "fields": [
                    {
                        "field_key": "hpi_mental_sleep_appetite",
                        "label": "精神睡眠食欲",
                        "qwen_type": "J",
                        "qwen_path": ["现病史", "精神睡眠食欲"],
                        "review_control": "judgement",
                        "options": ["正常", "异常", "未提及", "不确定"],
                    }
                ],
            }
        ],
    }
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "fields": [
                {
                    "field_key": "hpi_mental_sleep_appetite",
                    "field_name": "精神睡眠食欲",
                    "auto_value": "异常",
                    "final_value": "异常",
                    "status": "unreviewed",
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                    "history": [],
                }
            ],
        },
    )

    service = ReviewService(store, _TaskSvc(), schema_provider=lambda: schema)
    review = service.get_or_init("task_001")
    field = review["fields"][0]

    assert field["qwen_type"] == "J"
    assert field["qwen_path"] == ["现病史", "精神睡眠食欲"]
    assert review["field_groups"][0]["fields"][0]["qwen_type"] == "J"
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py::test_review_field_preserves_qwen_metadata_from_candidate app/backend/tests/test_review_service.py::test_review_hydrates_qwen_metadata_from_schema_for_existing_fields -q
```

Expected: FAIL because Qwen metadata is not preserved.

- [ ] **Step 3: Preserve metadata in review field factory**

In `app/backend/services/_review_field_factory.py`, add:

```python
QWEN_REVIEW_METADATA_KEYS = ("qwen_type", "qwen_path", "qwen_status", "review_control", "options")


def _copy_qwen_metadata(source: dict) -> dict:
    metadata = {}
    for key in QWEN_REVIEW_METADATA_KEYS:
        if key in source:
            metadata[key] = copy.deepcopy(source[key])
    return metadata
```

Update both `build_placeholder_field` and `build_field_from_candidate`:

- `build_placeholder_field(..., metadata: dict | None = None)`
- Merge `_copy_qwen_metadata(metadata or {})` into the returned field.
- Merge `_copy_qwen_metadata(candidate)` into extracted fields.

- [ ] **Step 4: Hydrate metadata from schema**

In `ReviewService`, change `_iter_schema_field_keys` to yield `(field_key, label, schema_field)`. When hydrating existing fields:

```python
for meta_key in ("qwen_type", "qwen_path", "review_control", "options"):
    if meta_key in schema_field and field.get(meta_key) != schema_field[meta_key]:
        field[meta_key] = schema_field[meta_key]
        mutated = True
```

When building placeholders:

```python
field = build_placeholder_field(fk, label, metadata=schema_field)
```

When building fields from candidates, after candidate sorting, merge schema metadata into candidates before `build_field_from_candidate`.

- [ ] **Step 5: Run focused tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/_review_field_factory.py app/backend/services/review_service.py app/backend/tests/test_review_service.py
git commit -m "保留Qwen审核字段元数据"
```

**Review Gate:** Spec reviewer checks frontend receives schema-driven Qwen metadata and no field inference occurs. Quality reviewer checks metadata propagation is centralized and backwards compatible.

---

### Task 9: Export Qwen Field Metadata And J Status

**Files:**
- Modify: `app/backend/services/export_service.py`
- Modify: `app/backend/tests/test_export_service.py`

- [ ] **Step 1: Add failing export tests**

Append to `app/backend/tests/test_export_service.py`:

```python
def test_export_json_includes_qwen_metadata_for_t_and_j_fields(tmp_path):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "field_groups": [
                {
                    "group_key": "history_of_present_illness",
                    "group_label": "现病史",
                    "fields": [
                        {"field_key": "hpi_mental_sleep_appetite", "label": "精神睡眠食欲", "qwen_type": "J", "qwen_path": ["现病史", "精神睡眠食欲"]},
                        {"field_key": "hpi_stool", "label": "大便情况", "qwen_type": "T", "qwen_path": ["现病史", "大便情况"]},
                    ],
                }
            ],
        },
    )
    write_task(store, status="done")
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "fields": [
                {
                    "field_key": "hpi_mental_sleep_appetite",
                    "field_name": "精神睡眠食欲",
                    "final_value": "异常",
                    "status": FieldStatus.CONFIRMED.value,
                    "qwen_type": "J",
                    "qwen_path": ["现病史", "精神睡眠食欲"],
                    "qwen_status": "abnormal",
                    "evidence": [{"id": "s1-s1", "text": "精神睡眠食欲差。", "start_offset": 0, "end_offset": 9, "anchor_start": "<s1>", "anchor_end": "<s1>"}],
                },
                {
                    "field_key": "hpi_stool",
                    "field_name": "大便情况",
                    "final_value": "大便正常",
                    "status": FieldStatus.CONFIRMED.value,
                    "qwen_type": "T",
                    "qwen_path": ["现病史", "大便情况"],
                    "evidence": [{"id": "s2-s2", "text": "大便正常。", "start_offset": 9, "end_offset": 14}],
                },
            ],
        },
    )

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        exported = json.load(f)
    fields = {field["field_key"]: field for field in exported["fields"]}
    assert fields["hpi_mental_sleep_appetite"]["qwen_type"] == "J"
    assert fields["hpi_mental_sleep_appetite"]["qwen_path"] == ["现病史", "精神睡眠食欲"]
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "abnormal"
    assert fields["hpi_mental_sleep_appetite"]["final_value"] == "异常"
    assert fields["hpi_mental_sleep_appetite"]["evidence"][0]["anchor_start"] == "<s1>"
    assert fields["hpi_stool"]["qwen_type"] == "T"


def test_export_excel_contains_qwen_type_column(tmp_path):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "field_groups": [
                {
                    "group_key": "history_of_present_illness",
                    "group_label": "现病史",
                    "fields": [{"field_key": "hpi_mental_sleep_appetite", "label": "精神睡眠食欲", "qwen_type": "J", "qwen_path": ["现病史", "精神睡眠食欲"]}],
                }
            ],
        },
    )
    write_task(store, status="done")
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "qwen_batch_admission_record.v1",
            "document_type": "qwen_batch_admission_record",
            "fields": [
                {
                    "field_key": "hpi_mental_sleep_appetite",
                    "field_name": "精神睡眠食欲",
                    "final_value": "异常",
                    "status": FieldStatus.CONFIRMED.value,
                    "qwen_type": "J",
                    "qwen_path": ["现病史", "精神睡眠食欲"],
                    "qwen_status": "abnormal",
                    "evidence": [],
                }
            ],
        },
    )

    info = export_service.export_excel("task_001")

    with zipfile.ZipFile(info["path"]) as archive:
        sheet1_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "字段类型" in sheet1_xml
    assert "Qwen路径" in sheet1_xml
    assert "J" in sheet1_xml
    assert "现病史 / 精神睡眠食欲" in sheet1_xml
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py::test_export_json_includes_qwen_metadata_for_t_and_j_fields app/backend/tests/test_export_service.py::test_export_excel_contains_qwen_type_column -q
```

Expected: FAIL because export model omits Qwen metadata.

- [ ] **Step 3: Modify export model**

In `_build_export_model`, include these keys per field:

```python
"qwen_type": f.get("qwen_type"),
"qwen_path": list(f.get("qwen_path") or []),
"qwen_status": f.get("qwen_status"),
"review_control": f.get("review_control"),
```

In `_build_schema_view`, hydrate missing metadata from `schema_field` into the view:

```python
for meta_key in ("qwen_type", "qwen_path", "review_control", "options"):
    if meta_key in schema_field and meta_key not in field:
        field = {**field, meta_key: schema_field[meta_key]}
```

Update XLSX headers:

```python
_HEADERS = ["字段 key", "字段名", "字段类型", "Qwen路径", "final_value", "状态", "来源页", "来源证据"]
_COL_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H"]
```

Update row writer values to include:

```python
f.get("qwen_type") or "",
" / ".join(f.get("qwen_path") or []),
```

- [ ] **Step 4: Run focused export tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "导出Qwen字段元数据"
```

**Review Gate:** Spec reviewer checks export follows Qwen schema and does not revive old field mapping. Quality reviewer checks XLSX changes are compatible with existing export tests.

---

### Task 10: Add Frontend Qwen Types And J-Field Controls

**Files:**
- Modify: `app/frontend/src/api/review.ts`
- Modify: `app/frontend/src/components/review/FieldList.tsx`
- Modify: `app/frontend/src/components/review/FieldList.test.tsx`
- Modify: `app/frontend/src/pages/review/review.css`

- [ ] **Step 1: Add failing frontend tests**

Append to `app/frontend/src/components/review/FieldList.test.tsx`:

```tsx
it('renders_qwen_j_field_as_status_segmented_control', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onFocus = vi.fn();
  const onToggle = vi.fn();
  const groups: FieldGroupDef[] = [
    {
      group_key: 'history_of_present_illness',
      group_label: '现病史',
      fields: [
        {
          field_key: 'hpi_mental_sleep_appetite',
          label: '精神睡眠食欲',
          qwen_type: 'J',
          qwen_path: ['现病史', '精神睡眠食欲']
        }
      ]
    }
  ];

  render(
    <FieldList
      fields={[makeField({
        field_key: 'hpi_mental_sleep_appetite',
        field_name: '精神睡眠食欲',
        label: '精神睡眠食欲',
        value: '异常',
        final_value: '异常',
        qwen_type: 'J',
        qwen_status: 'abnormal',
        qwen_path: ['现病史', '精神睡眠食欲']
      })]}
      fieldGroups={groups}
      selectedFieldKey={null}
      onChange={onChange}
      onFocusField={onFocus}
      onToggleReviewed={onToggle}
    />
  );

  expect(screen.queryByLabelText('hpi_mental_sleep_appetite')).toBeNull();
  expect(screen.getByRole('button', { name: '正常 精神睡眠食欲' })).toBeTruthy();
  expect(screen.getByRole('button', { name: '异常 精神睡眠食欲' }).getAttribute('aria-pressed')).toBe('true');

  await user.click(screen.getByRole('button', { name: '正常 精神睡眠食欲' }));

  expect(onChange).toHaveBeenCalledWith([
    expect.objectContaining({
      field_key: 'hpi_mental_sleep_appetite',
      final_value: '正常',
      value: '正常',
      qwen_status: 'normal',
      status: 'modified'
    })
  ]);
});

it('disables_qwen_j_control_when_read_only', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const onFocus = vi.fn();
  const onToggle = vi.fn();

  render(
    <FieldList
      fields={[makeField({
        field_key: 'pe_skin',
        field_name: '皮肤',
        label: '皮肤',
        value: '正常',
        final_value: '正常',
        qwen_type: 'J',
        qwen_status: 'normal'
      })]}
      fieldGroups={[{ group_key: 'physical_exam', group_label: '体格检查', fields: [{ field_key: 'pe_skin', label: '皮肤', qwen_type: 'J' }] }]}
      selectedFieldKey={null}
      onChange={onChange}
      onFocusField={onFocus}
      onToggleReviewed={onToggle}
      readOnly
    />
  );

  const normal = screen.getByRole('button', { name: '正常 皮肤' }) as HTMLButtonElement;
  expect(normal.disabled).toBe(true);
  await user.click(normal);
  expect(onChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests and confirm failure**

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/components/review/FieldList.test.tsx
```

Expected: FAIL because `qwen_type` is not typed and J controls are not rendered.

- [ ] **Step 3: Update frontend review types**

In `app/frontend/src/api/review.ts`:

```ts
export type QwenFieldType = 'T' | 'J';
export type QwenJudgementStatus = 'normal' | 'abnormal' | 'not_mentioned' | 'uncertain';
```

Extend `ReviewField`:

```ts
qwen_type?: QwenFieldType;
qwen_path?: string[];
qwen_status?: QwenJudgementStatus;
review_control?: 'text' | 'judgement';
options?: string[];
```

Extend `FieldGroupDef.fields`:

```ts
Array<{
  field_key: string;
  label: string;
  qwen_type?: QwenFieldType;
  qwen_path?: string[];
  review_control?: 'text' | 'judgement';
  options?: string[];
}>
```

In `normalizeReviewField`, keep `qwen_type`, `qwen_path`, `qwen_status`, `review_control`, and `options` as returned. Do not infer them from label text.

- [ ] **Step 4: Implement J segmented control**

In `FieldList.tsx`, define:

```ts
const QWEN_J_OPTIONS = [
  { value: '正常', status: 'normal', label: '正常' },
  { value: '异常', status: 'abnormal', label: '异常' },
  { value: '', status: 'not_mentioned', label: '未提及' },
  { value: '不确定', status: 'uncertain', label: '不确定' },
] as const;
```

Add helper:

```ts
function getQwenStatusFromValue(value: string): ReviewField['qwen_status'] {
  if (value === '正常') return 'normal';
  if (value === '异常') return 'abnormal';
  if (value === '不确定') return 'uncertain';
  if (value === '') return 'not_mentioned';
  return 'uncertain';
}
```

Add `updateQwenJudgementField(fieldKey, value, qwenStatus)`:

```ts
function updateQwenJudgementField(fieldKey: string, value: string, qwenStatus: NonNullable<ReviewField['qwen_status']>) {
  onChange(
    fields.map((f) =>
      f.field_key === fieldKey
        ? {
            ...f,
            value,
            final_value: value,
            qwen_status: qwenStatus,
            extraction_status: qwenStatus === 'not_mentioned' ? 'not_found' : f.extraction_status,
            status: value === (f.final_value ?? f.auto_value ?? '') ? f.status : ('modified' as const),
          }
        : f,
    ),
  );
}
```

Render J fields with a segmented control instead of `AutoGrowTextarea`:

```tsx
{field.qwen_type === 'J' || field.review_control === 'judgement' ? (
  <div className="field-card__judgement" role="group" aria-label={`${fieldLabel} 状态`}>
    {QWEN_J_OPTIONS.map((option) => {
      const currentStatus = field.qwen_status ?? getQwenStatusFromValue(value);
      const pressed = currentStatus === option.status;
      return (
        <button
          key={option.status}
          type="button"
          className="field-card__judgement-option"
          aria-label={`${option.label} ${fieldLabel}`}
          aria-pressed={pressed}
          disabled={readOnly}
          onClick={(event) => {
            event.stopPropagation();
            onFocusField(field);
            updateQwenJudgementField(field.field_key, option.value, option.status);
          }}
        >
          {option.label}
        </button>
      );
    })}
  </div>
) : (
  <AutoGrowTextarea ... />
)}
```

- [ ] **Step 5: Add CSS**

In `review.css`, add:

```css
.field-card__judgement {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
  width: 100%;
}

.field-card__judgement-option {
  min-height: 34px;
  border: 1px solid #d6e1f0;
  border-radius: 6px;
  background: #ffffff;
  color: #244263;
  font: inherit;
  cursor: pointer;
}

.field-card__judgement-option[aria-pressed="true"] {
  border-color: #8db7ff;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}

.field-card__judgement-option:disabled {
  cursor: not-allowed;
  opacity: 0.64;
}

@media (max-width: 520px) {
  .field-card__judgement {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
```

- [ ] **Step 6: Run focused frontend tests**

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/components/review/FieldList.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Run typecheck**

```bash
npm --prefix app/frontend run typecheck
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src/api/review.ts app/frontend/src/components/review/FieldList.tsx app/frontend/src/components/review/FieldList.test.tsx app/frontend/src/pages/review/review.css
git commit -m "前端支持Qwen判断字段审核"
```

**Review Gate:** Spec reviewer checks J controls are schema-driven and no frontend inference from OCR text occurs. Quality reviewer checks mobile layout, accessibility labels, and no text overflow.

---

### Task 11: Add Review Page Evidence And Qwen Fixture Coverage

**Files:**
- Modify: `app/frontend/src/pages/review/demoReviewSample.ts`
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify: `app/frontend/src/api/shared-contracts.test.ts`

- [ ] **Step 1: Add failing ReviewPage fixture test**

Append to `app/frontend/src/pages/review/ReviewPage.test.tsx`:

```tsx
it('loads_qwen_batch_fields_and_highlights_anchor_evidence', async () => {
  const payload = {
    task_id: 'task_qwen',
    status: 'review' as const,
    review_result: {
      ocr_text: '主诉：反复咳嗽15年。精神睡眠食欲差。',
      pages: [{ page_id: 'p1', page_no: 1, parsed_text: '主诉：反复咳嗽15年。精神睡眠食欲差。' }],
      field_groups: [
        {
          group_key: 'chief_complaint',
          group_label: '主诉',
          fields: [{ field_key: 'chief_complaint', label: '主诉', qwen_type: 'T', qwen_path: ['主诉'] }]
        },
        {
          group_key: 'history_of_present_illness',
          group_label: '现病史',
          fields: [{ field_key: 'hpi_mental_sleep_appetite', label: '精神睡眠食欲', qwen_type: 'J', qwen_path: ['现病史', '精神睡眠食欲'] }]
        }
      ],
      fields: [
        {
          field_key: 'chief_complaint',
          field_name: '主诉',
          label: '主诉',
          value: '反复咳嗽15年',
          final_value: '反复咳嗽15年',
          status: 'unreviewed' as const,
          qwen_type: 'T' as const,
          qwen_path: ['主诉'],
          evidence: [{ id: 's1-s1', text: '主诉：反复咳嗽15年。', start_offset: 0, end_offset: 13, anchor_start: '<s1>', anchor_end: '<s1>' }]
        },
        {
          field_key: 'hpi_mental_sleep_appetite',
          field_name: '精神睡眠食欲',
          label: '精神睡眠食欲',
          value: '异常',
          final_value: '异常',
          status: 'unreviewed' as const,
          qwen_type: 'J' as const,
          qwen_status: 'abnormal' as const,
          qwen_path: ['现病史', '精神睡眠食欲'],
          evidence: [{ id: 's2-s2', text: '精神睡眠食欲差。', start_offset: 13, end_offset: 22, anchor_start: '<s2>', anchor_end: '<s2>' }]
        }
      ]
    }
  };

  render(<ReviewPage taskId="task_qwen" demoPayload={payload} />);

  expect(await screen.findByText('现病史')).toBeTruthy();
  expect(screen.getByRole('button', { name: '异常 精神睡眠食欲' }).getAttribute('aria-pressed')).toBe('true');
  await userEvent.click(screen.getByTestId('review-field-card-hpi_mental_sleep_appetite'));
  expect(screen.getByText('点击字段可定位原文')).toBeTruthy();
  const mark = document.querySelector('mark');
  expect(mark?.textContent).toBe('精神睡眠食欲差。');
});
```

- [ ] **Step 2: Add shared contract type test**

Append to `app/frontend/src/api/shared-contracts.test.ts`:

```ts
it('normalizes_review_payload_with_qwen_metadata', () => {
  const payload = {
    task_id: 'task_qwen',
    status: 'review',
    review_result: {
      field_groups: [
        {
          group_key: 'history_of_present_illness',
          group_label: '现病史',
          fields: [{ field_key: 'hpi_mental_sleep_appetite', label: '精神睡眠食欲', qwen_type: 'J', qwen_path: ['现病史', '精神睡眠食欲'] }]
        }
      ],
      fields: [
        {
          field_key: 'hpi_mental_sleep_appetite',
          field_name: '精神睡眠食欲',
          final_value: '异常',
          status: 'unreviewed',
          qwen_type: 'J',
          qwen_status: 'abnormal',
          qwen_path: ['现病史', '精神睡眠食欲']
        }
      ]
    }
  };

  expect(JSON.stringify(payload)).toContain('qwen_type');
});
```

- [ ] **Step 3: Run tests and confirm failure or missing metadata behavior**

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/src/api/shared-contracts.test.ts
```

Expected before implementation: ReviewPage test may fail if metadata is dropped or J control is unavailable.

- [ ] **Step 4: Update demo fixture**

Add two Qwen fields to `demoReviewSample.ts` with:

```ts
qwen_type: 'T',
qwen_path: ['主诉']
```

and:

```ts
qwen_type: 'J',
qwen_status: 'abnormal',
qwen_path: ['现病史', '精神睡眠食欲']
```

Use synthetic text only. Do not add real patient names or real hospital records.

- [ ] **Step 5: Ensure ReviewPage keeps evidence offset path**

If the test fails because the highlighter ignores offset evidence when `text` is present, keep `findLocatedEvidenceText` behavior:

- Prefer valid offset slice when it matches.
- Fall back to evidence text search.
- Never parse `<sN>` in frontend.

- [ ] **Step 6: Run focused tests**

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/src/api/shared-contracts.test.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/review/demoReviewSample.ts app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/src/api/shared-contracts.test.ts
git commit -m "补充Qwen审核页证据用例"
```

**Review Gate:** Spec reviewer checks frontend still relies on backend evidence offsets instead of anchor parsing. Quality reviewer checks fixtures are synthetic and tests are stable.

---

### Task 12: Add Mocked End-To-End Backend Flow For Qwen Batch

**Files:**
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/backend/tests/conftest.py` only if a reusable fixture is cleaner

- [ ] **Step 1: Add failing backend e2e test**

Add to `app/backend/tests/test_backend_e2e.py`:

```python
def test_qwen_batch_mocked_processing_reaches_review(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports import qwen_batch_adapter

    def fake_runner(job_dir: str, schema_path: str, timeout_seconds: int):
        job = Path(job_dir)
        (job / "result.json").write_text(
            json.dumps(
                {
                    "job_id": "1",
                    "status": "success",
                    "engine": {"name": "qwen_batch_engine", "upstream_commit": "a746ba9"},
                    "document_result": {
                        "merged_text": "主诉：反复咳嗽15年。精神睡眠食欲差。",
                        "pages": [{"page_id": "page_001", "page_no": 1, "status": "success", "text": "主诉：反复咳嗽15年。精神睡眠食欲差。"}],
                    },
                    "review_fields": [
                        {
                            "field_key": "chief_complaint",
                            "field_label": "主诉",
                            "section_key": "chief_complaint",
                            "section_label": "主诉",
                            "original_value": "反复咳嗽15年",
                            "evidence": [{"id": "s1-s1", "text": "主诉：反复咳嗽15年。", "start_offset": 0, "end_offset": 13, "page_no": 1}],
                            "confidence": None,
                            "extraction_status": "extracted",
                            "verification_status": "not_checked",
                            "attention_required": False,
                            "attention_message": "",
                            "quality_flags": [],
                            "source_section": "主诉",
                            "source_hint": "主诉",
                            "source_text": "主诉：反复咳嗽15年。",
                            "source_group_id": "chief_complaint",
                            "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                            "qwen_type": "T",
                            "qwen_path": ["主诉"],
                            "qwen_status": None,
                        }
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(qwen_batch_adapter, "default_run_job", fake_runner)

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    log_dir = tmp_path / "logs"
    export_dir = tmp_path / "exports"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
server:
  port: 18082
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
algorithms:
  algorithm_engine: qwen_batch
  qwen_batch_job_dir: "{tmp_path / "jobs"}"
  qwen_batch_schema_path: "./app/config/schemas/qwen_batch_admission_record.v1.yaml"
""",
        encoding="utf-8",
    )

    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    client = app.test_client()

    patient_response = client.post("/api/patients", json={"name": "测试患者"})
    assert patient_response.status_code == 201
    patient_id = patient_response.get_json()["patient_id"]

    task_response = client.post(
        "/api/tasks",
        json={
            "patient_id": patient_id,
            "document_type": "qwen_batch_admission_record",
            "record_date": "2026-06-26",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.get_json()["task_id"]

    upload = client.post(
        f"/api/mobile/tasks/{task_id}/pages",
        data={"file": (io.BytesIO(b"fake image"), "page.jpg")},
        content_type="multipart/form-data",
    )
    assert upload.status_code in {200, 201}

    finish = client.post(f"/api/mobile/tasks/{task_id}/complete")
    assert finish.status_code == 200

    review = client.get(f"/api/tasks/{task_id}/review")
    assert review.status_code == 200
    payload = review.get_json()
    assert payload["review_result"]["schema_version"] == "qwen_batch_admission_record.v1"
    assert payload["review_result"]["fields"][0]["qwen_type"] == "T"
    assert payload["review_result"]["fields"][0]["evidence"][0]["start_offset"] == 0
```

Add `import io` at the top of the file if not present.

- [ ] **Step 2: Run test and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_qwen_batch_mocked_processing_reaches_review -q
```

Expected: FAIL until app factory, task creation, mobile upload route, and qwen batch orchestrator align.

- [ ] **Step 3: Fix integration points only within planned boundaries**

Allowed fixes:

- Ensure `DocumentProfileRegistry` offers `qwen_batch_admission_record` as an available document type when `algorithm_engine=qwen_batch`.
- Ensure task creation accepts the qwen document type through existing document profile validation.
- Ensure background runner in tests completes deterministically if the existing test fixture already runs inline; otherwise set `background_runner` injection in app test setup.
- Ensure review response includes `field_groups` with Qwen metadata.

Disallowed fixes:

- Do not map `qwen_batch_admission_record` back to `copd_admission_record`.
- Do not bypass mobile upload validation.
- Do not call real vLLM or Docker from this test.

- [ ] **Step 4: Run focused e2e test**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_qwen_batch_mocked_processing_reaches_review -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_backend_e2e.py app/backend/tests/conftest.py app/backend/__init__.py app/backend/services/document_profiles.py
git commit -m "验证Qwen批处理端到端流程"
```

**Review Gate:** Spec reviewer checks qwen flow is mocked but contract-real. Quality reviewer checks no real model/network dependency enters test suite.

---

### Task 13: Add Offline Deployment And Sync Governance Checks

**Files:**
- Modify: `deploy/CLAUDE.md`
- Create: `app/backend/tests/test_qwen_batch_offline_safety.py`

- [ ] **Step 1: Write failing safety test**

Create `app/backend/tests/test_qwen_batch_offline_safety.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "algorithms" / "qwen_batch_engine"


def test_qwen_batch_compose_documents_latest_as_non_production_default():
    compose = (ENGINE / "upstream" / "docker-compose.yaml").read_text(encoding="utf-8")
    assert "vllm/vllm-openai:latest" in compose
    changelog = (ENGINE / "overlay" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "正式离线部署不得使用 latest 作为生产默认镜像" in changelog


def test_qwen_batch_runtime_dirs_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/algorithm_jobs/*" in gitignore
    assert "algorithms/qwen_batch_engine/upstream/model/*" in gitignore
    assert "algorithms/qwen_batch_engine/upstream/vllm_cache/*" in gitignore
```

- [ ] **Step 2: Run test and confirm failure**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_offline_safety.py -q
```

Expected: FAIL until overlay changelog and ignore rules include the production warning.

- [ ] **Step 3: Update overlay changelog and deployment docs**

Add to `algorithms/qwen_batch_engine/overlay/CHANGELOG.md`:

```markdown
### 离线部署约束

- 正式离线部署不得使用 latest 作为生产默认镜像。
- `upstream/docker-compose.yaml` 中的 `vllm/vllm-openai:latest` 仅作为上游原样同步记录保留；产品部署必须在 `deploy/` 层固定镜像 tag 或 digest。
- Python client 依赖必须来自离线 wheelhouse 或预构建镜像。
- 模型权重只通过 `models/llm/` 或现场部署目录只读挂载，不提交到仓库。
```

Add to `deploy/CLAUDE.md` a Qwen batch note:

```markdown
## Qwen Batch Engine Deployment Boundary

- `algorithms/qwen_batch_engine/upstream/` keeps the upstream compose and Dockerfile for diff and sync.
- Production Windows offline deployment must pin the vLLM image tag or digest in `deploy/` assets before switching `algorithm_engine=qwen_batch`.
- Runtime directories `data/algorithm_jobs/`, `logs/`, `exports/`, `models/llm/`, `vllm_cache/`, and upstream `input/output/model/logs/vllm_cache` contents must not be committed.
```

- [ ] **Step 4: Run focused safety test**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_batch_offline_safety.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add algorithms/qwen_batch_engine/overlay/CHANGELOG.md deploy/CLAUDE.md app/backend/tests/test_qwen_batch_offline_safety.py
git commit -m "补充Qwen离线部署约束"
```

**Review Gate:** Spec reviewer checks production path remains offline and upstream `latest` is not normalized into product default. Quality reviewer checks docs are precise and do not hide deployment risk.

---

### Task 14: Run Full Verification Before Default Switch

**Files:**
- Modify only files required to fix failures found by verification.

- [ ] **Step 1: Run backend focused Qwen tests**

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_qwen_batch_engine_layout.py \
  app/backend/tests/test_qwen_batch_normalize_result.py \
  app/backend/tests/test_qwen_batch_run_job.py \
  app/backend/tests/test_qwen_batch_adapter.py \
  app/backend/tests/test_qwen_batch_orchestrator.py \
  app/backend/tests/test_qwen_batch_offline_safety.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run backend contract tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py app/backend/tests/test_backend_e2e.py app/backend/tests/test_review_service.py app/backend/tests/test_export_service.py app/backend/tests/test_schema_loader.py app/backend/tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests and typecheck**

```bash
npm --prefix app/frontend run typecheck
npm --prefix app/frontend run test -- --run
npm --prefix app/frontend run build
```

Expected: all commands PASS.

- [ ] **Step 5: Run git cleanliness checks**

```bash
git diff --check
rg "真实患者|patient base64|完整模型输出|模型权重|密钥|BEGIN PRIVATE KEY|api_key" algorithms/qwen_batch_engine app/backend app/frontend docs deploy
```

Expected:

- `git diff --check` prints no output.
- `rg` may match documentation warnings but must not reveal real patient data, real OCR text, secrets, or committed runtime output.

- [ ] **Step 6: Commit verification-only fixes**

If verification required code or test fixes:

```bash
git add <changed-files>
git commit -m "修正Qwen批处理迁移验证问题"
```

If no fixes were required, do not create an empty commit.

**Review Gate:** Use the final review wave. Do not switch `algorithm_engine` default to `qwen_batch` until all final reviewers approve.

---

### Task 15: Controlled Default Switch After Review Approval

**Files:**
- Modify: `app/config/default.yaml`
- Modify: deployment/local config template if this repository has one
- Modify: `docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md` only to record the switch date and verification evidence

- [ ] **Step 1: Confirm switch gates**

Before editing defaults, confirm all are true:

```text
contract tests passed
mocked backend e2e passed
frontend review tests passed
export tests passed
offline safety test passed
rollback config remains available
legacy path still selectable with algorithm_engine=legacy
```

- [ ] **Step 2: Switch default only if the user explicitly approves**

Change `app/config/default.yaml`:

```yaml
algorithms:
  algorithm_engine: qwen_batch
```

Do not remove legacy config keys or old orchestrator code in this task.

- [ ] **Step 3: Add rollback note**

Add a short rollback note to the spec:

```markdown
## 默认切换记录

- 切换日期：2026-06-26 或实际执行日期。
- 默认引擎：`algorithm_engine=qwen_batch`。
- 回滚方式：将 `app/config/local.yaml` 或部署配置中的 `algorithms.algorithm_engine` 改回 `legacy`，重新处理任务会使用旧逐页 OCR/字段抽取路径；失败任务不会静默回落。
- 验证：记录本次执行的测试命令和结果摘要。
```

- [ ] **Step 4: Run switch verification**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py app/backend/tests/test_backend_e2e.py::test_create_backend_app_with_qwen_batch_engine_config -q
npm --prefix app/frontend run typecheck
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config/default.yaml docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md
git commit -m "切换默认Qwen批处理引擎"
```

**Review Gate:** Spec reviewer checks explicit approval and rollback. Quality reviewer checks default switch does not delete legacy code.

---

## Final Multi-Angle Review Prompts

After Task 14, and again after Task 15 if the default switch is approved, dispatch these reviewers with the full diff and test results.

### Architecture Reviewer Prompt

```text
Review the Qwen batch migration architecture in `/home/kbzz1/manzufei_ocr`.

Focus:
- `algorithms/qwen_batch_engine/upstream` remains upstream sync area.
- `overlay` contains audited productization changes only.
- `adapter` owns job/result normalization and does not infer fields.
- `app/backend` only depends on stable port/result contracts.
- legacy algorithm path remains selectable and not silently used as fallback.

Report findings first with file/line references. Approve only if boundaries are clean.
```

### Field Contract Reviewer Prompt

```text
Review Qwen field contract migration.

Focus:
- `app/config/schemas/qwen_batch_admission_record.v1.yaml` matches upstream Chinese nested schema.
- `qwen_type`, `qwen_path`, `qwen_status`, and stable `field_key` are preserved through backend, review API, frontend, and export.
- T fields remain original-text extraction fields.
- J fields remain judgement/status fields.
- No default mapping back to old 61 fields exists.

Report findings first with file/line references.
```

### Evidence Reviewer Prompt

```text
Review evidence handling.

Focus:
- Anchor ranges are normalized to evidence text, offsets, page/source metadata.
- Missing anchors mark a field for manual attention without failing the whole task.
- Frontend highlighter uses backend-provided offsets/text and does not parse anchors or infer evidence.
- Export preserves evidence audit metadata.

Report findings first with file/line references.
```

### Backend Failure And Privacy Reviewer Prompt

```text
Review backend failure and privacy semantics.

Focus:
- job creation, subprocess failure, timeout, invalid JSON, empty OCR, and empty fields lead to failed tasks.
- single-field evidence problems produce attention flags, not task failure.
- ordinary logs and error files do not include OCR full text, patient names, base64 images, full prompts, or full model outputs.
- tests do not call real vLLM, Docker, network, or use real patient data.

Report findings first with file/line references.
```

### Frontend UX Reviewer Prompt

```text
Review frontend Qwen review workflow.

Focus:
- T fields are editable text fields.
- J fields are compact status controls for 正常 / 异常 / 未提及 / 不确定.
- controls work in read-only mode, mobile width, and keyboard/screen-reader labels.
- evidence click still jumps/highlights OCR text.
- frontend never infers structured values from schema or OCR text.

Report findings first with file/line references.
```

### Offline Deployment Reviewer Prompt

```text
Review offline deployment safety.

Focus:
- no committed model weights, real data, logs, vLLM cache, `.env`, or local private paths.
- production docs require pinned vLLM image tag/digest before enabling Qwen batch in deployment.
- runtime directories are ignored.
- no runtime CDN/cloud/download/telemetry dependency was introduced.

Report findings first with file/line references.
```

### Test Reviewer Prompt

```text
Review test coverage for the Qwen batch migration.

Focus:
- focused tests cover layout, schema, normalization, runner, backend adapter, orchestrator, review, export, frontend J controls, evidence, config, and mocked e2e.
- full backend and frontend verification commands were run or blocked with clear reasons.
- tests are deterministic and do not require real model services.

Report findings first with file/line references.
```

---

## Execution Handoff Prompt

```text
请在 `/home/kbzz1/manzufei_ocr` 中执行：

Spec: `docs/superpowers/specs/2026-06-26-qwen-batch-engine-migration-design.md`
Plan: `docs/superpowers/plans/2026-06-26-qwen-batch-engine-migration-implementation-plan.md`

要求：
- 先读取 `AGENTS.md`、`CLAUDE.md`、`docs/AGENTS.md`、`app/backend/CLAUDE.md`、`app/backend/services/algorithm_ports/CLAUDE.md`、`app/frontend/AGENTS.md`。
- 使用 `$Skill`/Superpowers：`superpowers:subagent-driven-development`。
- 严格按 plan task-by-task 执行；每个任务先写失败测试，再实现，再跑测试。
- 每个任务完成后单独 commit，commit message 使用中文。
- 每个任务后必须先派 spec-compliance reviewer，再派 code-quality reviewer；有问题就修复并复审。
- 全部任务完成后必须按 plan 的 final multi-angle review prompts 派多角度 reviewer。
- 不要修改与计划无关的文件；不要回滚用户已有改动。
- 不要提交真实数据、日志、模型权重、密钥、本机私有路径、OCR 全文、图片 base64 或完整模型输出。
- 新 engine 失败时必须进入 failed，不允许静默 fallback 到 legacy 生成另一套字段。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 最后运行 plan 的最终验证命令，并报告通过项和无法运行项及原因。

开始执行前，先复述你将执行的 Task 1、Task 1 的验证命令，以及本轮不会切换默认引擎，除非用户在 Task 15 前明确批准。
```
