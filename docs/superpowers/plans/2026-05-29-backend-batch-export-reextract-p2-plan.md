# 批量导出、重抽取与文书模板 P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现任务级文书模板选择基础、手机端模板选择、按 `document_type` 选择 schema/prompt/抽取端口，并补齐批量 zip manifest、重抽取审计元数据和 `section_groups` OCR 风险提示。

**Architecture:** 新增文书 profile registry 作为 document_type 到 schema、prompt、field port 的唯一后端入口。电脑端创建任务不传模板，`TaskService` 使用后端记忆的 `last_document_type`；手机端上传页可在 `uploading` 状态切换模板。处理和重抽取统一从任务 `document_type` 解析 profile，未注册类型失败，不静默回退。

**Tech Stack:** Flask、pytest、JsonStore、zipfile、Vite React、Vitest/React Testing Library。测试命令默认使用 `conda run -n manzufei_ocr python -m pytest ...` 和 `npm --prefix app/frontend run test -- ...`。

---

## Spec Review

审查对象：`docs/superpowers/specs/2026-05-29-backend-batch-export-reextract-p2-design.md`

结论：spec 可执行，范围集中在同一条任务级模板能力链路上，无需拆分。它现在覆盖四组能力：文书模板 registry 和手机选择、批量导出 manifest/失败报告、`section_groups` prompt OCR 风险提示、重抽取元数据和按文书类型重抽取。

执行注意：

- 当前工作区已有未提交的 Excel 导出修复，涉及 `app/backend/services/export_service.py` 和 `app/backend/tests/test_export_service.py`。实施时保留这些改动，只追加本计划所需代码。
- 手机端可选模板列表只能暴露已注册且具备 schema/prompt/field port 的 profile；`progress_note` 可作为测试用 fake profile，但不能在默认运行配置中显示。
- 电脑端新建任务弹窗不新增模板选择。任何任务默认模板都由后端 `last_document_type` 决定。
- 批量导出失败路径必须先完成所有任务校验，再写 zip。失败时不要覆盖 `exports/batch/batch-review-export.zip`。

## File Map

- Create: `app/backend/services/document_profiles.py`
  - 文书 profile registry、默认模板记忆、可用模板列表、schema/prompt/field port 查询。
- Modify: `app/backend/__init__.py`
  - 装配 `DOCUMENT_PROFILE_REGISTRY`，把当前 COPD schema、prompt 和 field port 注册为 `copd_admission_record`。
- Modify: `app/backend/services/task_service.py`
  - 创建任务时写入默认 `document_type`/`schema_version`/`prompt_version`；新增 `change_document_type()`。
- Modify: `app/backend/routes/mobile.py`
  - 上传状态返回模板信息；新增 `PATCH /api/mobile-upload/{task_id}/document-type`。
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
  - 字段抽取阶段按任务 `document_type` 解析 profile 和 field port。
- Modify: `app/backend/services/reextraction_service.py`
  - 重抽取按任务 `document_type` 解析 schema/prompt/field port。
- Modify: `app/backend/services/export_service.py`
  - 批量 zip 写入 `manifest.json`，失败响应包含 failed task report。
- Modify: `app/backend/services/copd_extraction/prompts.py`
  - 补齐 `build_section_group_extraction_prompt()` OCR 风险提示。
- Modify: `app/frontend/src/api/mobileUpload.ts`
  - 增加模板类型、上传状态字段、修改模板 API。
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
  - 增加手机端模板选择控件；上传完成后禁用。
- Tests:
  - `app/backend/tests/test_document_profiles.py`
  - `app/backend/tests/test_task_service.py`
  - `app/backend/tests/test_mobile_upload_routes.py`
  - `app/backend/tests/test_orchestrator.py`
  - `app/backend/tests/test_reextraction_service.py`
  - `app/backend/tests/test_export_service.py`
  - `app/backend/tests/test_export_routes.py`
  - `app/backend/tests/test_copd_prompts.py`
  - `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
  - `app/frontend/src/api/shared-contracts.test.ts`
- Docs after implementation:
  - `docs/PRD任务清单.md`

---

### Task 1: Document Profile Registry

**Files:**
- Create: `app/backend/services/document_profiles.py`
- Test: `app/backend/tests/test_document_profiles.py`

- [ ] **Step 1: Write failing registry tests**

Create `app/backend/tests/test_document_profiles.py`:

```python
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.document_profiles import DocumentProfile, DocumentProfileRegistry
from app.backend.storage.json_store import JsonStore


class FakeFieldPort:
    def extract(self, input):
        return []


def make_profile(document_type="copd_admission_record", label="入院记录"):
    return DocumentProfile(
        document_type=document_type,
        label=label,
        schema={"version": f"{document_type}.v1", "document_type": document_type, "field_groups": []},
        prompt_version=f"{document_type}.prompt.v1",
        field_port=FakeFieldPort(),
        quality_rule_profile=document_type,
    )


def test_registry_lists_only_registered_profiles(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[make_profile()],
        default_document_type="copd_admission_record",
    )

    assert registry.get_available_document_types() == [
        {
            "document_type": "copd_admission_record",
            "label": "入院记录",
            "schema_version": "copd_admission_record.v1",
        }
    ]


def test_registry_remembers_last_document_type(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[
            make_profile("copd_admission_record", "入院记录"),
            make_profile("progress_note", "病程记录"),
        ],
        default_document_type="copd_admission_record",
    )

    registry.remember_last_document_type("progress_note")

    assert registry.get_default_document_type() == "progress_note"
    assert JsonStore(str(tmp_path)).read("settings/document_type.json")["last_document_type"] == "progress_note"


def test_registry_rejects_unknown_document_type(tmp_path):
    registry = DocumentProfileRegistry(
        store=JsonStore(str(tmp_path)),
        profiles=[make_profile()],
        default_document_type="copd_admission_record",
    )

    with pytest.raises(AppError) as exc:
        registry.get_profile("progress_note")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code
    assert exc.value.details["document_type"] == "progress_note"
```

- [ ] **Step 2: Run registry tests to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_document_profiles.py -q
```

Expected: FAIL because `app.backend.services.document_profiles` does not exist.

- [ ] **Step 3: Implement registry**

Create `app/backend/services/document_profiles.py`:

```python
from dataclasses import dataclass
from typing import Any

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


@dataclass(frozen=True)
class DocumentProfile:
    document_type: str
    label: str
    schema: dict
    prompt_version: str
    field_port: Any
    quality_rule_profile: str | None = None

    @property
    def schema_version(self) -> str:
        return str(self.schema.get("version") or "")


class DocumentProfileRegistry:
    def __init__(self, store: JsonStore, profiles: list[DocumentProfile], default_document_type: str):
        self._store = store
        self._profiles = {profile.document_type: profile for profile in profiles}
        self._default_document_type = default_document_type

    def get_profile(self, document_type: str | None) -> DocumentProfile:
        resolved = document_type or self.get_default_document_type()
        profile = self._profiles.get(resolved)
        if profile is None:
            raise AppError(
                ErrorCode.INVALID_REQUEST_PARAMS,
                message="文书模板不存在或未完成接入",
                details={"document_type": resolved},
            )
        return profile

    def get_schema(self, document_type: str | None) -> dict:
        return self.get_profile(document_type).schema

    def get_available_document_types(self) -> list[dict]:
        return [
            {
                "document_type": profile.document_type,
                "label": profile.label,
                "schema_version": profile.schema_version,
            }
            for profile in self._profiles.values()
        ]

    def get_default_document_type(self) -> str:
        settings = self._store.read("settings/document_type.json") or {}
        candidate = settings.get("last_document_type")
        if candidate in self._profiles:
            return candidate
        return self._default_document_type

    def remember_last_document_type(self, document_type: str) -> None:
        self.get_profile(document_type)
        self._store.write("settings/document_type.json", {"last_document_type": document_type})

    def to_task_document_summary(self, document_type: str | None) -> dict:
        profile = self.get_profile(document_type)
        return {
            "document_type": profile.document_type,
            "document_type_label": profile.label,
            "schema_version": profile.schema_version,
            "prompt_version": profile.prompt_version,
            "extraction_profile": profile.document_type,
        }
```

- [ ] **Step 4: Run registry tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_document_profiles.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit registry**

Run:

```bash
git add app/backend/services/document_profiles.py app/backend/tests/test_document_profiles.py
git commit -m "新增文书模板Profile注册表"
```

Expected: commit succeeds.

---

### Task 2: TaskService document_type defaults and updates

**Files:**
- Modify: `app/backend/services/task_service.py`
- Test: `app/backend/tests/test_task_service.py`

- [ ] **Step 1: Write failing task default test**

Add this helper and test to `app/backend/tests/test_task_service.py`:

```python
class FakeDocumentProfiles:
    def __init__(self):
        self.remembered = []
        self.default_document_type = "copd_admission_record"

    def get_default_document_type(self):
        return self.default_document_type

    def to_task_document_summary(self, document_type):
        return {
            "document_type": document_type,
            "document_type_label": "入院记录" if document_type == "copd_admission_record" else "病程记录",
            "schema_version": f"{document_type}.v1",
            "prompt_version": f"{document_type}.prompt.v1",
            "extraction_profile": document_type,
        }

    def remember_last_document_type(self, document_type):
        self.remembered.append(document_type)


def test_create_task_uses_last_document_type_default(tmp_path):
    profiles = FakeDocumentProfiles()
    profiles.default_document_type = "progress_note"
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)

    task = service.create_uploading_task("http://127.0.0.1:8081")

    assert task["document_type"] == "progress_note"
    assert task["schema_version"] == "progress_note.v1"
    assert task["prompt_version"] == "progress_note.prompt.v1"
```

- [ ] **Step 2: Write failing mobile update service test**

Add this test to `app/backend/tests/test_task_service.py`:

```python
def test_change_document_type_updates_uploading_task_and_default(tmp_path):
    profiles = FakeDocumentProfiles()
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)
    task = service.create_uploading_task("http://127.0.0.1:8081")

    updated = service.change_document_type(task["task_id"], "progress_note")

    assert updated["document_type"] == "progress_note"
    assert updated["schema_version"] == "progress_note.v1"
    assert profiles.remembered == ["progress_note"]
```

- [ ] **Step 3: Write failing locked-state test**

Add this test:

```python
def test_change_document_type_rejects_non_uploading_task(tmp_path):
    profiles = FakeDocumentProfiles()
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)
    task = service.create_uploading_task("http://127.0.0.1:8081")
    persisted = service.get_task(task["task_id"])
    persisted["status"] = "processing"
    JsonStore(str(tmp_path)).write(f"tasks/{task['task_id']}.json", persisted)

    with pytest.raises(AppError) as exc:
        service.change_document_type(task["task_id"], "progress_note")

    assert exc.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
```

- [ ] **Step 4: Run task service tests to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py::test_create_task_uses_last_document_type_default app/backend/tests/test_task_service.py::test_change_document_type_updates_uploading_task_and_default app/backend/tests/test_task_service.py::test_change_document_type_rejects_non_uploading_task -q
```

Expected: FAIL because `TaskService.__init__()` has no `document_profiles` parameter and `change_document_type()` does not exist.

- [ ] **Step 5: Implement TaskService document_type support**

Modify `TaskService.__init__` signature:

```python
        document_profiles=None,
```

Store it:

```python
        self._document_profiles = document_profiles
```

Add this helper:

```python
    def _document_summary_for(self, document_type: str | None = None) -> dict:
        if self._document_profiles is None:
            schema = self._schema_provider() if self._schema_provider else {}
            return {
                "document_type": document_type or schema.get("document_type") or "copd_admission_record",
                "document_type_label": "入院记录",
                "schema_version": schema.get("version"),
                "prompt_version": None,
                "extraction_profile": document_type or schema.get("document_type") or "copd_admission_record",
            }
        resolved_type = document_type or self._document_profiles.get_default_document_type()
        return self._document_profiles.to_task_document_summary(resolved_type)
```

In `create_uploading_task()`, before `task = {...}`, add:

```python
        document_summary = self._document_summary_for()
```

Add these fields to the task dict:

```python
            "document_type": document_summary["document_type"],
            "document_type_label": document_summary["document_type_label"],
            "schema_version": document_summary["schema_version"],
            "prompt_version": document_summary["prompt_version"],
            "extraction_profile": document_summary["extraction_profile"],
```

Add this method:

```python
    def change_document_type(self, task_id: str, document_type: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.UPLOADING.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": "document_type_change"},
            )
        document_summary = self._document_summary_for(document_type)
        task.update(document_summary)
        task["updated_at"] = self._now()
        self._write_task(task)
        if self._document_profiles is not None:
            self._document_profiles.remember_last_document_type(document_summary["document_type"])
        return self._normalize_task(task)
```

In `_to_task_summary()`, include:

```python
            "document_type": task.get("document_type"),
            "document_type_label": task.get("document_type_label"),
            "schema_version": task.get("schema_version"),
            "prompt_version": task.get("prompt_version"),
```

In `_normalize_task()`, add compatibility defaults:

```python
        normalized.setdefault("document_type", "copd_admission_record")
        normalized.setdefault("document_type_label", "入院记录")
        normalized.setdefault("schema_version", None)
        normalized.setdefault("prompt_version", None)
        normalized.setdefault("extraction_profile", normalized.get("document_type"))
```

- [ ] **Step 6: Run task service tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit TaskService changes**

Run:

```bash
git add app/backend/services/task_service.py app/backend/tests/test_task_service.py
git commit -m "支持任务级文书模板默认值"
```

Expected: commit succeeds.

---

### Task 3: Mobile upload template API

**Files:**
- Modify: `app/backend/routes/mobile.py`
- Test: `app/backend/tests/test_mobile_upload_routes.py`

- [ ] **Step 1: Write failing status response test**

Add to `app/backend/tests/test_mobile_upload_routes.py`:

```python
def test_mobile_upload_status_returns_document_type_options(client, app):
    task = client.post("/api/tasks").get_json()["data"]

    response = client.get(f"/api/mobile-upload/{task['task_id']}?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["document_type"] == "copd_admission_record"
    assert data["document_type_label"] == "入院记录"
    assert data["available_document_types"] == [
        {
            "document_type": "copd_admission_record",
            "label": "入院记录",
            "schema_version": data["schema_version"],
        }
    ]
```

- [ ] **Step 2: Write failing PATCH route test**

Add:

```python
def test_mobile_upload_can_change_document_type_while_uploading(client):
    task = client.post("/api/tasks").get_json()["data"]

    response = client.patch(
        f"/api/mobile-upload/{task['task_id']}/document-type?token={task['upload_token']}",
        json={"document_type": "copd_admission_record"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["document_type"] == "copd_admission_record"
    assert data["document_type_label"] == "入院记录"
```

- [ ] **Step 3: Run mobile route tests to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_mobile_upload_routes.py::test_mobile_upload_status_returns_document_type_options app/backend/tests/test_mobile_upload_routes.py::test_mobile_upload_can_change_document_type_while_uploading -q
```

Expected: FAIL because mobile route does not return template fields and PATCH route does not exist.

- [ ] **Step 4: Implement mobile route changes**

In `get_task_upload_status()`, build available types:

```python
    registry = current_app.config.get("DOCUMENT_PROFILE_REGISTRY")
    available_document_types = registry.get_available_document_types() if registry else []
```

Add these response fields:

```python
            "document_type": task.get("document_type"),
            "document_type_label": task.get("document_type_label"),
            "schema_version": task.get("schema_version"),
            "available_document_types": available_document_types,
```

Add route:

```python
@mobile_bp.route("/api/mobile-upload/<task_id>/document-type", methods=["PATCH"])
def change_task_document_type(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    payload = request.get_json(silent=True) or {}
    document_type = payload.get("document_type")
    if not isinstance(document_type, str) or not document_type:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="document_type 必须是非空字符串")
    updated = task_service.change_document_type(task_id, document_type)
    return success(
        data={
            "task_id": updated["task_id"],
            "document_type": updated["document_type"],
            "document_type_label": updated.get("document_type_label"),
            "schema_version": updated.get("schema_version"),
            "prompt_version": updated.get("prompt_version"),
        }
    )
```

- [ ] **Step 5: Run mobile route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_mobile_upload_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit mobile route changes**

Run:

```bash
git add app/backend/routes/mobile.py app/backend/tests/test_mobile_upload_routes.py
git commit -m "增加手机端文书模板选择接口"
```

Expected: commit succeeds.

---

### Task 4: Backend wiring for profiles

**Files:**
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Test: `app/backend/tests/test_orchestrator.py`
- Test: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write failing orchestrator field-port selection test**

Add to `app/backend/tests/test_orchestrator.py`:

```python
def test_orchestrator_uses_document_type_specific_field_port(tmp_path):
    class PassingImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class PassingDocPort:
        def parse(self, input):
            return {"pages": [{"page_id": "p1", "page_no": 1, "status": "success"}], "merged_text": "姓名：张三"}

    class CapturingFieldPort:
        def __init__(self):
            self.inputs = []

        def extract(self, input):
            self.inputs.append(input)
            return [{
                "field_key": "patient_name",
                "original_value": "张三",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }]

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    field_port = CapturingFieldPort()
    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    orchestrator = ProcessingOrchestrator(
        store=JsonStore(str(tmp_path)),
        image_port=PassingImagePort(),
        doc_port=PassingDocPort(),
        field_port_registry={"copd_admission_record": field_port},
    )

    orchestrator.run(
        {
            "task_id": "task_001",
            "document_type": "copd_admission_record",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema={"version": "copd.v1", "document_type": "copd_admission_record"},
    )

    assert field_port.inputs[0]["document_type"] == "copd_admission_record"
```

- [ ] **Step 2: Run orchestrator test to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py::test_orchestrator_uses_document_type_specific_field_port -q
```

Expected: FAIL because `ProcessingOrchestrator.__init__()` does not accept `field_port_registry`.

- [ ] **Step 3: Implement orchestrator field port registry**

Modify `ProcessingOrchestrator.__init__()` to accept:

```python
        field_port_registry=None,
```

Store:

```python
        self._field_port_registry = field_port_registry or {}
```

Add helper:

```python
    def _resolve_field_port(self, document_type: str | None):
        if document_type and document_type in self._field_port_registry:
            return self._field_port_registry[document_type]
        return self._field_port
```

Replace the field port missing check:

```python
        field_port = self._resolve_field_port(task.get("document_type"))
        if field_port is None:
```

Build field input as:

```python
        field_input = {
            "task_id": task_id,
            "document_type": task.get("document_type"),
            "document_result": doc_result,
            "schema": schema,
            "prompt_version": task.get("prompt_version"),
        }
```

Call:

```python
            candidates = field_port.extract(field_input)
```

- [ ] **Step 4: Wire registry in backend app**

In `app/backend/__init__.py`, import:

```python
from .services.document_profiles import DocumentProfile, DocumentProfileRegistry
from .services.copd_extraction.prompts import COPD_EXTRACTION_PROMPT_VERSION
```

After `schema_service` and `field_port` are created, construct:

```python
document_profile_registry = DocumentProfileRegistry(
    store=store,
    profiles=[
        DocumentProfile(
            document_type="copd_admission_record",
            label="入院记录",
            schema=schema_service.get_current(),
            prompt_version=COPD_EXTRACTION_PROMPT_VERSION,
            field_port=field_port,
            quality_rule_profile="copd_admission_record",
        )
    ],
    default_document_type="copd_admission_record",
)
app.config["DOCUMENT_PROFILE_REGISTRY"] = document_profile_registry
```

Pass `document_profiles=document_profile_registry` to `TaskService(...)`, and pass:

```python
field_port_registry={"copd_admission_record": field_port}
```

to `ProcessingOrchestrator(...)`.

- [ ] **Step 5: Run backend wiring tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py app/backend/tests/test_backend_e2e.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit backend wiring**

Run:

```bash
git add app/backend/__init__.py app/backend/services/algorithm_ports/orchestrator.py app/backend/tests/test_orchestrator.py app/backend/tests/test_backend_e2e.py
git commit -m "按文书类型选择字段抽取端口"
```

Expected: commit succeeds.

---

### Task 5: Reextraction document_type profile support

**Files:**
- Modify: `app/backend/services/reextraction_service.py`
- Modify: `app/backend/__init__.py`
- Test: `app/backend/tests/test_reextraction_service.py`

- [ ] **Step 1: Write failing reextract profile test**

Add to `app/backend/tests/test_reextraction_service.py`:

```python
def test_reextract_uses_task_document_type_profile(tmp_path):
    class ProfileFieldPort(FakeFieldPort):
        pass

    class FakeProfiles:
        def __init__(self, field_port):
            self.field_port = field_port

        def get_profile(self, document_type):
            assert document_type == "copd_admission_record"
            return type("Profile", (), {
                "document_type": "copd_admission_record",
                "schema": schema(),
                "prompt_version": "copd.prompt.v2",
                "field_port": self.field_port,
            })()

    field_port = ProfileFieldPort()
    service, store, _task_service, _port = make_service(tmp_path, field_port=None)
    service._document_profiles = FakeProfiles(field_port)
    write_task(store, status="review")
    task = store.read("tasks/task_001.json")
    task["document_type"] = "copd_admission_record"
    store.write("tasks/task_001.json", task)
    write_document_result(store)

    result = service.reextract("task_001")

    assert field_port.inputs[0]["document_type"] == "copd_admission_record"
    assert result["prompt_version"] == "copd.prompt.v2"
```

- [ ] **Step 2: Run reextract profile test to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_reextraction_service.py::test_reextract_uses_task_document_type_profile -q
```

Expected: FAIL because `ReextractionService` has no `document_profiles` support.

- [ ] **Step 3: Implement profile-aware reextract**

Modify `ReextractionService.__init__()` to accept:

```python
        document_profiles=None,
```

Store it:

```python
        self._document_profiles = document_profiles
```

At the start of `reextract()` after loading task and document result, resolve profile:

```python
        profile = None
        if self._document_profiles is not None:
            profile = self._document_profiles.get_profile(task.get("document_type") or "copd_admission_record")
            schema = profile.schema
            field_port = profile.field_port
            prompt_version = profile.prompt_version
        else:
            schema = self._schema_provider() if self._schema_provider else {}
            field_port = self._field_port
            prompt_version = self._prompt_version_provider()
```

Use `field_port` instead of `self._field_port`, include document type in extract input:

```python
                "document_type": task.get("document_type") or "copd_admission_record",
```

Set metadata prompt version:

```python
            "prompt_version": prompt_version,
```

In `app/backend/__init__.py`, pass `document_profiles=document_profile_registry` to `ReextractionService(...)`.

- [ ] **Step 4: Strengthen existing metadata assertion**

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

- [ ] **Step 5: Run reextract tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_reextraction_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit reextract changes**

Run:

```bash
git add app/backend/services/reextraction_service.py app/backend/__init__.py app/backend/tests/test_reextraction_service.py
git commit -m "按文书类型执行OCR文本重抽取"
```

Expected: commit succeeds.

---

### Task 6: Frontend mobile template selection

**Files:**
- Modify: `app/frontend/src/api/mobileUpload.ts`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/mobile-capture.css`
- Test: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
- Test: `app/frontend/src/api/shared-contracts.test.ts`

- [ ] **Step 1: Add API contract test**

In `app/frontend/src/api/shared-contracts.test.ts`, add:

```ts
it('updates mobile task document type', async () => {
  server.use(
    http.patch('*/api/mobile-upload/task_001/document-type', async ({ request }) => {
      const body = await request.json() as { document_type: string };
      expect(body.document_type).toBe('copd_admission_record');
      return HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          document_type: 'copd_admission_record',
          document_type_label: '入院记录',
          schema_version: 'copd.v1'
        }
      });
    })
  );

  await expect(updateTaskDocumentType('task_001', 'token_001', 'copd_admission_record')).resolves.toMatchObject({
    document_type: 'copd_admission_record',
    document_type_label: '入院记录'
  });
});
```

Import `updateTaskDocumentType` from `./mobileUpload`.

- [ ] **Step 2: Update mobile upload API types**

In `app/frontend/src/api/mobileUpload.ts`, add:

```ts
export interface DocumentTypeOption {
  document_type: string;
  label: string;
  schema_version: string;
}

export interface TaskDocumentTypeUpdate {
  task_id: string;
  document_type: string;
  document_type_label?: string;
  schema_version?: string;
  prompt_version?: string;
}
```

Extend `TaskUploadStatus`:

```ts
  document_type?: string;
  document_type_label?: string;
  schema_version?: string;
  available_document_types?: DocumentTypeOption[];
```

Add:

```ts
export function updateTaskDocumentType(taskId: string, token: string, documentType: string) {
  return apiRequest<TaskDocumentTypeUpdate>(
    `/api/mobile-upload/${encodeURIComponent(taskId)}/document-type?token=${encodeURIComponent(token)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_type: documentType })
    }
  );
}
```

- [ ] **Step 3: Add mobile component test**

In `MobileCapturePage.test.tsx`, add:

```tsx
it('shows document template selector and updates selection before finish', async () => {
  const user = userEvent.setup();
  server.use(
    http.get('*/api/mobile-upload/task_001', () => HttpResponse.json({
      success: true,
      data: {
        task_id: 'task_001',
        status: 'uploading',
        page_count: 0,
        images: [],
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        schema_version: 'copd.v1',
        available_document_types: [
          { document_type: 'copd_admission_record', label: '入院记录', schema_version: 'copd.v1' }
        ]
      }
    })),
    http.patch('*/api/mobile-upload/task_001/document-type', () => HttpResponse.json({
      success: true,
      data: {
        task_id: 'task_001',
        document_type: 'copd_admission_record',
        document_type_label: '入院记录',
        schema_version: 'copd.v1'
      }
    }))
  );

  render(<MobileCapturePage taskId="task_001" token="token_001" />);

  const select = await screen.findByLabelText('文书模板');
  expect(select).toHaveValue('copd_admission_record');
  await user.selectOptions(select, 'copd_admission_record');
  expect(await screen.findByText('当前模板：入院记录')).toBeTruthy();
});
```

- [ ] **Step 4: Implement mobile template UI**

In `MobileCapturePage.tsx`, import `updateTaskDocumentType` and add state:

```tsx
  const [documentType, setDocumentType] = useState('');
  const [documentTypeLabel, setDocumentTypeLabel] = useState('');
  const [documentTypes, setDocumentTypes] = useState<DocumentTypeOption[]>([]);
  const [isChangingDocumentType, setIsChangingDocumentType] = useState(false);
```

When loading status, set:

```tsx
        setDocumentType(status.document_type ?? '');
        setDocumentTypeLabel(status.document_type_label ?? '');
        setDocumentTypes(status.available_document_types ?? []);
```

Add handler:

```tsx
  async function handleDocumentTypeChange(nextDocumentType: string) {
    if (!taskId || !token || !nextDocumentType || isFinished) return;
    setIsChangingDocumentType(true);
    setError(null);
    try {
      const updated = await updateTaskDocumentType(taskId, token, nextDocumentType);
      setDocumentType(updated.document_type);
      setDocumentTypeLabel(updated.document_type_label ?? '');
    } catch (documentTypeError) {
      setError(getErrorMessage(documentTypeError, '文书模板切换失败'));
    } finally {
      setIsChangingDocumentType(false);
    }
  }
```

Render before upload card:

```tsx
        {documentTypes.length > 0 ? (
          <section className="capture-card capture-card--template" aria-label="文书模板">
            <label className="mobile-capture__template-select">
              <span>文书模板</span>
              <select
                aria-label="文书模板"
                value={documentType}
                disabled={isFinished || isChangingDocumentType}
                onChange={(event) => void handleDocumentTypeChange(event.currentTarget.value)}
              >
                {documentTypes.map((item) => (
                  <option key={item.document_type} value={item.document_type}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <p>当前模板：{documentTypeLabel || documentType}</p>
          </section>
        ) : null}
```

Add CSS:

```css
.capture-card--template {
  gap: 10px;
}

.mobile-capture__template-select {
  display: grid;
  gap: 8px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}

.mobile-capture__template-select select {
  min-height: 42px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  padding: 0 12px;
  background: #ffffff;
  color: #0f172a;
  font-size: 15px;
}
```

- [ ] **Step 5: Run frontend tests**

Run:

```bash
npm --prefix app/frontend run test -- MobileCapturePage.test.tsx shared-contracts.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit frontend mobile template UI**

Run:

```bash
git add app/frontend/src/api/mobileUpload.ts app/frontend/src/api/shared-contracts.test.ts app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx app/frontend/src/pages/mobile-capture/mobile-capture.css
git commit -m "增加手机端文书模板选择"
```

Expected: commit succeeds.

---

### Task 7: Batch zip manifest and failure report

**Files:**
- Modify: `app/backend/services/export_service.py`
- Modify: `app/backend/tests/test_export_service.py`
- Modify: `app/backend/tests/test_export_routes.py`

- [ ] **Step 1: Write failing manifest service test**

Append after `test_batch_zip_exports_json_files_for_multiple_tasks`:

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

    assert names == ["manifest.json", "task_001/task_001.review.json", "task_002/task_002.review.json"]
    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2
    assert manifest["success_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["failed_tasks"] == []
    assert manifest["success_tasks"][0]["json_path"] == "task_001/task_001.review.json"
    assert manifest["success_tasks"][0]["field_count"] == 1
    assert manifest["success_tasks"][0]["schema_version"] == "1.0.0"
    assert manifest["success_tasks"][0]["document_type"] == "general_medical_record"
    assert manifest["generated_at"]
```

- [ ] **Step 2: Write failing batch validation details test**

Append:

```python
def test_batch_zip_reports_all_non_exportable_tasks_without_writing_new_zip(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="uploading")
    write_review_result(export_service._store, task_id="task_002")

    with pytest.raises(AppError) as exc:
        export_service.export_batch_zip(["task_001", "task_002"])

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code
    assert exc.value.details["format"] == "batch_zip"
    assert exc.value.details["failed_tasks"] == [
        {
            "task_id": "task_002",
            "error_code": "EXPORT_VALIDATION_FAILED",
            "reason": "只有待审核或已完成任务可以导出",
            "status": "uploading",
        }
    ]
    assert "batch_zip" not in task_service.get_task("task_001")["export_summary"]["formats"]
    assert not (tmp_path / "exports" / "batch" / "batch-review-export.zip").exists()
```

- [ ] **Step 3: Run export service tests to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py::test_batch_zip_writes_manifest_with_export_summary app/backend/tests/test_export_service.py::test_batch_zip_reports_all_non_exportable_tasks_without_writing_new_zip -q
```

Expected: FAIL because manifest and failed task details are missing.

- [ ] **Step 4: Implement export manifest helpers**

Replace `ExportService.export_batch_zip()` with:

```python
    def export_batch_zip(self, task_ids: list[str]) -> dict:
        models, failed_tasks = self._build_batch_export_models(task_ids)
        if failed_tasks:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="批量导出存在不可导出任务",
                details={"format": "batch_zip", "task_count": len(task_ids), "failed_tasks": failed_tasks},
            )

        filename = "batch-review-export.zip"
        relative_path = f"batch/{filename}"
        batch_dir = os.path.join(self._export_dir, "batch")
        filepath = os.path.join(batch_dir, filename)

        try:
            os.makedirs(batch_dir, exist_ok=True)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(self._build_batch_manifest(models), ensure_ascii=False, indent=2))
                for item in models:
                    archive.writestr(item["json_path"], json.dumps(item["model"], ensure_ascii=False, indent=2))
        except OSError as e:
            raise AppError(ErrorCode.EXPORT_FAILED, message="批量导出文件写入失败", details={"format": "batch_zip", "reason": str(e)})

        for item in models:
            self._task_service.record_export(item["task_id"], format="batch_zip", relative_path=relative_path)

        return {"format": "batch_zip", "path": filepath, "relative_path": relative_path, "filename": filename}
```

Add helpers:

```python
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
            models.append({"task_id": task_id, "status": task["status"], "json_path": f"{task_id}/{task_id}.review.json", "model": model})
        return models, failed_tasks

    def _get_task_status_for_error(self, task_id: str) -> str | None:
        try:
            return self._task_service.get_task(task_id).get("status")
        except AppError:
            return None

    def _build_batch_manifest(self, models: list[dict]) -> dict:
        success_tasks = [
            {
                "task_id": item["task_id"],
                "status": item["status"],
                "json_path": item["json_path"],
                "field_count": len(item["model"].get("fields", [])),
                "schema_version": item["model"].get("schema_version", ""),
                "document_type": item["model"].get("document_type", ""),
            }
            for item in models
        ]
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

- [ ] **Step 5: Update route manifest assertions**

In `test_batch_zip_route_returns_zip_download`, assert `manifest.json` exists and parse it:

```python
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "task_001/task_001.review.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2
```

- [ ] **Step 6: Run export tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py -q
```

Expected before updating the existing file-list assertion: FAIL in `test_batch_zip_exports_json_files_for_multiple_tasks` because it expects only two files.

- [ ] **Step 7: Update existing batch zip file-list assertion**

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

- [ ] **Step 8: Run export tests again**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit export changes**

Run:

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py
git commit -m "补齐批量导出清单和失败报告"
```

Expected: commit succeeds.

---

### Task 8: section_groups prompt OCR risk coverage

**Files:**
- Modify: `app/backend/tests/test_copd_prompts.py`
- Modify: `app/backend/services/copd_extraction/prompts.py`

- [ ] **Step 1: Write failing prompt test**

Append after `test_section_group_prompt_asks_for_short_evidence_and_ocr_audit`:

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
```

- [ ] **Step 2: Run prompt test to verify failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py::test_section_group_prompt_contains_full_ocr_risk_warnings -q
```

Expected: FAIL because current section group prompt lacks some risk text.

- [ ] **Step 3: Update prompt**

Replace the `OCR 风险提示` block in `build_section_group_extraction_prompt()` with:

```python
OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、药名和医学词近形/同音/缺字错读（例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱）、单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason；没有纠偏时 applied=false。
如果同一字段在证据中出现前后矛盾数值，例如脉搏：9次/分但后文心率99次/分，属于前后矛盾数值，不得静默选值，应降低 confidence 并保留原始 evidence_phrase。
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit prompt changes**

Run:

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "补齐分组抽取OCR风险提示"
```

Expected: commit succeeds.

---

### Task 9: PRD status and final verification

**Files:**
- Modify: `docs/PRD任务清单.md`

- [ ] **Step 1: Update PRD task list**

In `docs/PRD任务清单.md`:

- Mark `BE-MVP-05-07 批量导出清单与失败报告` as `[x]`.
- Add a note under `BE-MVP-04-04 慢阻肺专病字段抽取`:

```markdown
  - P2：默认 `section_groups` prompt 已补齐 OCR 风险提示；任务级 `document_type` 已作为后续多文书模板选择、schema/prompt/抽取规则选择的主入口。
```

- Add or update frontend task note under `FE-MVP-02 手机上传页`:

```markdown
- [x] **FE-MVP-02-05 手机端文书模板选择**
  - 范围：上传页展示后端可用文书模板，允许 `uploading` 任务在完成上传前切换模板。
  - 边界：电脑端新建任务弹窗不选择模板；前端不从 OCR 或图片推断模板。
```

- [ ] **Step 2: Run targeted backend tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_document_profiles.py app/backend/tests/test_task_service.py app/backend/tests/test_mobile_upload_routes.py app/backend/tests/test_orchestrator.py app/backend/tests/test_reextraction_service.py app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py app/backend/tests/test_copd_prompts.py -q
```

Expected: PASS.

- [ ] **Step 3: Run targeted frontend tests**

Run:

```bash
npm --prefix app/frontend run test -- MobileCapturePage.test.tsx shared-contracts.test.ts
```

Expected: PASS.

- [ ] **Step 4: Run broader backend smoke**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS. If blocked by environment-specific OCR/GPU assumptions, capture exact failure and keep targeted backend command from Step 2 as the completion gate for this implementation.

- [ ] **Step 5: Commit docs and verify status**

Run:

```bash
git add docs/PRD任务清单.md
git commit -m "更新文书模板与批量导出进度"
git status --short
```

Expected: commit succeeds. `git status --short` shows only unrelated pre-existing dirty files or a clean tree.

---

## Plan Self-Review

- Spec coverage: document profile registry is covered by Tasks 1 and 4; task default and mobile template switching are covered by Tasks 2, 3, and 6; processing and reextract by `document_type` are covered by Tasks 4 and 5; batch manifest and failed task report are covered by Task 7; section_groups prompt risk coverage is covered by Task 8; PRD and verification are covered by Task 9.
- Placeholder scan: no placeholder markers or unspecified “add tests” steps remain.
- Type consistency: plan uses `DocumentProfileRegistry`, `TaskService.change_document_type()`, `ProcessingOrchestrator.field_port_registry`, `ReextractionService.document_profiles`, `updateTaskDocumentType()`, and existing `ExportService`/prompt APIs consistently.
