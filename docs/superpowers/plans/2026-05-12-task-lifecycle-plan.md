# Task Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PR-BE-004 A-lite task lifecycle APIs and service behavior from `docs/superpowers/specs/2026-05-12-task-lifecycle-design.md`.

**Architecture:** Add a focused `TaskService` that owns task JSON normalization, state transitions, history, failure metadata, list/detail queries, and A-lite process/retry failure behavior. Add a `task_bp` route module that exposes `/api/tasks`, `/api/tasks/<task_id>`, `/process`, and `/retry`, registered by the existing Flask app factory. Extend `JsonStore` with a safe directory JSON listing helper so task listing does not reach into private storage internals.

**Tech Stack:** Python, Flask, pytest, local JSON persistence through `app/backend/storage/json_store.py`.

---

## File Structure

- Modify: `app/backend/storage/json_store.py`
  - Add `list_json(relative_dir: str) -> list[dict]` for safe, sorted JSON reads below the configured storage root.
- Modify: `app/backend/tests/test_json_store.py`
  - Cover sorted JSON listing, missing directory, and non-JSON exclusion.
- Create: `app/backend/services/task_service.py`
  - Implement normalization, list/detail, transition guard, history, `process`, `retry`, `mark_ready`, `mark_failed`, `mark_confirmed`, and `mark_exported`.
- Create: `app/backend/tests/test_task_service.py`
  - Unit tests for state transitions, legacy Task stubs, history, failure metadata, list/detail behavior, and A-lite algorithm-not-configured failure.
- Create: `app/backend/routes/task.py`
  - Implement task API endpoints and shape success payloads.
- Create: `app/backend/tests/test_task_routes.py`
  - API tests for list/detail/process/retry success and error cases.
- Modify: `app/backend/__init__.py`
  - Instantiate `TaskService`, store it in `app.config["TASK_SERVICE"]`, and register `task_bp`.
- Modify: `app/backend/routes/__init__.py`
  - Add `_get_task_service()` helper if route helpers are centralized there.

## Task 1: JsonStore Safe JSON Listing

**Files:**
- Modify: `app/backend/storage/json_store.py`
- Modify: `app/backend/tests/test_json_store.py`

- [ ] **Step 1: Write failing tests for JSON listing**

Append to `app/backend/tests/test_json_store.py`:

```python
class TestJsonStoreListJson:
    def test_list_json_returns_sorted_json_documents(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("tasks/b.json", {"task_id": "b"})
        store.write("tasks/a.json", {"task_id": "a"})
        (tmp_path / "tasks" / "note.txt").write_text("skip", encoding="utf-8")

        result = store.list_json("tasks")

        assert [item["task_id"] for item in result] == ["a", "b"]

    def test_list_json_missing_directory_returns_empty_list(self, tmp_path):
        store = JsonStore(str(tmp_path))

        assert store.list_json("tasks") == []

    def test_list_json_rejects_absolute_path(self, tmp_path):
        store = JsonStore(str(tmp_path))

        with pytest.raises(ValueError):
            store.list_json(str(tmp_path / "tasks"))
```

- [ ] **Step 2: Run the failing JsonStore tests**

Run:

```bash
python -m pytest app/backend/tests/test_json_store.py::TestJsonStoreListJson -q
```

Expected: FAIL with `AttributeError: 'JsonStore' object has no attribute 'list_json'`.

- [ ] **Step 3: Implement `list_json`**

Add this method to `JsonStore` in `app/backend/storage/json_store.py`:

```python
    def list_json(self, relative_dir: str):
        directory = self._resolve(relative_dir)
        if not os.path.isdir(directory):
            return []

        items = []
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(relative_dir, name)
            items.append(self.read(path))
        return items
```

- [ ] **Step 4: Run JsonStore tests**

Run:

```bash
python -m pytest app/backend/tests/test_json_store.py -q
```

Expected: PASS for all JsonStore tests.

- [ ] **Step 5: Commit**

```bash
git add app/backend/storage/json_store.py app/backend/tests/test_json_store.py
git commit -m "feat: 增加 JSON 存储目录列举能力"
```

## Task 2: TaskService Normalization, Queries, and State Machine

**Files:**
- Create: `app/backend/services/task_service.py`
- Create: `app/backend/tests/test_task_service.py`

- [ ] **Step 1: Write failing TaskService tests**

Create `app/backend/tests/test_task_service.py` with:

```python
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path):
    from app.backend.services.task_service import TaskService

    return TaskService(JsonStore(str(tmp_path)))


def write_task(tmp_path, task_id="task-001", status="uploaded", **overrides):
    task = {
        "task_id": task_id,
        "session_id": "session-001",
        "status": status,
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2,
        "page_order": ["page-1", "page-2"],
        "source": "capture_session",
    }
    task.update(overrides)
    JsonStore(str(tmp_path)).write(f"tasks/{task_id}.json", task)
    return task


class TestTaskServiceQueries:
    def test_legacy_task_stub_is_normalized(self, tmp_path):
        write_task(tmp_path)
        service = make_service(tmp_path)

        task = service.get_task("task-001")

        assert task["error_code"] is None
        assert task["error_message"] is None
        assert task["failed_at"] is None
        assert task["processing_at"] is None
        assert task["ready_at"] is None
        assert task["page_summary"] == {"page_count": 2, "page_order": ["page-1", "page-2"]}
        assert task["document_summary"] is None
        assert task["review_summary"] == {
            "status": None,
            "unreviewed_count": None,
            "suspicious_count": None,
        }
        assert task["export_summary"] == {"last_exported_at": None, "formats": []}
        assert task["status_history"] == [
            {
                "from_status": None,
                "to_status": "uploaded",
                "changed_at": "2026-05-12T10:00:00+00:00",
                "reason": "采集会话完成采集",
            }
        ]

    def test_list_tasks_returns_all_when_no_filter(self, tmp_path):
        write_task(tmp_path, task_id="task-b", status="failed")
        write_task(tmp_path, task_id="task-a", status="uploaded")
        service = make_service(tmp_path)

        tasks = service.list_tasks()

        assert [task["task_id"] for task in tasks] == ["task-a", "task-b"]
        assert tasks[0] == {
            "task_id": "task-a",
            "session_id": "session-001",
            "status": "uploaded",
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 2,
        }

    def test_list_tasks_filters_by_status(self, tmp_path):
        write_task(tmp_path, task_id="task-1", status="uploaded")
        write_task(tmp_path, task_id="task-2", status="failed")
        service = make_service(tmp_path)

        tasks = service.list_tasks(status="failed")

        assert [task["task_id"] for task in tasks] == ["task-2"]

    def test_list_tasks_unknown_status_returns_empty_list(self, tmp_path):
        write_task(tmp_path, task_id="task-1", status="uploaded")
        service = make_service(tmp_path)

        assert service.list_tasks(status="unknown") == []

    def test_get_nonexistent_task_raises_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.get_task("missing")

        assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND.code


class TestTaskServiceTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("created", "uploading"),
            ("created", "failed"),
            ("uploading", "uploaded"),
            ("uploading", "failed"),
            ("uploaded", "processing"),
            ("uploaded", "failed"),
            ("processing", "ready_for_review"),
            ("processing", "failed"),
            ("failed", "processing"),
            ("ready_for_review", "confirmed"),
            ("ready_for_review", "processing"),
            ("ready_for_review", "failed"),
            ("confirmed", "exported"),
        ],
    )
    def test_valid_transitions_match_state_enums(self, tmp_path, current, target):
        service = make_service(tmp_path)

        service._validate_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("uploaded", "confirmed"),
            ("processing", "uploaded"),
            ("failed", "confirmed"),
            ("confirmed", "failed"),
            ("exported", "failed"),
        ],
    )
    def test_invalid_transitions_raise_invalid_transition(self, tmp_path, current, target):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service._validate_transition(current, target)

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
        assert exc_info.value.details == {"current": current, "target": target}

    def test_process_without_algorithm_marks_failed(self, tmp_path):
        write_task(tmp_path, status="uploaded")
        service = make_service(tmp_path)

        result = service.process("task-001")

        assert result["status"] == "failed"
        assert result["processing_at"] is not None
        assert result["failed_at"] is not None
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["error_message"] == "算法模块未配置"
        assert [entry["to_status"] for entry in result["status_history"]] == [
            "uploaded",
            "processing",
            "failed",
        ]

    def test_process_invalid_state_raises_invalid_transition(self, tmp_path):
        write_task(tmp_path, status="confirmed")
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.process("task-001")

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code

    def test_retry_without_algorithm_marks_failed_again(self, tmp_path):
        write_task(
            tmp_path,
            status="failed",
            error_code="ALGORITHM_MODULE_FAILED",
            error_message="旧错误",
            failed_at="2026-05-12T10:01:00+00:00",
            status_history=[
                {
                    "from_status": None,
                    "to_status": "uploaded",
                    "changed_at": "2026-05-12T10:00:00+00:00",
                    "reason": "采集会话完成采集",
                },
                {
                    "from_status": "processing",
                    "to_status": "failed",
                    "changed_at": "2026-05-12T10:01:00+00:00",
                    "reason": "旧错误",
                },
            ],
        )
        service = make_service(tmp_path)

        result = service.retry("task-001")

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["error_message"] == "算法模块未配置"
        assert result["status_history"][-2]["from_status"] == "failed"
        assert result["status_history"][-2]["to_status"] == "processing"
        assert result["status_history"][-1]["from_status"] == "processing"
        assert result["status_history"][-1]["to_status"] == "failed"

    def test_mark_ready_sets_ready_at(self, tmp_path):
        write_task(tmp_path, status="processing")
        service = make_service(tmp_path)

        result = service.mark_ready("task-001")

        assert result["status"] == "ready_for_review"
        assert result["ready_at"] is not None

    def test_mark_failed_saves_error_info(self, tmp_path):
        write_task(tmp_path, status="processing")
        service = make_service(tmp_path)

        result = service.mark_failed("task-001", "ALGORITHM_MODULE_FAILED", "算法模块异常")

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["error_message"] == "算法模块异常"
        assert result["failed_at"] is not None

    def test_mark_confirmed_and_exported(self, tmp_path):
        write_task(tmp_path, status="ready_for_review")
        service = make_service(tmp_path)

        confirmed = service.mark_confirmed("task-001")
        exported = service.mark_exported("task-001")

        assert confirmed["status"] == "confirmed"
        assert exported["status"] == "exported"
```

- [ ] **Step 2: Run failing TaskService tests**

Run:

```bash
python -m pytest app/backend/tests/test_task_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.backend.services.task_service'`.

- [ ] **Step 3: Implement TaskService**

Create `app/backend/services/task_service.py`:

```python
from datetime import datetime, timezone

from ..enums import TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class TaskService:
    def __init__(self, store: JsonStore):
        self._store = store

    def list_tasks(self, status: str | None = None) -> list[dict]:
        tasks = [self._normalize_task(task) for task in self._store.list_json("tasks")]
        if status is not None:
            tasks = [task for task in tasks if task["status"] == status]
        return [
            {
                "task_id": task["task_id"],
                "session_id": task["session_id"],
                "status": task["status"],
                "created_at": task["created_at"],
                "page_count": task["page_count"],
            }
            for task in sorted(tasks, key=lambda item: item["task_id"])
        ]

    def get_task(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        return self._normalize_task(task)

    def process(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "触发任务处理")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")

    def retry(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "失败任务重试")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")

    def mark_ready(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.READY_FOR_REVIEW.value, "算法处理完成")
        task["ready_at"] = self._now()
        self._write_task(task)
        return task

    def mark_failed(self, task_id: str, error_code: str, error_message: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.FAILED.value, error_message)
        task["error_code"] = error_code
        task["error_message"] = error_message
        task["failed_at"] = self._now()
        self._write_task(task)
        return task

    def mark_confirmed(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.CONFIRMED.value, "审核确认")
        self._write_task(task)
        return task

    def mark_exported(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.EXPORTED.value, "导出完成")
        self._write_task(task)
        return task

    def _read_task(self, task_id: str) -> dict:
        task = self._store.read(f"tasks/{task_id}.json")
        if task is None:
            raise AppError(ErrorCode.TASK_NOT_FOUND)
        return self._normalize_task(task)

    def _write_task(self, task: dict) -> None:
        self._store.write(f"tasks/{task['task_id']}.json", task)

    def _normalize_task(self, task: dict) -> dict:
        normalized = dict(task)
        normalized.setdefault("error_code", None)
        normalized.setdefault("error_message", None)
        normalized.setdefault("failed_at", None)
        normalized.setdefault("processing_at", None)
        normalized.setdefault("ready_at", None)
        normalized.setdefault(
            "status_history",
            [
                {
                    "from_status": None,
                    "to_status": normalized["status"],
                    "changed_at": normalized["created_at"],
                    "reason": "采集会话完成采集",
                }
            ],
        )
        normalized["page_summary"] = {
            "page_count": normalized.get("page_count", 0),
            "page_order": normalized.get("page_order", []),
        }
        normalized.setdefault("document_summary", None)
        normalized.setdefault(
            "review_summary",
            {"status": None, "unreviewed_count": None, "suspicious_count": None},
        )
        normalized.setdefault("export_summary", {"last_exported_at": None, "formats": []})
        return normalized

    def _transition(self, task: dict, target: str, reason: str) -> dict:
        current = task["status"]
        self._validate_transition(current, target)
        task["status"] = target
        self._add_history(task, current, target, reason)
        return task

    def _validate_transition(self, current: str, target: str) -> None:
        try:
            valid = TaskStatus.is_valid_transition(current, target)
        except ValueError:
            valid = False
        if not valid:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": current, "target": target},
            )

    def _add_history(self, task: dict, current: str, target: str, reason: str) -> None:
        task.setdefault("status_history", [])
        task["status_history"].append(
            {
                "from_status": current,
                "to_status": target,
                "changed_at": self._now(),
                "reason": reason,
            }
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run TaskService tests**

Run:

```bash
python -m pytest app/backend/tests/test_task_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/task_service.py app/backend/tests/test_task_service.py
git commit -m "feat: 实现任务生命周期服务"
```

## Task 3: Task Routes and App Registration

**Files:**
- Create: `app/backend/routes/task.py`
- Create: `app/backend/tests/test_task_routes.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/routes/__init__.py`

- [ ] **Step 1: Write failing route tests**

Create `app/backend/tests/test_task_routes.py`:

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


def write_task(app, task_id="task-001", status="uploaded", **overrides):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task = {
        "task_id": task_id,
        "session_id": "session-001",
        "status": status,
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2,
        "page_order": ["page-1", "page-2"],
        "source": "capture_session",
    }
    task.update(overrides)
    store.write(f"tasks/{task_id}.json", task)
    return task


class TestTaskRoutes:
    def test_list_tasks_returns_200(self, client, app):
        write_task(app, task_id="task-001", status="uploaded")

        resp = client.get("/api/tasks")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["tasks"][0]["task_id"] == "task-001"

    def test_list_tasks_filter_by_status(self, client, app):
        write_task(app, task_id="task-001", status="uploaded")
        write_task(app, task_id="task-002", status="failed")

        resp = client.get("/api/tasks?status=failed")

        assert resp.status_code == 200
        assert [task["task_id"] for task in resp.get_json()["data"]["tasks"]] == ["task-002"]

    def test_get_task_returns_200(self, client, app):
        write_task(app)

        resp = client.get("/api/tasks/task-001")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["task_id"] == "task-001"
        assert data["page_summary"]["page_order"] == ["page-1", "page-2"]
        assert data["document_summary"] is None
        assert data["review_summary"]["status"] is None
        assert data["export_summary"]["formats"] == []

    def test_get_nonexistent_task_returns_404(self, client):
        resp = client.get("/api/tasks/missing")

        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "TASK_NOT_FOUND"

    def test_process_task_without_algorithm_returns_failed_payload(self, client, app):
        write_task(app, status="uploaded")

        resp = client.post("/api/tasks/task-001/process")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert [entry["to_status"] for entry in data["status_history"]] == [
            "uploaded",
            "processing",
            "failed",
        ]

    def test_process_task_invalid_state_returns_400(self, client, app):
        write_task(app, status="confirmed")

        resp = client.post("/api/tasks/task-001/process")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"

    def test_retry_task_without_algorithm_returns_failed_payload(self, client, app):
        write_task(
            app,
            status="failed",
            error_code="ALGORITHM_MODULE_FAILED",
            error_message="旧错误",
            failed_at="2026-05-12T10:01:00+00:00",
        )

        resp = client.post("/api/tasks/task-001/retry")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert data["status_history"][-2]["to_status"] == "processing"
        assert data["status_history"][-1]["to_status"] == "failed"

    def test_retry_task_invalid_state_returns_400(self, client, app):
        write_task(app, status="uploaded")

        resp = client.post("/api/tasks/task-001/retry")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
```

- [ ] **Step 2: Run failing route tests**

Run:

```bash
python -m pytest app/backend/tests/test_task_routes.py -q
```

Expected: FAIL with 404 responses for `/api/tasks`.

- [ ] **Step 3: Add route helper**

If `app/backend/routes/__init__.py` does not already expose a task service helper, set it to:

```python
from flask import current_app


def _get_session_service():
    return current_app.config["SESSION_SERVICE"]


def _get_task_service():
    return current_app.config["TASK_SERVICE"]
```

If `_get_session_service()` already exists, add only:

```python
def _get_task_service():
    return current_app.config["TASK_SERVICE"]
```

- [ ] **Step 4: Implement `task_bp`**

Create `app/backend/routes/task.py`:

```python
from flask import Blueprint, request

from ..responses import success
from . import _get_task_service


task_bp = Blueprint("task", __name__)


@task_bp.route("/api/tasks", methods=["GET"])
def list_tasks():
    status = request.args.get("status")
    return success(data={"tasks": _get_task_service().list_tasks(status=status)})


@task_bp.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    return success(data=_get_task_service().get_task(task_id))


@task_bp.route("/api/tasks/<task_id>/process", methods=["POST"])
def process_task(task_id):
    return success(data=_get_task_service().process(task_id))


@task_bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
def retry_task(task_id):
    return success(data=_get_task_service().retry(task_id))
```

- [ ] **Step 5: Register service and blueprint**

Modify `app/backend/__init__.py`.

After `store = JsonStore(config["storage_dir"])`, add:

```python
    from .services.task_service import TaskService

    app.config["TASK_SERVICE"] = TaskService(store=store)
```

Near the other route registrations, add:

```python
    from .routes.task import task_bp
    app.register_blueprint(task_bp)
```

- [ ] **Step 6: Run route tests**

Run:

```bash
python -m pytest app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/backend/__init__.py app/backend/routes/__init__.py app/backend/routes/task.py app/backend/tests/test_task_routes.py
git commit -m "feat: 增加任务生命周期 API"
```

## Task 4: Full Backend Regression and Spec Alignment

**Files:**
- Modify only if tests reveal regressions.

- [ ] **Step 1: Run focused lifecycle tests**

Run:

```bash
python -m pytest app/backend/tests/test_json_store.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 3: Check for forbidden algorithm implementation**

Run:

```bash
rg -n "ocr|llm|extract|rule|规则|裁剪|透视|base64|requests|httpx|openai" app/backend
```

Expected: No new OCR/LLM/rule extraction implementation in lifecycle files. Existing legitimate references in docs, tests, or unrelated config can remain.

- [ ] **Step 4: Check diff**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` prints no whitespace errors. `git status --short` shows only intended task lifecycle files and this plan/spec if uncommitted.

- [ ] **Step 5: Commit final verification-only adjustments if any**

If Task 4 required small fixes:

```bash
git add app/backend docs/superpowers/specs/2026-05-12-task-lifecycle-design.md docs/superpowers/plans/2026-05-12-task-lifecycle-plan.md
git commit -m "test: 完成任务生命周期回归验证"
```

If no code changed in Task 4, do not create an empty commit.

## Self-Review

- Spec coverage:
  - Task listing and filtering: Task 2 service tests, Task 3 route tests.
  - Task detail with page/document/review/export summaries: Task 2 and Task 3.
  - Legal and illegal state transitions: Task 2.
  - Process/retry A-lite algorithm-not-configured failure: Task 2 and Task 3.
  - Failure metadata and status history: Task 2 and Task 3.
  - Old Task stub compatibility: Task 2.
- Placeholder scan:
  - No `TBD`, `TODO`, or "implement later" placeholders are required to execute the plan.
  - Code snippets include concrete method names, payload fields, and test expectations.
- Type consistency:
  - `TaskService` methods match the spec: `list_tasks`, `get_task`, `process`, `retry`, `mark_ready`, `mark_failed`, `mark_confirmed`, `mark_exported`.
  - Route endpoints match the spec paths.
  - Failure `error_code` is persisted as the string `ALGORITHM_MODULE_NOT_CONFIGURED`, not raised as an HTTP `ErrorCode`.
