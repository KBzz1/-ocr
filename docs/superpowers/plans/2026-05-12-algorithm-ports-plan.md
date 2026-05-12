# Algorithm Ports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement BE-05 external algorithm ports, orchestration, fixture success path, result persistence, and failure mapping from `docs/superpowers/specs/2026-05-12-algorithm-ports-design.md`.

**Architecture:** BE-05 depends on the BE-04 task lifecycle implementation. Add an `app/backend/algorithm/` package containing port protocols, default not-configured ports, fixture adapters, and `AlgorithmOrchestrator`; then wire `TaskService.process()` and `retry()` through the orchestrator. Store external results under `results/{task_id}/` and expose read-only result APIs for successful tasks.

**Tech Stack:** Python, Flask, pytest, local JSON persistence via `JsonStore`, existing `TaskService` state transitions.

---

## Prerequisite

This plan must be executed only after BE-04 task lifecycle is present in the working branch. Required files:

- `app/backend/services/task_service.py`
- `app/backend/routes/task.py`
- `app/backend/tests/test_task_service.py`
- `app/backend/tests/test_task_routes.py`

Required `TaskService` methods:

- `process(task_id: str) -> dict`
- `retry(task_id: str) -> dict`
- `mark_ready(task_id: str) -> dict`
- `mark_failed(task_id: str, error_code: str, error_message: str) -> dict`
- `get_task(task_id: str) -> dict`

Do not start Task 1 until those files and methods exist.

Observed scope from `worktree-backend-task-lifecycle` at review time:

- `TaskService.__init__(store: JsonStore)` stores only the JSON store.
- `TaskService.process()` transitions to `processing`, clears previous failure fields, then calls `mark_failed(..., "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")`.
- `TaskService.retry()` only allows `failed -> processing`, clears previous failure fields, then calls the same not-configured failure path.
- `TaskService.mark_ready()` and `mark_failed()` already own task status persistence and history.
- `app/backend/__init__.py` registers `TASK_SERVICE` and `task_bp`.

BE-05 should make the smallest extension to that scope: allow `TaskService` to receive an optional orchestrator, call it after entering `processing`, and keep the existing not-configured fallback when no orchestrator is configured.

## File Structure

- Create: `app/backend/algorithm/__init__.py`
- Create: `app/backend/algorithm/ports.py`
  - Error classes and Protocols for image processing, document parsing, and field extraction.
- Create: `app/backend/algorithm/defaults.py`
  - Default ports that raise `AlgorithmPortNotConfigured`.
- Create: `app/backend/algorithm/fixtures.py`
  - Test-only fixture ports that return fixed external-style results.
- Create: `app/backend/algorithm/orchestrator.py`
  - Reads task/page metadata, calls ports, validates contracts, persists results, and updates task status.
- Modify: `app/backend/services/task_service.py`
  - Accept optional orchestrator and call it from `process()`/`retry()`.
- Create: `app/backend/routes/task_results.py`
  - `GET /api/tasks/{task_id}/document-result`
  - `GET /api/tasks/{task_id}/structured-fields`
- Modify: `app/backend/__init__.py`
  - Register default ports, orchestrator, and result routes.
- Create: `app/backend/tests/test_algorithm_ports.py`
- Create: `app/backend/tests/test_algorithm_orchestrator.py`
- Create: `app/backend/tests/test_task_results_routes.py`

## Task 0: Merge BE-04 Baseline and Verify

**Files:**
- No direct edits unless merge conflicts require resolution.

- [ ] **Step 1: Verify BE-04 files exist**

Run:

```bash
test -f app/backend/services/task_service.py
test -f app/backend/routes/task.py
test -f app/backend/tests/test_task_service.py
test -f app/backend/tests/test_task_routes.py
```

Expected: all commands exit 0.

- [ ] **Step 2: Verify BE-04 backend tests pass**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 3: Verify full backend baseline**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 4: Commit conflict resolutions if any**

If BE-04 had to be merged and conflicts were resolved:

```bash
git add app/backend docs/superpowers
git commit -m "chore: 合并任务生命周期基线"
```

If no files changed, do not create a commit.

## Task 1: Algorithm Port Contracts and Fixture Adapters

**Files:**
- Create: `app/backend/algorithm/__init__.py`
- Create: `app/backend/algorithm/ports.py`
- Create: `app/backend/algorithm/defaults.py`
- Create: `app/backend/algorithm/fixtures.py`
- Create: `app/backend/tests/test_algorithm_ports.py`

- [ ] **Step 1: Write failing port tests**

Create `app/backend/tests/test_algorithm_ports.py`:

```python
import pytest

from app.backend.algorithm.defaults import (
    DefaultDocumentParsingPort,
    DefaultFieldExtractionPort,
    DefaultImageProcessingPort,
)
from app.backend.algorithm.fixtures import (
    FixtureDocumentParsingPort,
    FixtureFieldExtractionPort,
    FixtureImageProcessingPort,
)
from app.backend.algorithm.ports import AlgorithmPortNotConfigured


def test_default_image_processing_port_not_configured():
    port = DefaultImageProcessingPort()

    with pytest.raises(AlgorithmPortNotConfigured):
        port.process(
            {
                "task_id": "task-001",
                "page_id": "page-1",
                "page_no": 1,
                "original_path": "pages/session-1/page-1.jpg",
                "quad_points": None,
                "image_width": 100,
                "image_height": 100,
            }
        )


def test_default_document_parsing_port_not_configured():
    port = DefaultDocumentParsingPort()

    with pytest.raises(AlgorithmPortNotConfigured):
        port.parse({"task_id": "task-001", "pages": []})


def test_default_field_extraction_port_not_configured():
    port = DefaultFieldExtractionPort()

    with pytest.raises(AlgorithmPortNotConfigured):
        port.extract({"task_id": "task-001", "document_result": {}, "schema": {"fields": []}})


def test_fixture_image_processing_returns_processed_path():
    port = FixtureImageProcessingPort()

    result = port.process(
        {
            "task_id": "task-001",
            "page_id": "page-1",
            "page_no": 1,
            "original_path": "pages/session-1/page-1.jpg",
            "quad_points": [[0, 0], [10, 0], [10, 10], [0, 10]],
            "image_width": 100,
            "image_height": 100,
        }
    )

    assert result == {
        "page_id": "page-1",
        "page_no": 1,
        "processed_image_path": "results/task-001/processed/page-1.png",
        "status": "success",
    }


def test_fixture_document_parser_returns_pages_unchanged():
    port = FixtureDocumentParsingPort()

    result = port.parse(
        {
            "task_id": "task-001",
            "pages": [
                {
                    "page_id": "page-1",
                    "page_no": 1,
                    "processed_image_path": "results/task-001/processed/page-1.png",
                }
            ],
        }
    )

    assert result["task_id"] == "task-001"
    assert result["pages"][0]["plain_text"] == "fixture text from external parser"
    assert result["merged_text"] == "fixture text from external parser"


def test_fixture_field_extractor_returns_fields_unchanged():
    port = FixtureFieldExtractionPort()

    result = port.extract(
        {
            "task_id": "task-001",
            "document_result": {"task_id": "task-001", "pages": [], "merged_text": "fixture"},
            "schema": {"version": "fixture", "fields": ["chief_complaint"]},
        }
    )

    assert result == [
        {
            "field_key": "chief_complaint",
            "field_name": "主诉",
            "original_value": "fixture value from external extractor",
            "evidence": "fixture evidence",
            "page_no": 1,
            "confidence": "medium",
        }
    ]
```

- [ ] **Step 2: Run failing port tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_ports.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.backend.algorithm'`.

- [ ] **Step 3: Create algorithm package marker**

Create `app/backend/algorithm/__init__.py`:

```python
"""External algorithm port contracts and orchestration."""
```

- [ ] **Step 4: Implement port contracts**

Create `app/backend/algorithm/ports.py`:

```python
from typing import Protocol


class AlgorithmPortNotConfigured(Exception):
    """External algorithm port is not configured."""


class AlgorithmPortFailed(Exception):
    """External algorithm port raised or reported a runtime failure."""


class AlgorithmContractInvalid(Exception):
    """External algorithm port returned an invalid contract payload."""


class ImageProcessingPort(Protocol):
    def process(self, payload: dict) -> dict:
        ...


class DocumentParsingPort(Protocol):
    def parse(self, payload: dict) -> dict:
        ...


class FieldExtractionPort(Protocol):
    def extract(self, payload: dict) -> list[dict]:
        ...
```

- [ ] **Step 5: Implement default ports**

Create `app/backend/algorithm/defaults.py`:

```python
from .ports import AlgorithmPortNotConfigured


class DefaultImageProcessingPort:
    def process(self, payload: dict) -> dict:
        raise AlgorithmPortNotConfigured("算法模块未配置")


class DefaultDocumentParsingPort:
    def parse(self, payload: dict) -> dict:
        raise AlgorithmPortNotConfigured("算法模块未配置")


class DefaultFieldExtractionPort:
    def extract(self, payload: dict) -> list[dict]:
        raise AlgorithmPortNotConfigured("算法模块未配置")
```

- [ ] **Step 6: Implement fixture ports**

Create `app/backend/algorithm/fixtures.py`:

```python
class FixtureImageProcessingPort:
    def process(self, payload: dict) -> dict:
        return {
            "page_id": payload["page_id"],
            "page_no": payload["page_no"],
            "processed_image_path": f"results/{payload['task_id']}/processed/{payload['page_id']}.png",
            "status": "success",
        }


class FixtureDocumentParsingPort:
    def parse(self, payload: dict) -> dict:
        pages = [
            {
                "page_id": page["page_id"],
                "page_no": page["page_no"],
                "status": "success",
                "plain_text": "fixture text from external parser",
                "blocks": [],
                "tables": [],
            }
            for page in payload["pages"]
        ]
        return {
            "task_id": payload["task_id"],
            "pages": pages,
            "merged_text": "fixture text from external parser",
        }


class FixtureFieldExtractionPort:
    def extract(self, payload: dict) -> list[dict]:
        return [
            {
                "field_key": "chief_complaint",
                "field_name": "主诉",
                "original_value": "fixture value from external extractor",
                "evidence": "fixture evidence",
                "page_no": 1,
                "confidence": "medium",
            }
        ]
```

- [ ] **Step 7: Run port tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_ports.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/backend/algorithm app/backend/tests/test_algorithm_ports.py
git commit -m "feat: 定义外部算法端口契约"
```

## Task 2: AlgorithmOrchestrator Success Path

**Files:**
- Create: `app/backend/algorithm/orchestrator.py`
- Create: `app/backend/tests/test_algorithm_orchestrator.py`

- [ ] **Step 1: Write failing success-path orchestrator tests**

Create `app/backend/tests/test_algorithm_orchestrator.py` with:

```python
from app.backend.algorithm.fixtures import (
    FixtureDocumentParsingPort,
    FixtureFieldExtractionPort,
    FixtureImageProcessingPort,
)
from app.backend.algorithm.orchestrator import AlgorithmOrchestrator
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def write_task_and_pages(tmp_path, status="processing"):
    store = JsonStore(str(tmp_path))
    task = {
        "task_id": "task-001",
        "session_id": "session-001",
        "status": status,
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2,
        "page_order": ["page-1", "page-2"],
        "source": "capture_session",
        "error_code": None,
        "error_message": None,
        "failed_at": None,
        "processing_at": "2026-05-12T10:01:00+00:00",
        "ready_at": None,
        "status_history": [
            {
                "from_status": None,
                "to_status": "uploaded",
                "changed_at": "2026-05-12T10:00:00+00:00",
                "reason": "采集会话完成采集",
            },
            {
                "from_status": "uploaded",
                "to_status": "processing",
                "changed_at": "2026-05-12T10:01:00+00:00",
                "reason": "触发任务处理",
            },
        ],
    }
    store.write("tasks/task-001.json", task)
    for page_no, page_id in enumerate(task["page_order"], start=1):
        store.write(
            f"pages/session-001/{page_id}.json",
            {
                "task_id": None,
                "session_id": "session-001",
                "page_id": page_id,
                "page_no": page_no,
                "original_image_path": f"pages/session-001/{page_id}.jpg",
                "processed_image_path": None,
                "image_width": 100,
                "image_height": 100,
                "quad_points": None,
            },
        )
    return store


def make_orchestrator(tmp_path):
    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    return AlgorithmOrchestrator(
        store=store,
        task_service=task_service,
        image_port=FixtureImageProcessingPort(),
        document_port=FixtureDocumentParsingPort(),
        field_port=FixtureFieldExtractionPort(),
        schema={"version": "fixture", "fields": ["chief_complaint"]},
    )


def test_process_with_fixture_ports_marks_ready(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator(tmp_path)

    result = orchestrator.process("task-001")

    assert result["status"] == "ready_for_review"
    assert result["ready_at"] is not None


def test_process_persists_image_processing_results(tmp_path):
    store = write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator(tmp_path)

    orchestrator.process("task-001")

    image_result = store.read("results/task-001/image-processing.json")
    assert [item["processed_image_path"] for item in image_result["pages"]] == [
        "results/task-001/processed/page-1.png",
        "results/task-001/processed/page-2.png",
    ]
    page = store.read("pages/session-001/page-1.json")
    assert page["processed_image_path"] == "results/task-001/processed/page-1.png"


def test_process_persists_document_result_unchanged(tmp_path):
    store = write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator(tmp_path)

    orchestrator.process("task-001")

    document = store.read("results/task-001/document-result.json")
    assert document["merged_text"] == "fixture text from external parser"
    assert document["pages"][0]["plain_text"] == "fixture text from external parser"


def test_process_persists_structured_fields_unreviewed(tmp_path):
    store = write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator(tmp_path)

    orchestrator.process("task-001")

    fields = store.read("results/task-001/structured-fields.json")
    assert fields["task_id"] == "task-001"
    assert fields["fields"][0]["field_key"] == "chief_complaint"
    assert fields["fields"][0]["original_value"] == "fixture value from external extractor"
    assert fields["fields"][0]["status"] == "unreviewed"
    assert fields["fields"][0]["reviewed_value"] is None
```

- [ ] **Step 2: Run failing success tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_orchestrator.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `app.backend.algorithm.orchestrator`.

- [ ] **Step 3: Implement success-path orchestrator**

Create `app/backend/algorithm/orchestrator.py`:

```python
from .ports import AlgorithmContractInvalid, AlgorithmPortFailed, AlgorithmPortNotConfigured


class AlgorithmOrchestrator:
    def __init__(self, store, task_service, image_port, document_port, field_port, schema):
        self._store = store
        self._task_service = task_service
        self._image_port = image_port
        self._document_port = document_port
        self._field_port = field_port
        self._schema = schema

    def process(self, task_id: str) -> dict:
        try:
            task = self._task_service.get_task(task_id)
            page_payloads = self._load_page_payloads(task)
            image_results = self._process_images(task_id, page_payloads)
            self._store.write(f"results/{task_id}/image-processing.json", {"task_id": task_id, "pages": image_results})
            self._write_processed_paths(task, image_results)

            document_result = self._document_port.parse({"task_id": task_id, "pages": image_results})
            self._validate_document_result(document_result)
            self._store.write(f"results/{task_id}/document-result.json", document_result)
            if any(page["status"] == "failed" for page in document_result["pages"]):
                return self._task_service.mark_failed(task_id, "ALGORITHM_MODULE_FAILED", "文档解析部分页面失败")

            fields = self._field_port.extract(
                {"task_id": task_id, "document_result": document_result, "schema": self._schema}
            )
            persisted_fields = self._prepare_fields(fields)
            self._store.write(f"results/{task_id}/structured-fields.json", {"task_id": task_id, "fields": persisted_fields})
            return self._task_service.mark_ready(task_id)
        except AlgorithmPortNotConfigured as exc:
            return self._task_service.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", str(exc) or "算法模块未配置")
        except AlgorithmContractInvalid as exc:
            return self._task_service.mark_failed(task_id, "ALGORITHM_CONTRACT_INVALID", str(exc) or "算法返回契约非法")
        except AlgorithmPortFailed as exc:
            return self._task_service.mark_failed(task_id, "ALGORITHM_MODULE_FAILED", str(exc) or "算法模块异常")
        except Exception:
            return self._task_service.mark_failed(task_id, "ALGORITHM_MODULE_FAILED", "算法模块异常")

    def _load_page_payloads(self, task: dict) -> list[dict]:
        payloads = []
        for page_no, page_id in enumerate(task["page_order"], start=1):
            page = self._store.read(f"pages/{task['session_id']}/{page_id}.json")
            if page is None:
                raise AlgorithmContractInvalid("页面元数据不存在")
            payloads.append(
                {
                    "task_id": task["task_id"],
                    "page_id": page_id,
                    "page_no": page.get("page_no", page_no),
                    "original_path": page["original_image_path"],
                    "quad_points": page.get("quad_points"),
                    "image_width": page.get("image_width"),
                    "image_height": page.get("image_height"),
                }
            )
        return payloads

    def _process_images(self, task_id: str, page_payloads: list[dict]) -> list[dict]:
        results = []
        for payload in page_payloads:
            result = self._image_port.process(payload)
            self._validate_image_result(payload, result)
            results.append(result)
        return results

    def _validate_image_result(self, payload: dict, result: dict) -> None:
        if result.get("page_id") != payload["page_id"]:
            raise AlgorithmContractInvalid("图像处理返回 page_id 不匹配")
        if result.get("status") != "success":
            raise AlgorithmContractInvalid("图像处理状态非法")
        if not result.get("processed_image_path"):
            raise AlgorithmContractInvalid("图像处理未返回 processed_image_path")

    def _write_processed_paths(self, task: dict, image_results: list[dict]) -> None:
        for result in image_results:
            page_path = f"pages/{task['session_id']}/{result['page_id']}.json"
            page = self._store.read(page_path)
            page["processed_image_path"] = result["processed_image_path"]
            self._store.write(page_path, page)

    def _validate_document_result(self, document_result: dict) -> None:
        pages = document_result.get("pages")
        if not isinstance(pages, list) or not pages:
            raise AlgorithmContractInvalid("文档解析结果 pages 为空")
        for page in pages:
            if "page_id" not in page or "page_no" not in page or "status" not in page:
                raise AlgorithmContractInvalid("文档解析页面结构非法")
            if page["status"] not in {"success", "failed"}:
                raise AlgorithmContractInvalid("文档解析页面状态非法")

    def _prepare_fields(self, fields: list[dict]) -> list[dict]:
        if not isinstance(fields, list) or not fields:
            raise AlgorithmContractInvalid("字段候选为空")
        allowed = set(self._schema.get("fields", []))
        prepared = []
        for field in fields:
            if "field_key" not in field or "original_value" not in field:
                raise AlgorithmContractInvalid("字段候选结构非法")
            if field["field_key"] not in allowed:
                raise AlgorithmContractInvalid("字段候选包含 schema 外字段")
            prepared.append(
                {
                    **field,
                    "status": "unreviewed",
                    "reviewed_value": None,
                    "reviewed_at": None,
                    "review_note": None,
                }
            )
        return prepared
```

- [ ] **Step 4: Run success-path orchestrator tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_orchestrator.py -q
```

Expected: PASS for the four success-path tests.

- [ ] **Step 5: Commit**

```bash
git add app/backend/algorithm/orchestrator.py app/backend/tests/test_algorithm_orchestrator.py
git commit -m "feat: 实现算法端口成功编排"
```

## Task 3: AlgorithmOrchestrator Failure Mapping

**Files:**
- Modify: `app/backend/tests/test_algorithm_orchestrator.py`
- Modify: `app/backend/algorithm/orchestrator.py`

- [ ] **Step 1: Add failing failure-mapping tests**

Append to `app/backend/tests/test_algorithm_orchestrator.py`:

```python
from app.backend.algorithm.ports import AlgorithmPortFailed


class EmptyDocumentPort:
    def parse(self, payload):
        return {"task_id": payload["task_id"], "pages": [], "merged_text": ""}


class PartialFailedDocumentPort:
    def parse(self, payload):
        return {
            "task_id": payload["task_id"],
            "pages": [
                {
                    "page_id": payload["pages"][0]["page_id"],
                    "page_no": payload["pages"][0]["page_no"],
                    "status": "failed",
                    "plain_text": "",
                    "blocks": [],
                    "tables": [],
                }
            ],
            "merged_text": "",
        }


class EmptyFieldPort:
    def extract(self, payload):
        return []


class SchemaExtraFieldPort:
    def extract(self, payload):
        return [{"field_key": "outside_schema", "original_value": "bad"}]


class MissingFieldKeyPort:
    def extract(self, payload):
        return [{"original_value": "bad"}]


class FailingImagePort:
    def process(self, payload):
        raise AlgorithmPortFailed("图像处理异常")


def make_orchestrator_with_ports(tmp_path, image_port, document_port, field_port):
    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    return AlgorithmOrchestrator(
        store=store,
        task_service=task_service,
        image_port=image_port,
        document_port=document_port,
        field_port=field_port,
        schema={"version": "fixture", "fields": ["chief_complaint"]},
    )


def test_image_port_exception_maps_failed(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FailingImagePort(),
        FixtureDocumentParsingPort(),
        FixtureFieldExtractionPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
    assert result["error_message"] == "图像处理异常"


def test_empty_document_pages_marks_contract_invalid(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FixtureImageProcessingPort(),
        EmptyDocumentPort(),
        FixtureFieldExtractionPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"


def test_partial_document_failure_marks_task_failed_and_keeps_result(tmp_path):
    store = write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FixtureImageProcessingPort(),
        PartialFailedDocumentPort(),
        FixtureFieldExtractionPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
    document = store.read("results/task-001/document-result.json")
    assert document["pages"][0]["status"] == "failed"


def test_empty_fields_marks_contract_invalid(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FixtureImageProcessingPort(),
        FixtureDocumentParsingPort(),
        EmptyFieldPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"


def test_schema_extra_field_marks_contract_invalid(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FixtureImageProcessingPort(),
        FixtureDocumentParsingPort(),
        SchemaExtraFieldPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"


def test_missing_required_field_key_marks_contract_invalid(tmp_path):
    write_task_and_pages(tmp_path)
    orchestrator = make_orchestrator_with_ports(
        tmp_path,
        FixtureImageProcessingPort(),
        FixtureDocumentParsingPort(),
        MissingFieldKeyPort(),
    )

    result = orchestrator.process("task-001")

    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
```

- [ ] **Step 2: Run failure-mapping tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_orchestrator.py -q
```

Expected: PASS if Task 2 implementation already includes the failure mapping. If any failure appears, adjust only `AlgorithmOrchestrator` to satisfy the explicit expected status and error codes above.

- [ ] **Step 3: Commit**

```bash
git add app/backend/algorithm/orchestrator.py app/backend/tests/test_algorithm_orchestrator.py
git commit -m "feat: 完成算法失败映射"
```

## Task 4: Wire TaskService Process/Retry Through Orchestrator

**Files:**
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_task_service.py`
- Modify: `app/backend/tests/test_task_routes.py`

- [ ] **Step 1: Add failing TaskService injection tests**

Append to `app/backend/tests/test_task_service.py`:

```python
class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def process(self, task_id):
        self.calls.append(task_id)
        return {"task_id": task_id, "status": "ready_for_review"}


def test_process_delegates_to_orchestrator_after_entering_processing(tmp_path):
    write_task(tmp_path, status="uploaded")
    orchestrator = RecordingOrchestrator()
    service = make_service(tmp_path, orchestrator=orchestrator)

    result = service.process("task-001")

    assert orchestrator.calls == ["task-001"]
    assert result["status"] == "ready_for_review"


def test_retry_delegates_to_orchestrator_after_entering_processing(tmp_path):
    write_task(tmp_path, status="failed")
    orchestrator = RecordingOrchestrator()
    service = make_service(tmp_path, orchestrator=orchestrator)

    result = service.retry("task-001")

    assert orchestrator.calls == ["task-001"]
    assert result["status"] == "ready_for_review"
```

Update the `make_service` helper in `test_task_service.py`:

```python
def make_service(tmp_path, orchestrator=None):
    from app.backend.services.task_service import TaskService

    return TaskService(JsonStore(str(tmp_path)), orchestrator=orchestrator)
```

- [ ] **Step 2: Run failing TaskService injection tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py -q
```

Expected: FAIL because `TaskService.__init__` does not accept `orchestrator`.

- [ ] **Step 3: Modify TaskService**

In `app/backend/services/task_service.py`, update constructor:

```python
    def __init__(self, store: JsonStore, orchestrator=None):
        self._store = store
        self._orchestrator = orchestrator
```

Add:

```python
    def set_orchestrator(self, orchestrator) -> None:
        self._orchestrator = orchestrator
```

In `process()` and `retry()`, after writing the transition into `processing`, replace the fixed `mark_failed(...ALGORITHM_MODULE_NOT_CONFIGURED...)` return with:

```python
        if self._orchestrator is None:
            return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")
        return self._orchestrator.process(task_id)
```

Keep the existing fallback behavior when no orchestrator is configured.

- [ ] **Step 4: Wire orchestrator in app factory**

In `app/backend/__init__.py`, after creating `TASK_SERVICE`, add:

```python
    from .algorithm.defaults import (
        DefaultDocumentParsingPort,
        DefaultFieldExtractionPort,
        DefaultImageProcessingPort,
    )
    from .algorithm.orchestrator import AlgorithmOrchestrator

    task_service = app.config["TASK_SERVICE"]
    algorithm_orchestrator = AlgorithmOrchestrator(
        store=store,
        task_service=task_service,
        image_port=DefaultImageProcessingPort(),
        document_port=DefaultDocumentParsingPort(),
        field_port=DefaultFieldExtractionPort(),
        schema={"version": "fixture", "fields": ["chief_complaint"]},
    )
    task_service.set_orchestrator(algorithm_orchestrator)
    app.config["ALGORITHM_ORCHESTRATOR"] = algorithm_orchestrator
```

This keeps production default behavior as `ALGORITHM_MODULE_NOT_CONFIGURED`.

- [ ] **Step 5: Run task service and route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS. Existing route tests for default process/retry should still return `failed` with `ALGORITHM_MODULE_NOT_CONFIGURED`.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/task_service.py app/backend/__init__.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py
git commit -m "feat: 接入算法处理编排入口"
```

## Task 5: Result Read APIs

**Files:**
- Create: `app/backend/routes/task_results.py`
- Create: `app/backend/tests/test_task_results_routes.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: Write failing result route tests**

Create `app/backend/tests/test_task_results_routes.py`:

```python
import pytest

from app.backend import create_backend_app
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
sessions:
  capture_session_ttl_minutes: 30
uploads:
  max_upload_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def write_task(app, status):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task-001.json",
        {
            "task_id": "task-001",
            "session_id": "session-001",
            "status": status,
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 1,
            "page_order": ["page-1"],
            "source": "capture_session",
        },
    )
    return store


def test_get_document_result_returns_saved_result(client, app):
    store = write_task(app, "ready_for_review")
    store.write(
        "results/task-001/document-result.json",
        {"task_id": "task-001", "pages": [{"page_id": "page-1", "status": "success"}], "merged_text": "fixture"},
    )

    resp = client.get("/api/tasks/task-001/document-result")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["merged_text"] == "fixture"


def test_get_document_result_for_failed_task_returns_error(client, app):
    write_task(app, "failed")

    resp = client.get("/api/tasks/task-001/document-result")

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_get_structured_fields_returns_saved_fields(client, app):
    store = write_task(app, "ready_for_review")
    store.write(
        "results/task-001/structured-fields.json",
        {"task_id": "task-001", "fields": [{"field_key": "chief_complaint", "status": "unreviewed"}]},
    )

    resp = client.get("/api/tasks/task-001/structured-fields")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["fields"][0]["field_key"] == "chief_complaint"


def test_get_structured_fields_for_failed_task_returns_error(client, app):
    write_task(app, "failed")

    resp = client.get("/api/tasks/task-001/structured-fields")

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
```

- [ ] **Step 2: Run failing result route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_results_routes.py -q
```

Expected: FAIL with 404 for result endpoints.

- [ ] **Step 3: Implement result routes**

Create `app/backend/routes/task_results.py`:

```python
from flask import Blueprint, current_app

from ..errors import AppError, ErrorCode
from ..responses import success


task_results_bp = Blueprint("task_results", __name__)


def _store():
    from ..storage.json_store import JsonStore

    return JsonStore(current_app.config["BACKEND_CONFIG"]["storage_dir"])


def _task_service():
    return current_app.config["TASK_SERVICE"]


def _ensure_result_readable(task_id: str) -> None:
    task = _task_service().get_task(task_id)
    if task["status"] not in {"ready_for_review", "confirmed", "exported"}:
        raise AppError(
            ErrorCode.INVALID_TASK_TRANSITION,
            details={"current": task["status"], "target": "read_results"},
        )


@task_results_bp.route("/api/tasks/<task_id>/document-result", methods=["GET"])
def get_document_result(task_id):
    _ensure_result_readable(task_id)
    result = _store().read(f"results/{task_id}/document-result.json")
    if result is None:
        raise AppError(ErrorCode.TASK_NOT_FOUND, message="文档解析结果不存在")
    return success(data=result)


@task_results_bp.route("/api/tasks/<task_id>/structured-fields", methods=["GET"])
def get_structured_fields(task_id):
    _ensure_result_readable(task_id)
    result = _store().read(f"results/{task_id}/structured-fields.json")
    if result is None:
        raise AppError(ErrorCode.TASK_NOT_FOUND, message="结构化字段结果不存在")
    return success(data=result)
```

- [ ] **Step 4: Register result routes**

In `app/backend/__init__.py`, add:

```python
    from .routes.task_results import task_results_bp
    app.register_blueprint(task_results_bp)
```

- [ ] **Step 5: Run result route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_results_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routes/task_results.py app/backend/tests/test_task_results_routes.py app/backend/__init__.py
git commit -m "feat: 增加算法结果读取接口"
```

## Task 6: Full Regression and Boundary Check

**Files:**
- Modify only if verification reveals issues.

- [ ] **Step 1: Run BE-05 focused tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_algorithm_ports.py app/backend/tests/test_algorithm_orchestrator.py app/backend/tests/test_task_results_routes.py -q
```

Expected: PASS.

- [ ] **Step 2: Run lifecycle integration tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 4: Check forbidden implementation patterns**

Run:

```bash
rg -n "pytesseract|opencv|cv2|openai|requests|httpx|规则抽取|正则抽取|透视|裁剪|base64" app/backend
```

Expected: No BE-05 implementation code uses OCR, LLM, network calls, image processing libraries, base64 payload logging, or rule extraction. Test strings and documentation mentions are acceptable only when they assert prohibition or fixture behavior.

- [ ] **Step 5: Check diff hygiene**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Status contains only intended files if anything remains uncommitted.

- [ ] **Step 6: Commit verification fixes if needed**

If Task 6 required fixes:

```bash
git add app/backend docs/superpowers/specs/2026-05-12-algorithm-ports-design.md docs/superpowers/plans/2026-05-12-algorithm-ports-plan.md
git commit -m "test: 完成外部算法端口回归验证"
```

If no files changed, do not create an empty commit.

## Self-Review

- Spec coverage:
  - Port contracts: Task 1.
  - Default not-configured failure: Task 1, Task 4.
  - Fixture success path: Task 1, Task 2.
  - Result persistence: Task 2.
  - Failure mapping: Task 3.
  - TaskService process/retry integration: Task 4.
  - Result read APIs: Task 5.
  - Prohibited OCR/LLM/rule behavior checks: Task 6.
- Placeholder scan:
  - No incomplete implementation instructions are required for execution.
  - The prerequisite is explicit and executable.
- Type consistency:
  - `AlgorithmOrchestrator.process(task_id)` returns the updated task dict from `TaskService`.
  - Port methods match the spec: `process`, `parse`, `extract`.
  - Result file names match the spec: `image-processing.json`, `document-result.json`, `structured-fields.json`.
