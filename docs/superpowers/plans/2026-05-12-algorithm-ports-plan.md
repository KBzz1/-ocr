# 外部算法端口编排实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定义三个外部算法端口接口 + 编排器 + fixture 适配器，替换 TaskService 中硬编码的未配置失败路径。

**Architecture:** 新建 `algorithm_ports/` 包（image_processing.py / document_parsing.py / field_extraction.py / orchestrator.py / fixtures.py）。ProcessingOrchestrator 构造函数注入三个端口和可选 schema_validator，按 image→document→field 顺序串联，任一步失败停止并调 mark_failed。TaskService 通过构造函数接收 orchestrator，process/retry 直接委托。

**Tech Stack:** Python, Flask, pytest, JsonStore。不实现任何算法。

**依赖:** BE-04 合并后 TaskService 已有 process/retry/mark_failed。BE-06 并行开发 schema，BE-05 只接收 dict 透传。

---

## 前置

### Task 0: 确保 BE-04 基线

- [ ] **Step 1: 确认 TaskService 存在且测试通过**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

预期: 全部 PASS。

如果 worktree 是从最新 master 创建的，BE-04 基线已包含。

---

## 阶段一：端口接口

### Task 1: 实现三个端口接口 + 字段结构校验

**Files:**
- Create: `app/backend/services/algorithm_ports/__init__.py`
- Create: `app/backend/services/algorithm_ports/image_processing.py`
- Create: `app/backend/services/algorithm_ports/document_parsing.py`
- Create: `app/backend/services/algorithm_ports/field_extraction.py`
- Create: `app/backend/tests/test_field_extraction_port.py`

- [ ] **Step 1: 写字段结构校验测试（RED）**

创建 `app/backend/tests/test_field_extraction_port.py`:

```python
import pytest
from app.backend.errors import AppError, ErrorCode


class TestValidateFieldCandidates:
    def test_valid_candidates_pass(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        candidates = [
            {"field_key": "chief_complaint", "original_value": "头痛3天", "confidence": 0.95},
            {"field_key": "name", "original_value": "张三", "evidence": "page1"},
        ]
        validate_field_candidates(candidates)

    def test_non_list_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates({"key": "value"})
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_item_not_dict_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates(["not a dict"])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_missing_field_key_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"original_value": "x"}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_empty_field_key_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": "", "original_value": "x"}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_non_string_field_key_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": 123, "original_value": "x"}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_missing_original_value_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": "k"}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_non_string_original_value_raises_contract_invalid(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": "k", "original_value": 123}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_confidence_must_be_number_if_present(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": "k", "original_value": "x", "confidence": "high"}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_evidence_must_be_string_or_none(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        with pytest.raises(AppError) as exc_info:
            validate_field_candidates([{"field_key": "k", "original_value": "x", "evidence": 42}])
        assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code

    def test_evidence_none_is_accepted(self):
        from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates
        validate_field_candidates([{"field_key": "k", "original_value": "x", "evidence": None}])
```

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py -q`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 2: 实现四个模块**

创建 `app/backend/services/algorithm_ports/__init__.py`:

```python
from .image_processing import ImageProcessingPort
from .document_parsing import DocumentParsingPort
from .field_extraction import FieldExtractionPort, validate_field_candidates
from .orchestrator import ProcessingOrchestrator
```

创建 `app/backend/services/algorithm_ports/image_processing.py`:

```python
class ImageProcessingPort:
    def process(self, input: dict) -> dict:
        raise NotImplementedError
```

创建 `app/backend/services/algorithm_ports/document_parsing.py`:

```python
class DocumentParsingPort:
    def parse(self, input: dict) -> dict:
        raise NotImplementedError
```

创建 `app/backend/services/algorithm_ports/field_extraction.py`:

```python
from ...errors import AppError, ErrorCode


class FieldExtractionPort:
    def extract(self, input: dict) -> list[dict]:
        raise NotImplementedError


def validate_field_candidates(candidates: list) -> None:
    if not isinstance(candidates, list):
        raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                       message="字段候选必须是列表")

    for item in candidates:
        if not isinstance(item, dict):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                           message="字段候选项必须是字典")

        field_key = item.get("field_key")
        if not isinstance(field_key, str) or field_key == "":
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                           message="field_key 必须是非空字符串")

        original_value = item.get("original_value")
        if not isinstance(original_value, str):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                           message="original_value 必须是字符串")

        if "confidence" in item:
            confidence = item["confidence"]
            if not isinstance(confidence, (int, float)):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                               message="confidence 必须是数字")

        if "evidence" in item and item["evidence"] is not None:
            if not isinstance(item["evidence"], str):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID,
                               message="evidence 必须是字符串或 None")
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py -q
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/algorithm_ports/ app/backend/tests/test_field_extraction_port.py
git commit -m "feat: 定义算法端口接口与字段结构校验"
```

---

## 阶段二：编排器 + TaskService 改造

### Task 2: 实现 ProcessingOrchestrator + 改造 TaskService

**Files:**
- Create: `app/backend/services/algorithm_ports/orchestrator.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/__init__.py`
- Create: `app/backend/tests/test_orchestrator.py`

> 编排器需要从 session JSON 读取 pages 获取 upload_ref 映射。它接收 `session_service` 参数而非直接读文件。

- [ ] **Step 1: 写编排器测试（RED）**

创建 `app/backend/tests/test_orchestrator.py`:

```python
import json
import os
import pytest
from app.backend.storage.json_store import JsonStore


def _make_service(tmp_path, image_port=None, doc_port=None, field_port=None):
    from app.backend.services.task_service import TaskService
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator

    store = JsonStore(str(tmp_path))
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=image_port,
        doc_port=doc_port,
        field_port=field_port,
    )
    return TaskService(store=store, orchestrator=orchestrator)


def _write_task_and_session(store, task_id="task-001", session_id="session-001",
                             page_order=None, page_data=None):
    """写入任务和关联的会话/页面元数据。"""
    if page_order is None:
        page_order = ["page-1"]
    if page_data is None:
        page_data = {
            "page-1": {"original_image_path": "/tmp/p1.jpg", "quad_points": None,
                        "image_width": 1920, "image_height": 1080},
        }

    # 写入页面元数据
    for pid, meta in page_data.items():
        store.write(f"pages/{session_id}/{pid}.json", {
            "page_id": pid, "session_id": session_id, "page_no": 1,
            "original_image_path": meta["original_image_path"],
            "processed_image_path": None,
            "image_width": meta["image_width"],
            "image_height": meta["image_height"],
            "quad_points": meta.get("quad_points"),
            "uploaded_at": "2026-05-12T10:00:00+00:00",
        })

    # 写入会话
    pages = [{"page_id": pid, "page_no": i + 1,
              "upload_ref": f"pages/{session_id}/{pid}.json",
              "created_at": "2026-05-12T10:00:00+00:00",
              "page_id": pid}
             for i, pid in enumerate(page_order)]
    store.write(f"sessions/{session_id}.json", {
        "session_id": session_id, "status": "locked",
        "created_at": "2026-05-12T10:00:00+00:00",
        "expires_at": "2026-05-12T10:30:00+00:00",
        "qr_code_url": None, "page_count": len(page_order),
        "pages": pages, "locked_at": "2026-05-12T10:05:00+00:00",
        "task_id": task_id,
    })

    # 写入任务
    store.write(f"tasks/{task_id}.json", {
        "task_id": task_id, "session_id": session_id,
        "status": "processing", "created_at": "2026-05-12T10:05:00+00:00",
        "page_count": len(page_order), "page_order": page_order,
        "source": "capture_session",
        "error_code": None, "error_message": None, "failed_at": None,
        "processing_at": "2026-05-12T10:05:00+00:00", "ready_at": None,
        "status_history": [
            {"from_status": "uploaded", "to_status": "processing",
             "changed_at": "2026-05-12T10:05:00+00:00", "reason": "触发任务处理"},
        ],
    })


class FixtureImagePort:
    def __init__(self, should_fail=False):
        self._should_fail = should_fail
        self.calls = []

    def process(self, input):
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture image error")
        return {"processed_path": f"/tmp/processed/{input['page_id']}.jpg"}


class FixtureDocPort:
    def __init__(self, should_fail=False, return_empty=False, partial_fail_page=None):
        self._should_fail = should_fail
        self._return_empty = return_empty
        self._partial_fail_page = partial_fail_page
        self.calls = []

    def parse(self, input):
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture doc error")
        if self._return_empty:
            return {"pages": [], "merged_text": ""}
        pages = []
        for p in input["pages"]:
            status = "failed" if p["page_id"] == self._partial_fail_page else "success"
            pages.append({"page_id": p["page_id"], "page_no": p["page_no"],
                          "status": status, "text": f"text_{p['page_id']}", "blocks": [], "tables": []})
        return {"pages": pages, "merged_text": "merged"}


class FixtureFieldPort:
    def __init__(self, should_fail=False, return_empty=False):
        self._should_fail = should_fail
        self._return_empty = return_empty
        self.calls = []

    def extract(self, input):
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture field error")
        if self._return_empty:
            return []
        return [{"field_key": "test", "original_value": "val", "confidence": 0.9}]


class TestOrchestrator:
    def test_no_ports_configured_marks_failed(self, tmp_path):
        service = _make_service(tmp_path)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["details"]["failed_stage"] == "image_processing"

    def test_all_ports_configured_flow_to_ready(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        service = _make_service(tmp_path, image_port=img, doc_port=doc, field_port=field)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "ready_for_review"
        assert result["ready_at"] is not None
        assert len(img.calls) == 1
        assert len(doc.calls) == 1
        assert len(field.calls) == 1

    def test_image_fails_skips_doc_and_field(self, tmp_path):
        img = FixtureImagePort(should_fail=True)
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        service = _make_service(tmp_path, image_port=img, doc_port=doc, field_port=field)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["failed_stage"] == "image_processing"
        assert doc.calls == []
        assert field.calls == []

    def test_doc_fails_skips_field(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(should_fail=True)
        field = FixtureFieldPort()
        service = _make_service(tmp_path, image_port=img, doc_port=doc, field_port=field)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["failed_stage"] == "document_parsing"
        assert field.calls == []

    def test_doc_empty_pages_marks_failed(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(return_empty=True)
        service = _make_service(tmp_path, image_port=img, doc_port=doc)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["failed_stage"] == "document_parsing"

    def test_field_empty_candidates_marks_failed(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort(return_empty=True)
        service = _make_service(tmp_path, image_port=img, doc_port=doc, field_port=field)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["failed_stage"] == "field_extraction"

    def test_partial_page_failure_marks_task_failed(self, tmp_path):
        img = FixtureImagePort()
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store, page_order=["page-1", "page-2"],
                                 page_data={
                                     "page-1": {"original_image_path": "/tmp/p1.jpg",
                                                 "quad_points": None, "image_width": 1920, "image_height": 1080},
                                     "page-2": {"original_image_path": "/tmp/p2.jpg",
                                                 "quad_points": None, "image_width": 1920, "image_height": 1080},
                                 })
        doc = FixtureDocPort(partial_fail_page="page-1")
        service = _make_service(tmp_path, image_port=img, doc_port=doc)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["failed_stage"] == "document_parsing"

    def test_results_persisted_to_results_dir(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        service = _make_service(tmp_path, image_port=img, doc_port=doc, field_port=field)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store)
        task = store.read("tasks/task-001.json")

        service._orchestrator.run(task, service)

        assert store.exists("results/task-001/image_result.json")
        assert store.exists("results/task-001/document_result.json")
        assert store.exists("results/task-001/field_candidates.json")

    def test_missing_page_metadata_marks_failed(self, tmp_path):
        img = FixtureImagePort()
        service = _make_service(tmp_path, image_port=img)
        store = JsonStore(str(tmp_path))
        _write_task_and_session(store, page_data={})  # no page metadata

        task = store.read("tasks/task-001.json")
        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["failed_stage"] == "image_processing"
```

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q`
Expected: FAIL — ModuleNotFoundError for orchestrator

- [ ] **Step 2: 实现编排器**

创建 `app/backend/services/algorithm_ports/orchestrator.py`:

```python
from ...storage.json_store import JsonStore


class ProcessingOrchestrator:
    def __init__(
        self,
        store: JsonStore,
        image_port=None,
        doc_port=None,
        field_port=None,
        schema_validator=None,
    ):
        self._store = store
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port
        self._schema_validator = schema_validator

    def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
        task_id = task["task_id"]

        # --- image processing ---
        if self._image_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED",
                "图像处理模块未配置",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "module_not_configured"},
            )

        image_inputs = self._build_image_inputs(task)
        if image_inputs is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID",
                "页面元数据缺失",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "page_metadata_missing"},
            )

        processed_pages = []
        for img_input in image_inputs:
            try:
                result = self._image_port.process(img_input)
                processed_pages.append({
                    "page_id": img_input["page_id"],
                    "page_no": img_input["page_no"],
                    "processed_path": result["processed_path"],
                })
            except Exception:
                return task_service.mark_failed(
                    task_id, "ALGORITHM_MODULE_FAILED",
                    "图像处理模块异常",
                    stage="image_processing",
                    details={"stage": "image_processing", "reason": "module_exception"},
                )

        self._store.write(f"results/{task_id}/image_result.json", {
            "task_id": task_id, "stage": "image_processing", "status": "success",
            "pages": [{"page_id": p["page_id"], "original_path": img["original_path"],
                        "processed_path": p["processed_path"]}
                      for p, img in zip(processed_pages, image_inputs)],
        })

        # --- document parsing ---
        if self._doc_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED",
                "文档解析模块未配置",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_not_configured"},
            )

        doc_input = {
            "task_id": task_id,
            "image_paths": [p["processed_path"] for p in processed_pages],
            "pages": [{"page_id": p["page_id"], "page_no": p["page_no"],
                        "processed_path": p["processed_path"]}
                      for p in processed_pages],
        }
        try:
            doc_result = self._doc_port.parse(doc_input)
        except Exception:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED",
                "文档解析模块异常",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "module_exception"},
            )

        pages = doc_result.get("pages", [])
        if not pages:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID",
                "文档解析结果为空",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "empty_result"},
            )

        has_failure = any(p.get("status") == "failed" for p in pages)
        self._store.write(f"results/{task_id}/document_result.json", {
            "task_id": task_id, "stage": "document_parsing",
            "status": "success" if not has_failure else "partial_failure",
            "pages": pages, "merged_text": doc_result.get("merged_text", ""),
        })

        if has_failure:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED",
                "部分页面解析失败",
                stage="document_parsing",
                details={"stage": "document_parsing", "reason": "partial_page_failure"},
            )

        # --- field extraction ---
        if self._field_port is None:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_NOT_CONFIGURED",
                "字段抽取模块未配置",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_not_configured"},
            )

        if not isinstance(schema, dict):
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID",
                "schema 缺失或非法",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "schema_missing"},
            )

        field_input = {
            "task_id": task_id,
            "document_result": doc_result,
            "schema": schema,
        }
        try:
            candidates = self._field_port.extract(field_input)
        except Exception:
            return task_service.mark_failed(
                task_id, "ALGORITHM_MODULE_FAILED",
                "字段抽取模块异常",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "module_exception"},
            )

        if not candidates:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID",
                "字段候选结果为空",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "empty_result"},
            )

        from .field_extraction import validate_field_candidates
        try:
            validate_field_candidates(candidates)
        except Exception as e:
            return task_service.mark_failed(
                task_id, "ALGORITHM_CONTRACT_INVALID",
                f"字段候选结构非法: {e.message}",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "contract_invalid"},
            )

        self._store.write(f"results/{task_id}/field_candidates.json", {
            "task_id": task_id, "stage": "field_extraction", "status": "success",
            "candidates": candidates,
        })

        return task_service.mark_ready(task_id)

    def _build_image_inputs(self, task: dict) -> list | None:
        session_id = task.get("session_id")
        page_order = task.get("page_order", [])
        if not session_id or not page_order:
            return None

        session = self._store.read(f"sessions/{session_id}.json")
        if session is None:
            return None

        page_by_id = {p["page_id"]: p for p in session.get("pages", [])}

        inputs = []
        for page_no, page_id in enumerate(page_order, start=1):
            session_page = page_by_id.get(page_id)
            if not session_page or not session_page.get("upload_ref"):
                return None

            meta = self._store.read(session_page["upload_ref"])
            if meta is None:
                return None

            original_path = meta.get("original_image_path")
            if not original_path:
                return None
            if not isinstance(meta.get("image_width"), int) or not isinstance(meta.get("image_height"), int):
                return None

            inputs.append({
                "task_id": task["task_id"],
                "page_id": page_id,
                "page_no": page_no,
                "original_path": original_path,
                "quad_points": meta.get("quad_points"),
                "image_width": meta["image_width"],
                "image_height": meta["image_height"],
            })
        return inputs
```

- [ ] **Step 3: 改造 TaskService**

修改 `task_service.py`：

构造函数增加 `orchestrator` 参数：

```python
class TaskService:
    def __init__(self, store: JsonStore, orchestrator=None):
        self._store = store
        self._orchestrator = orchestrator
```

`process()` 替换固定失败为委托：

```python
    def process(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "触发任务处理")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        if self._orchestrator:
            return self._orchestrator.run(task, self)
        return self.mark_failed(
            task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置",
            stage="processing",
            details={"stage": "processing", "reason": "module_not_configured"},
        )
```

`retry()` 同样：

```python
    def retry(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.FAILED.value:
            raise AppError(ErrorCode.INVALID_TASK_TRANSITION,
                           message="仅 failed 状态可重试",
                           details={"current": task["status"]})
        task = self._transition(task, TaskStatus.PROCESSING.value, "失败任务重试")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        if self._orchestrator:
            return self._orchestrator.run(task, self)
        return self.mark_failed(
            task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置",
            stage="processing",
            details={"stage": "processing", "reason": "module_not_configured"},
        )
```

`mark_failed` 扩展 `details` 参数：

```python
    def mark_failed(self, task_id: str, error_code: str, message: str,
                    stage: str = "processing", details: dict | None = None) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.FAILED.value, message)
        task["error_code"] = error_code
        task["error_message"] = message
        task["failed_at"] = self._now()
        task["details"] = details or {"failed_stage": stage}
        self._write_task(task)
        return task
```

- [ ] **Step 4: 更新 __init__.py**

```python
    from .services.algorithm_ports.orchestrator import ProcessingOrchestrator

    orchestrator = ProcessingOrchestrator(store=store)
    app.config["TASK_SERVICE"] = TaskService(store=store, orchestrator=orchestrator)
```

- [ ] **Step 5: 运行编排器测试确认 GREEN**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q
```

- [ ] **Step 6: 运行全部测试确认无回归**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

- [ ] **Step 7: 提交**

```bash
git add app/backend/services/algorithm_ports/orchestrator.py app/backend/services/task_service.py app/backend/__init__.py app/backend/tests/test_orchestrator.py
git commit -m "feat: 实现处理编排器并替换 TaskService 硬编码失败路径"
```

---

## 阶段三：Fixture 适配器

### Task 3: 实现测试用 Fixture 适配器

**Files:**
- Create: `app/backend/services/algorithm_ports/fixtures.py`
- Create: `app/backend/tests/test_image_processing_port.py`
- Create: `app/backend/tests/test_document_parsing_port.py`

- [ ] **Step 1: 实现 Fixture 适配器**

创建 `app/backend/services/algorithm_ports/fixtures.py`:

```python
from .image_processing import ImageProcessingPort
from .document_parsing import DocumentParsingPort
from .field_extraction import FieldExtractionPort


class FixtureImagePort(ImageProcessingPort):
    def __init__(self, processed_dir="/tmp/processed", should_fail=False):
        self._processed_dir = processed_dir
        self._should_fail = should_fail
        self.calls = []

    def process(self, input: dict) -> dict:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture image processing failure")
        return {"processed_path": f"{self._processed_dir}/{input['page_id']}_processed.jpg"}


class FixtureDocPort(DocumentParsingPort):
    def __init__(self, pages=None, merged_text="merged text",
                 partial_fail_page_id=None, should_fail=False, return_empty=False):
        self._preset_pages = pages
        self._merged_text = merged_text
        self._partial_fail_page_id = partial_fail_page_id
        self._should_fail = should_fail
        self._return_empty = return_empty
        self.calls = []

    def parse(self, input: dict) -> dict:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture document parsing failure")
        if self._return_empty:
            return {"pages": [], "merged_text": ""}
        if self._preset_pages:
            return {"pages": self._preset_pages, "merged_text": self._merged_text}
        pages = []
        for p in input.get("pages", []):
            status = "failed" if p["page_id"] == self._partial_fail_page_id else "success"
            pages.append({
                "page_id": p["page_id"], "page_no": p["page_no"],
                "status": status,
                "text": f"text of {p['page_id']}", "blocks": [], "tables": [],
            })
        return {"pages": pages, "merged_text": self._merged_text}


class FixtureFieldPort(FieldExtractionPort):
    def __init__(self, candidates=None, should_fail=False, return_empty=False):
        self._candidates = candidates or [
            {"field_key": "chief_complaint", "original_value": "头痛3天",
             "evidence": "page 1 line 2", "confidence": 0.95},
        ]
        self._should_fail = should_fail
        self._return_empty = return_empty
        self.calls = []

    def extract(self, input: dict) -> list[dict]:
        self.calls.append(input)
        if self._should_fail:
            raise RuntimeError("fixture field extraction failure")
        if self._return_empty:
            return []
        return list(self._candidates)
```

- [ ] **Step 2: 写端口契约测试**

创建 `app/backend/tests/test_image_processing_port.py`:

```python
from app.backend.services.algorithm_ports.fixtures import FixtureImagePort


class TestImageProcessingPort:
    def test_fixture_returns_processed_path(self):
        port = FixtureImagePort()
        result = port.process({
            "task_id": "t1", "page_id": "p1", "page_no": 1,
            "original_path": "/tmp/orig.jpg", "quad_points": None,
            "image_width": 1920, "image_height": 1080,
        })
        assert result["processed_path"].endswith("p1_processed.jpg")

    def test_fixture_should_fail_raises(self):
        port = FixtureImagePort(should_fail=True)
        with pytest.raises(RuntimeError, match="fixture image processing failure"):
            port.process({"task_id": "t1", "page_id": "p1", "page_no": 1,
                          "original_path": "/tmp/orig.jpg", "quad_points": None,
                          "image_width": 1920, "image_height": 1080})

    def test_fixture_records_calls(self):
        port = FixtureImagePort()
        port.process({"task_id": "t1", "page_id": "p1", "page_no": 1,
                       "original_path": "/tmp/orig.jpg", "quad_points": None,
                       "image_width": 1920, "image_height": 1080})
        assert len(port.calls) == 1
        assert port.calls[0]["page_id"] == "p1"
```

创建 `app/backend/tests/test_document_parsing_port.py`:

```python
from app.backend.services.algorithm_ports.fixtures import FixtureDocPort


class TestDocumentParsingPort:
    def test_fixture_returns_pages(self):
        port = FixtureDocPort()
        result = port.parse({
            "task_id": "t1",
            "image_paths": ["/tmp/p1.jpg"],
            "pages": [{"page_id": "p1", "page_no": 1, "processed_path": "/tmp/p1.jpg"}],
        })
        assert len(result["pages"]) == 1
        assert result["pages"][0]["status"] == "success"

    def test_fixture_return_empty(self):
        port = FixtureDocPort(return_empty=True)
        result = port.parse({"task_id": "t1", "image_paths": [], "pages": []})
        assert result["pages"] == []

    def test_fixture_should_fail_raises(self):
        port = FixtureDocPort(should_fail=True)
        with pytest.raises(RuntimeError):
            port.parse({"task_id": "t1", "image_paths": [], "pages": []})

    def test_fixture_partial_failure(self):
        port = FixtureDocPort(partial_fail_page_id="p1")
        result = port.parse({
            "task_id": "t1",
            "image_paths": ["/tmp/p1.jpg", "/tmp/p2.jpg"],
            "pages": [{"page_id": "p1", "page_no": 1, "processed_path": "/tmp/p1.jpg"},
                       {"page_id": "p2", "page_no": 2, "processed_path": "/tmp/p2.jpg"}],
        })
        statuses = [p["status"] for p in result["pages"]]
        assert "failed" in statuses
        assert "success" in statuses
```

- [ ] **Step 3: 运行测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_image_processing_port.py app/backend/tests/test_document_parsing_port.py -q
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/algorithm_ports/fixtures.py app/backend/tests/test_image_processing_port.py app/backend/tests/test_document_parsing_port.py
git commit -m "feat: 新增 Fixture 适配器与端口契约测试"
```

---

## 阶段四：收尾

### Task 4: 全量回归 + 算法泄漏检查

- [ ] **Step 1: 运行全量测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

- [ ] **Step 2: 检查无算法实现泄漏**

```bash
grep -rn "ocr\|llm\|extract\|规则抽取\|裁剪\|透视\|base64\|requests\|httpx\|openai\|PIL\|cv2\|pytesseract" app/backend/services/algorithm_ports/ || echo "PASS: no algorithm implementation found"
```

- [ ] **Step 3: 提交**

```bash
git commit --allow-empty -m "chore: BE-05 外部算法端口编排 A-lite 实现完成"
```

---

## 自审

- Spec 覆盖: 三个端口 + 编排器 + fixture + TaskService 改造 + 多页处理 + 失败映射全部覆盖。
- 无占位符: 无 TBD/TODO。
- 类型一致: 编排器 `run(task, task_service, schema)` 签名与 TaskService 调用一致。`mark_failed` 新增 `details` 参数向后兼容。
