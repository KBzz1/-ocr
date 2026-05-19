# MVP Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛旧的采集会话、quad、旧任务状态，把主流程改为 `uploading -> processing -> review -> done` 和 `failed`，手机端只保留扫码多图上传与完成上传。

**Architecture:** 以后端 `Task` 作为唯一业务根，手机上传直接绑定 `task_id + upload_token`，图片页序由上传成功顺序决定。前端路由、API mock、页面与 E2E 全部切到 MVP 五状态，停止注册和使用旧 `/api/capture-sessions*`、`/api/mobile/<session_id>/*`、quad 和 session 入口。

**Tech Stack:** Flask + pytest + JsonStore；React + TypeScript + Vite + Vitest/RTL + MSW + Playwright；本地离线资源，不引入云 API、CDN、遥测或运行时联网下载。

---

## Reference Context

- 全仓库规则：`AGENTS.md`
- 文档规则：`docs/AGENTS.md`
- 产品依据：`docs/产品PRD.md`
- 任务索引：`docs/PRD任务清单.md`
- 状态契约：`docs/Shared/state-enums.md`
- 错误码契约：`docs/Shared/error-codes.md`
- Spec：`docs/superpowers/specs/2026-05-19-mvp-simplification-design.md`
- 应用边界：`app/README.md`
- 后端边界：`app/backend/README.md`
- 前端边界：`app/frontend/README.md`
- 手机上传边界：`app/frontend/mobile-capture.README.md`
- 工作台边界：`app/frontend/workstation.README.md`

## File Structure

### Backend

- Modify: `app/backend/enums.py`
  - 只保留 MVP `TaskStatus`、`FieldStatus` 和 `TASK_STATUS_TRANSITIONS`。
  - 删除 `SessionStatus` 和 `SESSION_STATUS_TRANSITIONS` 的生产引用。
- Modify: `app/backend/errors.py`
  - 移除 `SESSION_*` 和 `INVALID_QUAD_POINTS` 错误码。
  - 新增 `TASK_UPLOAD_CLOSED`、`TASK_EMPTY`。
- Modify: `app/backend/__init__.py`
  - 不再创建 `SessionService`。
  - `PageService` 改为 task-bound。
  - `ProcessingOrchestrator` 不再接收 `session_service`。
  - 不注册 `capture_session_bp`。
- Modify: `app/backend/routes/task.py`
  - 新增 `POST /api/tasks`。
  - 保留 `GET /api/tasks`、`GET /api/tasks/{task_id}`、`POST /api/tasks/{task_id}/process`。
  - 将旧 `/retry` 收敛到 `POST /api/tasks/{task_id}/process`，或保留内部别名但不作为 MVP 文档入口。
- Modify/Create: `app/backend/routes/mobile.py`
  - 收敛为 `/api/mobile-upload/{task_id}/images`、`/api/mobile-upload/{task_id}/finish`。
  - 删除 quad、替换图片、session finish 的公开路由。
- Modify: `app/backend/services/task_service.py`
  - 新增 `create_uploading_task()`、`finish_upload()`、`complete_review()`。
  - 状态转换改为五状态。
  - 导出成功只更新 `export_summary`，不进入 `exported`。
- Modify: `app/backend/services/page_service.py`
  - 保存图片到 task 图片列表，返回 `page_id/page_no/original_image_path/preview_url`。
  - 不接收、不保存、不返回 `quad_points`、`processed_image_path`、`session_id`。
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
  - `_build_image_inputs()` 只从 `task["images"]` 构建输入。
  - 输入不包含 `quad_points`。
- Modify: `app/backend/services/review_service.py`
  - 字段状态只允许 `unreviewed/confirmed/modified`。
  - `confirm()` 后任务进入 `done`。
- Modify: `app/backend/services/export_service.py`
  - `review` 和 `done` 可导出。
  - 导出后调用 `task_service.record_export()` 更新摘要，不改变任务状态。
- Modify: `app/backend/tests/test_enums.py`
- Modify: `app/backend/tests/test_errors.py`
- Modify: `app/backend/tests/test_task_routes.py`
- Create: `app/backend/tests/test_mobile_upload_routes.py`
- Modify: `app/backend/tests/test_page_service.py`
- Modify: `app/backend/tests/test_orchestrator.py`
- Modify: `app/backend/tests/test_review_service.py`
- Modify: `app/backend/tests/test_review_routes.py`
- Modify: `app/backend/tests/test_export_service.py`
- Modify: `app/backend/tests/test_export_routes.py`
- Modify: `app/backend/tests/test_api_contracts.py`
- Modify: `app/backend/tests/test_backend_e2e.py`
- Delete or stop using: `app/backend/tests/test_capture_session.py`
- Delete or stop using: `app/backend/tests/test_session_service.py`
- Delete or stop using: `app/backend/tests/test_quad_validator.py`
- Delete or stop using: `app/backend/routes/capture_session.py`
- Delete or stop using: `app/backend/services/session_service.py`
- Delete or stop using: `app/backend/services/quad_validator.py`

### Frontend

- Modify: `app/frontend/src/api/tasks.ts`
  - Task status union 改为五状态。
  - 新增 `createTask()`、`processTask()`、`completeTask()`。
- Create: `app/frontend/src/api/mobileUpload.ts`
  - `getMobileUploadTask()`、`uploadTaskImages()`、`finishTaskUpload()`。
- Modify: `app/frontend/src/api/review.ts`
  - 支持 `GET/PUT /api/tasks/{task_id}/review` 和完成审核。
- Modify: `app/frontend/src/api/export.ts`
  - 导出入口只面向 `review/done`。
- Delete or stop using: `app/frontend/src/api/captureSessions.ts`
- Modify: `app/frontend/src/app/routes.tsx`
  - 手机入口改为 `/mobile/upload/:taskId`。
  - 删除 `/mobile/sessions/:sessionId` 的正向构造函数。
- Modify: `app/frontend/src/styles/status.ts`
  - 只保留五状态文案和字段状态文案。
- Modify: `app/frontend/src/components/workstation/CaptureQrDialog.tsx`
  - 展示 task 上传二维码，不展示 session 过期/锁定/取消信息。
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
  - 新建任务调用 `POST /api/tasks`。
- Modify: `app/frontend/src/state/workstationStore.ts`
  - 最近任务和统计只按五状态聚合。
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CapturePageList.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CapturePhotoButton.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CaptureFooter.tsx`
- Delete or stop using: `app/frontend/src/pages/mobile-capture/CaptureQuadScreen.tsx`
- Delete or stop using: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`
- Modify/Create: `app/frontend/src/pages/tasks/TasksPage.tsx`
- Modify/Create: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/tests/fixtures/tasks.ts`
- Modify/Create: `app/frontend/tests/fixtures/mobileUpload.ts`
- Delete or stop using: `app/frontend/tests/fixtures/sessions.ts`
- Delete or stop using: `app/frontend/tests/fixtures/uploads.ts` session fixtures
- Modify: `app/frontend/src/app/routes.test.ts`
- Modify: `app/frontend/src/api/shared-contracts.test.ts`
- Delete or rewrite: `app/frontend/src/api/captureSessions.test.ts`
- Delete or rewrite: `app/frontend/src/components/mobile-capture/QuadSelector.test.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
- Modify/Create: `app/frontend/src/pages/tasks/TasksPage.test.tsx`
- Modify/Create: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify: `app/frontend/src/components/export/ExportPanel.test.tsx`
- Modify: `app/frontend/tests/e2e/workstation.spec.ts`
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`

### Docs

- Modify after implementation: `docs/PRD任务清单.md`
  - 将完成的 `需收敛` 项更新为 `已完成`，保留未实施项真实状态。
  - 本计划本身不要求在执行期间提前修改清单。

---

## Backend Phase

### Task 1: Shared MVP Enums And Error Codes

**Files:**
- Modify: `app/backend/enums.py`
- Modify: `app/backend/errors.py`
- Modify: `app/backend/tests/test_enums.py`
- Modify: `app/backend/tests/test_errors.py`

- [ ] **Step 1: Write failing enum tests**

Replace or extend `app/backend/tests/test_enums.py` with tests that assert only MVP task and field states are accepted:

```python
import pytest

from app.backend.enums import FieldStatus, TaskStatus


def test_task_status_values_are_mvp_only():
    assert [status.value for status in TaskStatus] == [
        "uploading",
        "processing",
        "review",
        "done",
        "failed",
    ]


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("uploading", "processing"),
        ("uploading", "failed"),
        ("processing", "review"),
        ("processing", "failed"),
        ("review", "processing"),
        ("review", "done"),
        ("review", "failed"),
        ("done", "processing"),
        ("failed", "processing"),
    ],
)
def test_mvp_task_status_transitions_are_allowed(current, target):
    assert TaskStatus.is_valid_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("failed", "uploading"),
        ("done", "failed"),
        ("uploading", "review"),
        ("processing", "done"),
        ("review", "uploading"),
    ],
)
def test_invalid_mvp_task_status_transitions_are_rejected(current, target):
    assert not TaskStatus.is_valid_transition(current, target)


@pytest.mark.parametrize("legacy_status", ["capturing", "uploaded", "ready_for_review", "confirmed", "exported"])
def test_legacy_task_status_values_are_rejected(legacy_status):
    with pytest.raises(ValueError):
        TaskStatus(legacy_status)


def test_field_status_values_are_mvp_only():
    assert [status.value for status in FieldStatus] == [
        "unreviewed",
        "confirmed",
        "modified",
    ]


@pytest.mark.parametrize("legacy_status", ["suspicious", "empty", "confirmed_empty"])
def test_legacy_field_status_values_are_rejected(legacy_status):
    with pytest.raises(ValueError):
        FieldStatus(legacy_status)
```

- [ ] **Step 2: Write failing error-code tests**

Replace or extend `app/backend/tests/test_errors.py` with the MVP assertions:

```python
from app.backend.errors import ErrorCode


def test_mvp_error_codes_include_upload_errors():
    assert ErrorCode.TASK_UPLOAD_CLOSED.code == "TASK_UPLOAD_CLOSED"
    assert ErrorCode.TASK_UPLOAD_CLOSED.http_status == 409
    assert ErrorCode.TASK_EMPTY.code == "TASK_EMPTY"
    assert ErrorCode.TASK_EMPTY.http_status == 400


def test_session_and_quad_error_codes_are_not_public_contract():
    codes = {item.code for item in ErrorCode}
    assert "SESSION_NOT_FOUND" not in codes
    assert "SESSION_EXPIRED" not in codes
    assert "SESSION_LOCKED" not in codes
    assert "SESSION_EMPTY" not in codes
    assert "SESSION_CANCELLED" not in codes
    assert "SESSION_UNLOCK_NOT_ALLOWED" not in codes
    assert "INVALID_QUAD_POINTS" not in codes
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_enums.py app/backend/tests/test_errors.py -q
```

Expected: FAIL because `TaskStatus` still contains `capturing/uploaded/ready_for_review/confirmed/exported`, `FieldStatus` still contains complex statuses, and `ErrorCode` still exposes `SESSION_*` and `INVALID_QUAD_POINTS`.

- [ ] **Step 4: Implement MVP enums and errors**

Change `app/backend/enums.py` to this shape:

```python
from enum import Enum


TASK_STATUS_TRANSITIONS = {
    "uploading": ["processing", "failed"],
    "processing": ["review", "failed"],
    "review": ["processing", "done", "failed"],
    "done": ["processing"],
    "failed": ["processing"],
}


class TaskStatus(Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"

    @classmethod
    def _resolve(cls, value):
        if isinstance(value, cls):
            return value
        return cls(value)

    @classmethod
    def allowed_transitions(cls, current):
        current = cls._resolve(current)
        return [cls(v) for v in TASK_STATUS_TRANSITIONS.get(current.value, [])]

    @classmethod
    def is_valid_transition(cls, current, target):
        try:
            current = cls._resolve(current)
            target = cls._resolve(target)
        except ValueError:
            return False
        return target in cls.allowed_transitions(current)


class FieldStatus(Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
```

Change `app/backend/errors.py` `ErrorCode` members to keep the existing common and algorithm/export/review errors plus:

```python
class ErrorCode(Enum):
    REQUEST_NOT_FOUND = ("REQUEST_NOT_FOUND", 404, "请求路径不存在")
    INTERNAL_SERVER_ERROR = ("INTERNAL_SERVER_ERROR", 500, "服务器内部错误")
    INVALID_REQUEST_PARAMS = ("INVALID_REQUEST_PARAMS", 400, "请求参数缺失、类型错误、格式错误或取值非法")
    UNSUPPORTED_FILE_TYPE = ("UNSUPPORTED_FILE_TYPE", 400, "不支持的文件类型")
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", 400, "文件超过大小限制")
    TASK_NOT_FOUND = ("TASK_NOT_FOUND", 404, "任务不存在")
    TASK_UPLOAD_CLOSED = ("TASK_UPLOAD_CLOSED", 409, "任务不处于上传中，禁止继续上传图片")
    TASK_EMPTY = ("TASK_EMPTY", 400, "任务没有任何已上传图片，不能完成上传")
    INVALID_TASK_TRANSITION = ("INVALID_TASK_TRANSITION", 400, "非法任务状态流转")
    ALGORITHM_MODULE_NOT_CONFIGURED = ("ALGORITHM_MODULE_NOT_CONFIGURED", 500, "算法模块未配置")
    ALGORITHM_MODULE_FAILED = ("ALGORITHM_MODULE_FAILED", 500, "外部算法模块异常")
    ALGORITHM_CONTRACT_INVALID = ("ALGORITHM_CONTRACT_INVALID", 500, "外部算法模块返回结构不符合契约")
    REVIEW_VALIDATION_FAILED = ("REVIEW_VALIDATION_FAILED", 400, "审核保存或确认请求非法")
    EXPORT_VALIDATION_FAILED = ("EXPORT_VALIDATION_FAILED", 400, "导出请求非法或任务状态不允许导出")
    EXPORT_FAILED = ("EXPORT_FAILED", 500, "导出文件写入失败")
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_enums.py app/backend/tests/test_errors.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/enums.py app/backend/errors.py app/backend/tests/test_enums.py app/backend/tests/test_errors.py
git commit -m "收敛后端 MVP 状态和错误码"
```

### Task 2: Task Creation And Task-Bound Upload Model

**Files:**
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/routes/task.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_task_routes.py`
- Modify: `app/backend/tests/test_task_service.py`

- [ ] **Step 1: Write failing service tests**

Add tests in `app/backend/tests/test_task_service.py`:

```python
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def test_create_uploading_task_has_upload_token_and_empty_images(tmp_path):
    service = TaskService(store=JsonStore(tmp_path))

    task = service.create_uploading_task(base_url="http://192.168.1.5:8081")

    assert task["task_id"].startswith("task_")
    assert task["status"] == "uploading"
    assert task["upload_token"]
    assert task["mobile_upload_url"] == (
        f"http://192.168.1.5:8081/mobile/upload/{task['task_id']}?token={task['upload_token']}"
    )
    assert task["images"] == []
    assert task["error_code"] is None
    assert task["export_summary"] == {"last_exported_at": None, "formats": [], "files": []}


def test_list_tasks_does_not_expose_session_id(tmp_path):
    service = TaskService(store=JsonStore(tmp_path))
    created = service.create_uploading_task(base_url="http://127.0.0.1:8081")

    [summary] = service.list_tasks()

    assert summary["task_id"] == created["task_id"]
    assert summary["status"] == "uploading"
    assert summary["page_count"] == 0
    assert "session_id" not in summary
```

- [ ] **Step 2: Write failing route tests**

Add tests in `app/backend/tests/test_task_routes.py`:

```python
def test_post_tasks_creates_uploading_task(client):
    response = client.post("/api/tasks")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"].startswith("task_")
    assert data["status"] == "uploading"
    assert data["upload_token"]
    assert f"/mobile/upload/{data['task_id']}?token={data['upload_token']}" in data["mobile_upload_url"]


def test_get_task_returns_mvp_shape_without_session(client):
    created = client.post("/api/tasks").get_json()["data"]

    response = client.get(f"/api/tasks/{created['task_id']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "uploading"
    assert data["images"] == []
    assert "session_id" not in data
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: FAIL because `TaskService` lacks `create_uploading_task()`, `POST /api/tasks` is not registered, and task summaries still expose `session_id`.

- [ ] **Step 4: Implement task creation**

In `app/backend/services/task_service.py`, add deterministic task creation based on existing store contents:

```python
from secrets import token_urlsafe


def create_uploading_task(self, base_url: str) -> dict:
    existing_count = len(self._store.list_json("tasks"))
    task_id = f"task_{existing_count + 1:03d}"
    now = self._now()
    upload_token = token_urlsafe(24)
    task = {
        "task_id": task_id,
        "status": TaskStatus.UPLOADING.value,
        "created_at": now,
        "updated_at": now,
        "upload_token": upload_token,
        "images": [],
        "error_code": None,
        "error_message": None,
        "failed_at": None,
        "review_summary": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        "status_history": [
            {
                "from_status": None,
                "to_status": TaskStatus.UPLOADING.value,
                "changed_at": now,
                "reason": "创建上传任务",
            }
        ],
    }
    self._write_task(task)
    task = self._normalize_task(task)
    task["mobile_upload_url"] = self._build_mobile_upload_url(base_url, task_id, upload_token)
    return task


def _build_mobile_upload_url(self, base_url: str, task_id: str, upload_token: str) -> str:
    return f"{base_url.rstrip('/')}/mobile/upload/{task_id}?token={upload_token}"
```

Update `list_tasks()` to return summaries without `session_id` and with `page_count = len(images)`:

```python
return [
    {
        "task_id": task["task_id"],
        "status": task["status"],
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
        "page_count": len(task.get("images", [])),
        "review_summary": task.get("review_summary"),
        "export_summary": task.get("export_summary"),
        "error_code": task.get("error_code"),
        "error_message": task.get("error_message"),
    }
    for task in sorted(tasks, key=lambda item: item["task_id"])
]
```

Update `_normalize_task()` defaults to `images`, not session/page order:

```python
normalized.setdefault("images", [])
normalized.setdefault("review_summary", None)
normalized.setdefault("export_summary", {"last_exported_at": None, "formats": [], "files": []})
normalized["page_count"] = len(normalized["images"])
```

- [ ] **Step 5: Implement `POST /api/tasks`**

In `app/backend/routes/task.py`:

```python
@task_bp.route("/api/tasks", methods=["POST"])
def create_task():
    base_url = request.host_url.rstrip("/")
    return success(data=_get_task_service().create_uploading_task(base_url=base_url), status=201)
```

If existing tests expect 200 from `success()`, either update `success()` expectations to support 201 or remove `status=201`; keep route contract consistent across backend and frontend tests.

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/task_service.py app/backend/routes/task.py app/backend/__init__.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py
git commit -m "新增任务根上传入口"
```

### Task 3: Task-Bound Image Upload And Finish

**Files:**
- Modify/Create: `app/backend/routes/mobile.py`
- Modify: `app/backend/services/page_service.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/__init__.py`
- Create: `app/backend/tests/test_mobile_upload_routes.py`
- Modify: `app/backend/tests/test_page_service.py`

- [ ] **Step 1: Write failing page-service tests**

Add task-bound page tests in `app/backend/tests/test_page_service.py`:

```python
from app.backend.services.file_validator import FileValidator
from app.backend.services.page_service import PageService
from app.backend.storage.json_store import JsonStore
from app.backend.tests.fixtures.images import minimal_png


def test_save_task_image_appends_page_no_and_omits_quad(tmp_path):
    store = JsonStore(tmp_path)
    service = PageService(
        file_validator=FileValidator(max_size_mb=5, base_dir="pages"),
        store=store,
        storage_dir=str(tmp_path),
    )
    task = {
        "task_id": "task_001",
        "status": "uploading",
        "images": [],
    }

    first = service.save_task_image(task, minimal_png(), image_width=120, image_height=80)
    second = service.save_task_image(task, minimal_png(), image_width=120, image_height=80)

    assert first["page_no"] == 1
    assert second["page_no"] == 2
    assert first["task_id"] == "task_001"
    assert "session_id" not in first
    assert "quad_points" not in first
    assert "processed_image_path" not in first
```

- [ ] **Step 2: Write failing upload-route tests**

Create `app/backend/tests/test_mobile_upload_routes.py`:

```python
from io import BytesIO

from app.backend.tests.fixtures.images import minimal_png


def _create_task(client):
    return client.post("/api/tasks").get_json()["data"]


def _upload(client, task, image_name="page.png"):
    return client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token={task['upload_token']}",
        data={
            "image": (BytesIO(minimal_png()), image_name),
            "image_width": "120",
            "image_height": "80",
        },
        content_type="multipart/form-data",
    )


def test_upload_image_adds_page_to_task_in_upload_order(client):
    task = _create_task(client)

    first = _upload(client, task, "first.png")
    second = _upload(client, task, "second.png")

    assert first.status_code == 201
    assert second.status_code == 201
    first_data = first.get_json()["data"]
    second_data = second.get_json()["data"]
    assert first_data["page_no"] == 1
    assert second_data["page_no"] == 2
    assert "quad_points" not in first_data
    detail = client.get(f"/api/tasks/{task['task_id']}").get_json()["data"]
    assert [image["page_no"] for image in detail["images"]] == [1, 2]


def test_upload_rejects_invalid_token(client):
    task = _create_task(client)

    response = client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token=wrong",
        data={
            "image": (BytesIO(minimal_png()), "page.png"),
            "image_width": "120",
            "image_height": "80",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"


def test_finish_empty_task_returns_task_empty(client):
    task = _create_task(client)

    response = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "TASK_EMPTY"


def test_finish_with_images_moves_to_processing_or_failed(client):
    task = _create_task(client)
    _upload(client, task)

    response = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] in {"processing", "failed"}
    if data["status"] == "failed":
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py app/backend/tests/test_mobile_upload_routes.py -q
```

Expected: FAIL because current upload route uses `/api/mobile/<session_id>/pages`, `PageService` requires `session_service`, and route still parses quad.

- [ ] **Step 4: Implement task-bound `PageService`**

Refactor `PageService.__init__()` to remove `session_service` and `min_quad_area_ratio`:

```python
class PageService:
    def __init__(self, file_validator: FileValidator, store: JsonStore, storage_dir: str):
        self._file_validator = file_validator
        self._store = store
        self._storage_dir = os.path.realpath(storage_dir)
```

Add `save_task_image()`:

```python
def save_task_image(self, task: dict, image_data: bytes, image_width: int | None = None, image_height: int | None = None) -> dict:
    if image_width is not None and (not isinstance(image_width, int) or image_width <= 0):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 必须为正整数")
    if image_height is not None and (not isinstance(image_height, int) or image_height <= 0):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_height 必须为正整数")

    validation = self._file_validator.validate(image_data)
    ext = validation["ext"]
    page_no = len(task.get("images", [])) + 1
    page_id = f"page_{page_no:03d}"
    rel_path = self._file_validator.build_path(task["task_id"], page_id, ext)
    abs_image_path = os.path.join(self._storage_dir, rel_path)
    os.makedirs(os.path.dirname(abs_image_path), exist_ok=True)
    with open(abs_image_path, "wb") as f:
        f.write(image_data)

    page = {
        "page_id": page_id,
        "task_id": task["task_id"],
        "page_no": page_no,
        "original_image_path": abs_image_path,
        "preview_url": f"/api/tasks/{task['task_id']}/images/{page_id}",
        "image_width": image_width,
        "image_height": image_height,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    self._store.write(self._file_validator.build_path(task["task_id"], page_id, "json"), page)
    return page
```

- [ ] **Step 5: Implement task image append and finish upload**

In `TaskService`, add:

```python
def assert_upload_token(self, task: dict, token: str | None) -> None:
    if not token or token != task.get("upload_token"):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="上传令牌无效")


def add_image(self, task_id: str, page: dict) -> dict:
    task = self._read_task(task_id)
    if task["status"] != TaskStatus.UPLOADING.value:
        raise AppError(ErrorCode.TASK_UPLOAD_CLOSED)
    task.setdefault("images", []).append(page)
    task["updated_at"] = self._now()
    self._write_task(task)
    return page


def finish_upload(self, task_id: str) -> dict:
    task = self._read_task(task_id)
    if task["status"] != TaskStatus.UPLOADING.value:
        return task
    if not task.get("images"):
        raise AppError(ErrorCode.TASK_EMPTY)
    task = self._transition(task, TaskStatus.PROCESSING.value, "完成上传")
    task["processing_at"] = self._now()
    self._write_task(task)
    return self._run_orchestrator(task)
```

- [ ] **Step 6: Replace mobile routes**

In `app/backend/routes/mobile.py`, keep only the MVP routes:

```python
from flask import Blueprint, request

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _get_task_service

mobile_bp = Blueprint("mobile", __name__)


def _page_service():
    from flask import current_app
    return current_app.config["PAGE_SERVICE"]


def _parse_optional_dimensions():
    width = request.form.get("image_width")
    height = request.form.get("image_height")
    return int(width) if width else None, int(height) if height else None


@mobile_bp.route("/api/mobile-upload/<task_id>/images", methods=["POST"])
def upload_task_image(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    if task["status"] != "uploading":
        raise AppError(ErrorCode.TASK_UPLOAD_CLOSED)
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")
    image_width, image_height = _parse_optional_dimensions()
    page = _page_service().save_task_image(
        task=task,
        image_data=request.files["image"].read(),
        image_width=image_width,
        image_height=image_height,
    )
    return success(data=task_service.add_image(task_id, page), status=201)


@mobile_bp.route("/api/mobile-upload/<task_id>/finish", methods=["POST"])
def finish_task_upload(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    return success(data=task_service.finish_upload(task_id))
```

- [ ] **Step 7: Wire task-bound `PageService` in app factory**

In `app/backend/__init__.py`, instantiate without `SessionService`:

```python
page_service = PageService(
    file_validator=file_validator,
    store=store,
    storage_dir=config["storage_dir"],
)
app.config["PAGE_SERVICE"] = page_service
```

- [ ] **Step 8: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py app/backend/tests/test_mobile_upload_routes.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/backend/routes/mobile.py app/backend/services/page_service.py app/backend/services/task_service.py app/backend/__init__.py app/backend/tests/test_mobile_upload_routes.py app/backend/tests/test_page_service.py
git commit -m "收敛手机端任务图片上传"
```

### Task 4: Processing Uses Task Images, Not Session Or Quad

**Files:**
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_orchestrator.py`
- Modify: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write failing orchestrator tests**

Add tests in `app/backend/tests/test_orchestrator.py`:

```python
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.storage.json_store import JsonStore


def test_build_image_inputs_uses_task_images_and_omits_quad(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(tmp_path))
    task = {
        "task_id": "task_001",
        "images": [
            {
                "page_id": "page_001",
                "page_no": 1,
                "original_image_path": "/data/task_001/page_001.png",
                "image_width": 120,
                "image_height": 80,
            }
        ],
    }

    inputs = orchestrator._build_image_inputs(task)

    assert inputs == [
        {
            "task_id": "task_001",
            "page_id": "page_001",
            "page_no": 1,
            "original_path": "/data/task_001/page_001.png",
            "image_width": 120,
            "image_height": 80,
        }
    ]


def test_build_image_inputs_returns_none_when_task_has_no_images(tmp_path):
    orchestrator = ProcessingOrchestrator(store=JsonStore(tmp_path))

    assert orchestrator._build_image_inputs({"task_id": "task_001", "images": []}) is None
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q
```

Expected: FAIL because `_build_image_inputs()` currently depends on `session_id`, `page_order`, session pages, and includes `quad_points`.

- [ ] **Step 3: Implement task-image input builder**

Replace `_build_image_inputs()` with:

```python
def _build_image_inputs(self, task: dict) -> list | None:
    images = task.get("images") or []
    if not images:
        return None

    inputs = []
    for image in sorted(images, key=lambda item: item["page_no"]):
        original_path = image.get("original_image_path")
        if not original_path:
            return None
        inputs.append(
            {
                "task_id": task["task_id"],
                "page_id": image["page_id"],
                "page_no": image["page_no"],
                "original_path": original_path,
                "image_width": image.get("image_width"),
                "image_height": image.get("image_height"),
            }
        )
    return inputs
```

Update `ProcessingOrchestrator.__init__()` to remove `session_service`:

```python
def __init__(self, store: JsonStore, result_store=None, image_port=None, doc_port=None, field_port=None, schema_validator=None):
    self._store = store
    self._result_store = result_store or AlgorithmResultStore(store)
    self._image_port = image_port
    self._doc_port = doc_port
    self._field_port = field_port
    self._schema_validator = schema_validator
```

Update app factory construction accordingly:

```python
orchestrator = ProcessingOrchestrator(
    store=store,
    schema_validator=schema_service.build_validator(),
)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/orchestrator.py app/backend/__init__.py app/backend/tests/test_orchestrator.py
git commit -m "改为任务图片驱动算法输入"
```

### Task 5: Stop Registering Legacy Session And Quad API

**Files:**
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/tests/test_api_contracts.py`
- Modify/Delete: `app/backend/tests/test_capture_session.py`
- Modify/Delete: `app/backend/tests/test_session_service.py`
- Modify/Delete: `app/backend/tests/test_quad_validator.py`

- [ ] **Step 1: Write failing API-contract tests**

Add assertions in `app/backend/tests/test_api_contracts.py`:

```python
def test_legacy_capture_session_api_is_not_registered(client):
    assert client.post("/api/capture-sessions").status_code == 404
    assert client.get("/api/capture-sessions/session_001").status_code == 404


def test_legacy_mobile_session_api_is_not_registered(client):
    assert client.post("/api/mobile/session_001/pages").status_code == 404
    assert client.post("/api/mobile/session_001/finish").status_code == 404
    assert client.put("/api/mobile/session_001/pages/page_001/quad").status_code == 404
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py -q
```

Expected: FAIL because `capture_session_bp` and old mobile session routes are still registered.

- [ ] **Step 3: Stop registering legacy blueprint and services**

In `app/backend/__init__.py`, remove:

```python
from .services.session_service import SessionService
session_service = SessionService(...)
app.config["SESSION_SERVICE"] = session_service

from .routes.capture_session import capture_session_bp
app.register_blueprint(capture_session_bp)
```

Keep `mobile_bp`, but only after Task 3 has replaced it with MVP routes.

- [ ] **Step 4: Remove legacy tests from the default suite**

Delete the old positive-contract tests or rewrite them to assert 404:

```bash
git rm app/backend/tests/test_capture_session.py app/backend/tests/test_session_service.py app/backend/tests/test_quad_validator.py
```

If deleting production files in the same task is too risky, leave `app/backend/routes/capture_session.py`, `app/backend/services/session_service.py`, and `app/backend/services/quad_validator.py` unregistered, then delete them in Task 16 after full-suite green.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/__init__.py app/backend/tests/test_api_contracts.py
git rm app/backend/tests/test_capture_session.py app/backend/tests/test_session_service.py app/backend/tests/test_quad_validator.py
git commit -m "停止暴露旧采集会话接口"
```

### Task 6: Review Completion And Field Status Simplification

**Files:**
- Modify: `app/backend/services/review_service.py`
- Modify: `app/backend/routes/review.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/tests/test_review_service.py`
- Modify: `app/backend/tests/test_review_routes.py`

- [ ] **Step 1: Write failing review tests**

Add tests in `app/backend/tests/test_review_service.py`:

```python
import pytest

from app.backend.errors import AppError


def test_review_save_rejects_legacy_field_status(review_service, task_with_candidates):
    with pytest.raises(AppError) as exc:
        review_service.update_field(
            task_with_candidates["task_id"],
            "patient_name",
            {"value": "张三", "status": "suspicious"},
        )

    assert exc.value.code == "REVIEW_VALIDATION_FAILED"


def test_confirm_review_marks_task_done(review_service, task_service, task_with_candidates):
    task_id = task_with_candidates["task_id"]

    task = review_service.confirm(task_id)

    assert task["status"] == "done"
```

Add route test in `app/backend/tests/test_review_routes.py`:

```python
def test_put_review_saves_final_fields(client, review_task):
    response = client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "modified"},
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    assert response.status_code == 200
    fields = response.get_json()["data"]["review_result"]["fields"]
    assert {field["status"] for field in fields} <= {"unreviewed", "confirmed", "modified"}


def test_complete_review_route_marks_done(client, review_task):
    response = client.post(f"/api/tasks/{review_task['task_id']}/complete")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "done"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py -q
```

Expected: FAIL because review confirmation still targets `confirmed`, route uses `/review/confirm`, and legacy field statuses may still be accepted or summarized.

- [ ] **Step 3: Implement MVP review status handling**

In `review_service.py`, centralize status validation:

```python
MVP_FIELD_STATUSES = {"unreviewed", "confirmed", "modified"}


def _validate_field_status(status: str) -> None:
    if status not in MVP_FIELD_STATUSES:
        raise AppError(
            ErrorCode.REVIEW_VALIDATION_FAILED,
            message="字段状态必须是 unreviewed、confirmed 或 modified",
            details={"status": status},
        )
```

Use this validation in field update and bulk save. Update confirmation to call `task_service.complete_review()`:

```python
def confirm(self, task_id: str) -> dict:
    review = self.get_or_init(task_id)
    summary = self._build_summary(review)
    return self._task_service.complete_review(task_id, review_summary=summary)
```

In `TaskService`, add:

```python
def complete_review(self, task_id: str, review_summary: dict | None = None) -> dict:
    task = self._read_task(task_id)
    task = self._transition(task, TaskStatus.DONE.value, "审核完成")
    task["done_at"] = self._now()
    if review_summary is not None:
        task["review_summary"] = review_summary
    self._write_task(task)
    return task
```

- [ ] **Step 4: Add MVP review routes**

In `app/backend/routes/review.py`, keep `GET /api/tasks/<task_id>/review` and add:

```python
@review_bp.route("/api/tasks/<task_id>/review", methods=["PUT"])
def save_review(task_id):
    payload = request.get_json(silent=True) or {}
    review = _get_review_service().save(task_id, payload)
    return success(data={"task_id": task_id, "review_result": review})


@review_bp.route("/api/tasks/<task_id>/complete", methods=["POST"])
def complete_task(task_id):
    task = _get_review_service().confirm(task_id)
    return success(data=task)
```

Keep the old `/review/fields/<field_key>` and `/review/confirm` only if still needed by existing UI during migration, but do not use them in MVP tests or new frontend code.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/review_service.py app/backend/routes/review.py app/backend/services/task_service.py app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py
git commit -m "收敛审核完成和字段状态"
```

### Task 7: Export From Review Or Done Without Exported State

**Files:**
- Modify: `app/backend/services/export_service.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/tests/test_export_service.py`
- Modify: `app/backend/tests/test_export_routes.py`

- [ ] **Step 1: Write failing export tests**

Add tests in `app/backend/tests/test_export_service.py`:

```python
def test_review_task_can_export_json_without_status_change(export_service, task_service, review_task):
    task_id = review_task["task_id"]

    info = export_service.export_json(task_id)

    assert info["filename"].endswith(".json")
    assert task_service.get_task(task_id)["status"] == "review"
    assert "json" in task_service.get_task(task_id)["export_summary"]["formats"]


def test_done_task_can_export_excel_without_exported_state(export_service, task_service, done_task):
    task_id = done_task["task_id"]

    info = export_service.export_excel(task_id)

    assert info["filename"].endswith(".xlsx")
    assert task_service.get_task(task_id)["status"] == "done"
    assert "excel" in task_service.get_task(task_id)["export_summary"]["formats"]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py -q
```

Expected: FAIL because export currently may require `confirmed` and call `mark_exported()`.

- [ ] **Step 3: Implement export state rules**

In `ExportService.check()` or validation logic, allow only:

```python
if task["status"] not in {"review", "done"}:
    raise AppError(
        ErrorCode.EXPORT_VALIDATION_FAILED,
        message="只有待审核或已完成任务可以导出",
        details={"status": task["status"]},
    )
```

In `TaskService`, replace `mark_exported()` with:

```python
def record_export(self, task_id: str, format: str, relative_path: str) -> dict:
    task = self._read_task(task_id)
    self._update_export_summary(task, format=format, relative_path=relative_path)
    task["updated_at"] = self._now()
    self._write_task(task)
    return task
```

Update `ExportService.export_json()` and `export_excel()` to call `record_export()` and never transition status.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/export_service.py app/backend/services/task_service.py app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py
git commit -m "导出不再改变任务状态"
```

### Task 8: Backend MVP Contract And E2E Consolidation

**Files:**
- Modify: `app/backend/tests/test_api_contracts.py`
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/backend/tests/fixtures/client.py` if fixture wiring still creates sessions

- [ ] **Step 1: Write backend success-path E2E**

In `app/backend/tests/test_backend_e2e.py`, add an MVP success flow using fake algorithm ports:

```python
def test_mvp_success_flow_create_upload_process_review_done_export(client, configured_algorithm_ports, minimal_image_file):
    created = client.post("/api/tasks").get_json()["data"]
    upload = client.post(
        f"/api/mobile-upload/{created['task_id']}/images?token={created['upload_token']}",
        data={"image": minimal_image_file, "image_width": "120", "image_height": "80"},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "review"

    review = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": "patient_name", "value": "张三", "status": "modified"}]},
    )
    assert review.status_code == 200

    completed = client.post(f"/api/tasks/{created['task_id']}/complete")
    assert completed.get_json()["data"]["status"] == "done"

    exported = client.get(f"/api/tasks/{created['task_id']}/export/json")
    assert exported.status_code == 200
    assert client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]["status"] == "done"
```

- [ ] **Step 2: Write backend failure-path E2E**

In `app/backend/tests/test_backend_e2e.py`:

```python
def test_mvp_algorithm_not_configured_goes_failed(client, minimal_image_file):
    created = client.post("/api/tasks").get_json()["data"]
    client.post(
        f"/api/mobile-upload/{created['task_id']}/images?token={created['upload_token']}",
        data={"image": minimal_image_file, "image_width": "120", "image_height": "80"},
        content_type="multipart/form-data",
    )

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
```

- [ ] **Step 3: Run backend E2E to verify RED or fixture gaps**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_api_contracts.py app/backend/tests/test_backend_e2e.py -q
```

Expected before fixture updates: FAIL if `configured_algorithm_ports` or `minimal_image_file` fixture is missing, or if old session flow is still asserted.

- [ ] **Step 4: Update fixtures and remove old session E2E**

In `app/backend/tests/fixtures/client.py`, expose fixtures that configure fake ports on the app's `ProcessingOrchestrator`:

```python
class FakeImagePort:
    def process(self, image_input):
        return {"processed_path": image_input["original_path"]}


class FakeDocumentPort:
    def parse(self, doc_input):
        return {
            "pages": [{"page_id": page["page_id"], "page_no": page["page_no"], "text": "姓名 张三"} for page in doc_input["pages"]],
            "merged_text": "姓名 张三",
        }


class FakeFieldPort:
    def extract(self, field_input):
        return [{"field_key": "patient_name", "value": "张三", "confidence": 0.9, "source": "algorithm"}]
```

Set these fake ports on the orchestrator according to the current fixture style. Remove old E2E assertions for capture sessions, quad update, `ready_for_review`, `confirmed`, and `exported`.

- [ ] **Step 5: Run backend full suite**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS. Any remaining failures should be old-session tests or stale assertions; rewrite them to MVP behavior or delete them if they only prove removed behavior.

- [ ] **Step 6: Commit**

```bash
git add app/backend/tests/test_api_contracts.py app/backend/tests/test_backend_e2e.py app/backend/tests/fixtures/client.py
git commit -m "覆盖后端 MVP 主流程验收"
```

---

## Frontend Phase

### Task 9: Frontend Shared Contracts And Routes

**Files:**
- Modify: `app/frontend/src/api/tasks.ts`
- Create: `app/frontend/src/api/mobileUpload.ts`
- Modify: `app/frontend/src/app/routes.tsx`
- Modify: `app/frontend/src/styles/status.ts`
- Modify: `app/frontend/src/api/shared-contracts.test.ts`
- Modify: `app/frontend/src/app/routes.test.ts`
- Delete or rewrite: `app/frontend/src/api/captureSessions.test.ts`

- [ ] **Step 1: Write failing route tests**

In `app/frontend/src/app/routes.test.ts`:

```typescript
import { appRoutes, buildMobileUploadPath, buildReviewPath } from './routes';

it('uses task-bound mobile upload route', () => {
  expect(appRoutes.mobileCapture.path).toBe('/mobile/upload/:taskId');
  expect(buildMobileUploadPath('task_001')).toBe('/mobile/upload/task_001');
});

it('does not expose mobile session route helpers', () => {
  const routePaths = Object.values(appRoutes).map((route) => route.path);
  expect(routePaths).not.toContain('/mobile/sessions/:sessionId');
  expect(buildReviewPath('task_001')).toBe('/tasks/task_001/review');
});
```

- [ ] **Step 2: Write failing API contract tests**

In `app/frontend/src/api/shared-contracts.test.ts`:

```typescript
import type { TaskStatus } from './tasks';

const mvpStatuses: TaskStatus[] = ['uploading', 'processing', 'review', 'done', 'failed'];

it('frontend task statuses match MVP states', () => {
  expect(mvpStatuses).toEqual(['uploading', 'processing', 'review', 'done', 'failed']);
});

it('legacy task statuses are not assignable through runtime status labels', async () => {
  const { getTaskStatusLabel } = await import('../styles/status');
  expect(() => getTaskStatusLabel('ready_for_review' as TaskStatus)).toThrow('未知任务状态');
  expect(() => getTaskStatusLabel('exported' as TaskStatus)).toThrow('未知任务状态');
});
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/app/routes.test.ts src/api/shared-contracts.test.ts
```

Expected: FAIL because route still uses `/mobile/sessions/:sessionId`, TaskStatus still includes legacy states, and status labels likely handle old values.

- [ ] **Step 4: Implement MVP task API types**

In `app/frontend/src/api/tasks.ts`:

```typescript
export type TaskStatus = 'uploading' | 'processing' | 'review' | 'done' | 'failed';

export interface CreateTaskResult {
  task_id: string;
  status: 'uploading';
  upload_token: string;
  mobile_upload_url: string;
}

export interface TaskSummary {
  task_id: string;
  status: TaskStatus;
  created_at: string;
  updated_at?: string;
  page_count: number;
  error_code?: string | null;
  error_message?: string | null;
  review_summary?: { status?: string | null; confirmed_count?: number; total_count?: number } | null;
  export_summary?: { last_exported_at?: string | null; formats?: string[]; files?: Array<{ format: string; relative_path: string }> };
}

export function createTask() {
  return apiRequest<CreateTaskResult>('/api/tasks', { method: 'POST' });
}

export function processTask(taskId: string) {
  return apiRequest<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/process`, { method: 'POST' });
}

export function completeTask(taskId: string) {
  return apiRequest<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/complete`, { method: 'POST' });
}
```

- [ ] **Step 5: Create mobile upload API**

Create `app/frontend/src/api/mobileUpload.ts`:

```typescript
import { apiRequest } from './client';
import type { TaskSummary } from './tasks';

export interface UploadedImage {
  page_id: string;
  task_id: string;
  page_no: number;
  preview_url?: string;
  image_width?: number | null;
  image_height?: number | null;
  uploaded_at: string;
}

export function uploadTaskImage(taskId: string, token: string, file: File, dimensions?: { image_width?: number; image_height?: number }) {
  const body = new FormData();
  body.append('image', file);
  if (dimensions?.image_width) body.append('image_width', String(dimensions.image_width));
  if (dimensions?.image_height) body.append('image_height', String(dimensions.image_height));
  return apiRequest<UploadedImage>(`/api/mobile-upload/${encodeURIComponent(taskId)}/images?token=${encodeURIComponent(token)}`, {
    method: 'POST',
    body,
  });
}

export function finishTaskUpload(taskId: string, token: string) {
  return apiRequest<TaskSummary>(`/api/mobile-upload/${encodeURIComponent(taskId)}/finish?token=${encodeURIComponent(token)}`, {
    method: 'POST',
  });
}
```

- [ ] **Step 6: Implement MVP routes and labels**

In `app/frontend/src/app/routes.tsx`:

```typescript
export const appRoutes = {
  workstation: { id: 'workstation', label: '工作台总览', path: '/' },
  mobileCapture: { id: 'mobileCapture', label: '手机上传', path: '/mobile/upload/:taskId' },
  tasks: { id: 'tasks', label: '任务管理', path: '/tasks' },
  review: { id: 'review', label: '人工审核', path: '/tasks/:taskId/review' },
  export: { id: 'export', label: '导出结果', path: '/tasks/:taskId/export' },
} as const satisfies Record<string, AppRoute>;

export const MOBILE_UPLOAD_PREFIX = '/mobile/upload/';

export function buildMobileUploadPath(taskId: string) {
  return `${MOBILE_UPLOAD_PREFIX}${encodeURIComponent(taskId)}`;
}
```

In `status.ts`, map only:

```typescript
const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  uploading: '上传中',
  processing: '处理中',
  review: '待审核',
  done: '已完成',
  failed: '失败',
};
```

- [ ] **Step 7: Run tests to verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/app/routes.test.ts src/api/shared-contracts.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src/api/tasks.ts app/frontend/src/api/mobileUpload.ts app/frontend/src/app/routes.tsx app/frontend/src/styles/status.ts app/frontend/src/api/shared-contracts.test.ts app/frontend/src/app/routes.test.ts
git rm app/frontend/src/api/captureSessions.test.ts
git commit -m "收敛前端共享路由和状态契约"
```

### Task 10: Workstation Creates Task QR, Not Capture Session

**Files:**
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- Modify: `app/frontend/src/components/workstation/CaptureQrDialog.tsx`
- Modify: `app/frontend/src/state/workstationStore.ts`
- Modify: `app/frontend/src/components/workstation/TaskOverview.tsx`
- Modify: `app/frontend/src/components/workstation/RecentTasks.tsx`
- Modify: `app/frontend/tests/fixtures/tasks.ts`
- Modify/Create tests near existing workstation components

- [ ] **Step 1: Write failing workstation tests**

In existing workstation test files or `app/frontend/src/pages/workstation/WorkstationPage.test.tsx`:

```typescript
it('creates an uploading task and shows task upload QR dialog', async () => {
  server.use(
    http.post('/api/tasks', () =>
      HttpResponse.json({
        data: {
          task_id: 'task_001',
          status: 'uploading',
          upload_token: 'token_001',
          mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001',
        },
      }),
    ),
  );

  render(<WorkstationPage />);
  await userEvent.click(screen.getByRole('button', { name: '新建任务' }));

  expect(await screen.findByText('task_001')).toBeInTheDocument();
  expect(screen.getByText('http://127.0.0.1:8081/mobile/upload/task_001?token=token_001')).toBeInTheDocument();
  expect(screen.queryByText(/会话过期|修订采集|取消采集/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/pages/workstation src/components/workstation
```

Expected: FAIL because workstation likely creates capture sessions or shows session-specific copy.

- [ ] **Step 3: Implement task QR behavior**

In `WorkstationPage.tsx`, call `createTask()`:

```typescript
const handleCreateTask = async () => {
  const task = await createTask();
  setQrTask(task);
  await reloadTasks();
};
```

In `CaptureQrDialog.tsx`, require:

```typescript
type CaptureQrDialogProps = {
  open: boolean;
  task: CreateTaskResult | null;
  uploadedCount?: number;
  onClose: () => void;
};
```

Render task content only:

```tsx
<p className="qr-dialog__task-id">{task.task_id}</p>
<QRCodeCanvas value={task.mobile_upload_url} />
<p>{task.mobile_upload_url}</p>
<p>已上传 {uploadedCount ?? 0} 张图片</p>
```

- [ ] **Step 4: Update statistics and recent task mapping**

In `workstationStore.ts`, aggregate:

```typescript
const initialCounts = { uploading: 0, processing: 0, review: 0, done: 0, failed: 0 };
```

Do not include `ready_for_review`, `confirmed`, or `exported`.

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/pages/workstation src/components/workstation
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/workstation/WorkstationPage.tsx app/frontend/src/components/workstation/CaptureQrDialog.tsx app/frontend/src/state/workstationStore.ts app/frontend/src/components/workstation/TaskOverview.tsx app/frontend/src/components/workstation/RecentTasks.tsx app/frontend/tests/fixtures/tasks.ts
git commit -m "工作台改为任务上传二维码"
```

### Task 11: Mobile Upload Page Without Quad Or Sorting

**Files:**
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CapturePageList.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CapturePhotoButton.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/CaptureFooter.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/mobileCapture.types.ts`
- Modify/Create: `app/frontend/tests/fixtures/mobileUpload.ts`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
- Delete or stop using: `app/frontend/src/pages/mobile-capture/CaptureQuadScreen.tsx`
- Delete or stop using: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`
- Delete or rewrite: `app/frontend/src/components/mobile-capture/QuadSelector.test.tsx`

- [ ] **Step 1: Write failing mobile upload tests**

In `MobileCapturePage.test.tsx`:

```typescript
it('uploads selected images directly to task and shows upload order', async () => {
  render(<MobileCapturePage taskId="task_001" token="token_001" />);
  const file = new File(['png'], 'page-1.png', { type: 'image/png' });

  await userEvent.upload(screen.getByLabelText('拍照/选择图片'), file);

  expect(await screen.findByText('第 1 页')).toBeInTheDocument();
  expect(screen.queryByText('四边形框选')).not.toBeInTheDocument();
  expect(screen.queryByText('重新框选')).not.toBeInTheDocument();
});

it('disables finish until at least one image uploaded', async () => {
  render(<MobileCapturePage taskId="task_001" token="token_001" />);

  expect(screen.getByRole('button', { name: '完成上传' })).toBeDisabled();
});

it('finish upload tells user to return to desktop', async () => {
  render(<MobileCapturePage taskId="task_001" token="token_001" initialImages={[{ page_id: 'page_001', task_id: 'task_001', page_no: 1, uploaded_at: '2026-05-19T10:00:00+08:00' }]} />);

  await userEvent.click(screen.getByRole('button', { name: '完成上传' }));

  expect(await screen.findByText('上传已完成，请回到电脑端查看处理结果')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/pages/mobile-capture/MobileCapturePage.test.tsx
```

Expected: FAIL because current mobile flow still contains capture session/quad behavior.

- [ ] **Step 3: Implement task-bound mobile page**

Use route params `taskId` and query param `token`:

```typescript
const { taskId = '' } = useParams();
const [searchParams] = useSearchParams();
const token = searchParams.get('token') ?? '';
```

On file selection:

```typescript
const handleFiles = async (files: FileList | null) => {
  if (!files || !taskId || !token) return;
  for (const file of Array.from(files)) {
    const uploaded = await uploadTaskImage(taskId, token, file);
    setImages((current) => [...current, uploaded]);
  }
};
```

Finish:

```typescript
const handleFinish = async () => {
  await finishTaskUpload(taskId, token);
  setFinished(true);
};
```

- [ ] **Step 4: Remove quad UI from mobile path**

Delete imports and route branches for:

```typescript
CaptureQuadScreen
QuadSelector
quad_points
replace image
drag sorting
```

The rendered page keeps:

```tsx
<CapturePhotoButton onFilesSelected={handleFiles} />
<CapturePageList images={images} />
<CaptureFooter canFinish={images.length > 0} onFinish={handleFinish} />
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/pages/mobile-capture/MobileCapturePage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx app/frontend/src/pages/mobile-capture/CapturePageList.tsx app/frontend/src/pages/mobile-capture/CapturePhotoButton.tsx app/frontend/src/pages/mobile-capture/CaptureFooter.tsx app/frontend/src/pages/mobile-capture/mobileCapture.types.ts app/frontend/tests/fixtures/mobileUpload.ts app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx
git rm app/frontend/src/pages/mobile-capture/CaptureQuadScreen.tsx app/frontend/src/components/mobile-capture/QuadSelector.tsx app/frontend/src/components/mobile-capture/QuadSelector.test.tsx
git commit -m "手机端只保留多图上传"
```

### Task 12: Tasks Management Page With Five-State Filters

**Files:**
- Modify/Create: `app/frontend/src/pages/tasks/TasksPage.tsx`
- Modify/Delete: `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`
- Modify/Create: `app/frontend/src/pages/tasks/TasksPage.test.tsx`
- Modify: `app/frontend/src/components/tasks/TaskList.tsx`
- Modify: `app/frontend/src/components/tasks/tasks.css`
- Modify: `app/frontend/src/app/App.tsx`

- [ ] **Step 1: Write failing task page tests**

Create `app/frontend/src/pages/tasks/TasksPage.test.tsx`:

```typescript
it('renders five MVP filters and task operations', async () => {
  render(<TasksPage />);

  expect(await screen.findByRole('button', { name: '全部' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '上传中' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '处理中' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '待审核' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '已完成' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '失败' })).toBeInTheDocument();
  expect(screen.queryByText('修订采集')).not.toBeInTheDocument();
  expect(screen.queryByText('取消会话')).not.toBeInTheDocument();
  expect(screen.queryByText('已导出')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/pages/tasks src/components/tasks
```

Expected: FAIL if only placeholder exists or filters still include legacy status.

- [ ] **Step 3: Implement `TasksPage`**

Create task filters:

```typescript
const filters: Array<{ label: string; status: TaskStatus | 'all' }> = [
  { label: '全部', status: 'all' },
  { label: '上传中', status: 'uploading' },
  { label: '处理中', status: 'processing' },
  { label: '待审核', status: 'review' },
  { label: '已完成', status: 'done' },
  { label: '失败', status: 'failed' },
];
```

Render operations by status:

```typescript
const operationsByStatus: Record<TaskStatus, string[]> = {
  uploading: ['查看二维码'],
  processing: ['查看进度'],
  review: ['进入审核', '重新处理', '导出'],
  done: ['查看结果', '导出', '重新处理'],
  failed: ['查看原因', '重新处理'],
};
```

Wire actions:

```tsx
{task.status === 'review' && <Link to={buildReviewPath(task.task_id)}>进入审核</Link>}
{task.status === 'done' && <Link to={buildReviewPath(task.task_id)}>查看结果</Link>}
{task.status === 'failed' && <span>{task.error_message ?? task.error_code}</span>}
```

- [ ] **Step 4: Mount in `App.tsx`**

Replace `TasksPlaceholder` route element with:

```tsx
<Route path="/tasks" element={<TasksPage />} />
```

- [ ] **Step 5: Run tests to verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/pages/tasks src/components/tasks
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/tasks app/frontend/src/components/tasks app/frontend/src/app/App.tsx
git commit -m "新增 MVP 任务管理页"
```

### Task 13: Review Page And Export Entrypoints

**Files:**
- Modify/Create: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify/Delete: `app/frontend/src/pages/review/ReviewPlaceholder.tsx`
- Modify/Create: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify: `app/frontend/src/components/review/ReviewSourcePanel.tsx`
- Modify: `app/frontend/src/components/review/FieldList.tsx`
- Modify: `app/frontend/src/components/export/ExportPanel.tsx`
- Modify: `app/frontend/src/components/export/ExportPanel.test.tsx`
- Modify: `app/frontend/src/api/review.ts`
- Modify: `app/frontend/src/api/export.ts`

- [ ] **Step 1: Write failing review page tests**

Create `app/frontend/src/pages/review/ReviewPage.test.tsx`:

```typescript
it('shows images, OCR text, editable fields, complete and export actions', async () => {
  render(<ReviewPage taskId="task_001" />);

  expect(await screen.findByText('OCR 文本')).toBeInTheDocument();
  expect(screen.getByLabelText('patient_name')).toHaveValue('张三');

  await userEvent.clear(screen.getByLabelText('patient_name'));
  await userEvent.type(screen.getByLabelText('patient_name'), '李四');
  await userEvent.click(screen.getByRole('button', { name: '保存审核结果' }));

  expect(await screen.findByText('已保存')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '标记完成' }));
  expect(await screen.findByText('已完成')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '导出 JSON' })).toBeEnabled();
  expect(screen.getByRole('button', { name: '导出 Excel' })).toBeEnabled();
});
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/pages/review src/components/review src/components/export
```

Expected: FAIL if review page is still placeholder or export panel expects `confirmed/exported`.

- [ ] **Step 3: Implement review API**

In `app/frontend/src/api/review.ts`:

```typescript
export type FieldStatus = 'unreviewed' | 'confirmed' | 'modified';

export interface ReviewField {
  field_key: string;
  label?: string;
  value: string;
  status: FieldStatus;
}

export interface ReviewResult {
  fields: ReviewField[];
  ocr_text?: string;
  pages?: Array<{ page_id: string; page_no: number; preview_url?: string }>;
}

export function getReview(taskId: string) {
  return apiRequest<{ task_id: string; status: TaskStatus; review_result: ReviewResult }>(`/api/tasks/${encodeURIComponent(taskId)}/review`);
}

export function saveReview(taskId: string, fields: ReviewField[]) {
  return apiRequest<{ task_id: string; review_result: ReviewResult }>(`/api/tasks/${encodeURIComponent(taskId)}/review`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields }),
  });
}
```

- [ ] **Step 4: Implement review page UI**

Render three columns:

```tsx
<section aria-label="任务图片">
  <ReviewSourcePanel pages={review.pages ?? []} />
</section>
<section aria-label="OCR 文本">
  <pre>{review.ocr_text}</pre>
</section>
<section aria-label="结构化字段">
  <FieldList fields={fields} onChange={setFields} />
  <button onClick={handleSave}>保存审核结果</button>
  <button onClick={handleComplete}>标记完成</button>
  <ExportPanel taskId={taskId} status={taskStatus} />
</section>
```

`FieldList` status changes:

```typescript
const fieldStatuses: FieldStatus[] = ['unreviewed', 'confirmed', 'modified'];
```

- [ ] **Step 5: Update export panel state rules**

In `ExportPanel.tsx`, enable export for:

```typescript
const canExport = status === 'review' || status === 'done';
```

Do not show or expect `exported`.

- [ ] **Step 6: Run tests to verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/pages/review src/components/review src/components/export
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/review app/frontend/src/components/review app/frontend/src/components/export app/frontend/src/api/review.ts app/frontend/src/api/export.ts
git commit -m "新增 MVP 审核和导出界面"
```

---

## E2E And Acceptance Phase

### Task 14: Frontend E2E Success And Failure Flows

**Files:**
- Modify: `app/frontend/tests/e2e/workstation.spec.ts`
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`
- Modify/Create: `app/frontend/tests/fixtures/tasks.ts`
- Modify/Create: `app/frontend/tests/fixtures/mobileUpload.ts`
- Delete or stop using: `app/frontend/tests/fixtures/sessions.ts`
- Delete or stop using: session-based entries in `app/frontend/tests/fixtures/uploads.ts`

- [ ] **Step 1: Write MVP success E2E**

In `app/frontend/tests/e2e/current-workflows.spec.ts`:

```typescript
test('MVP flow: create task, upload images, finish, review, done, export', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '新建任务' }).click();
  await expect(page.getByText('task_001')).toBeVisible();
  await expect(page.getByText('/mobile/upload/task_001')).toBeVisible();

  await page.goto('/mobile/upload/task_001?token=token_001');
  await page.getByLabel('拍照/选择图片').setInputFiles([
    'tests/fixtures/images/page-1.png',
    'tests/fixtures/images/page-2.png',
    'tests/fixtures/images/page-3.png',
  ]);
  await expect(page.getByText('第 1 页')).toBeVisible();
  await expect(page.getByText('第 3 页')).toBeVisible();
  await page.getByRole('button', { name: '完成上传' }).click();
  await expect(page.getByText('上传已完成，请回到电脑端查看处理结果')).toBeVisible();

  await page.goto('/tasks/task_001/review');
  await page.getByLabel('patient_name').fill('李四');
  await page.getByRole('button', { name: '保存审核结果' }).click();
  await page.getByRole('button', { name: '标记完成' }).click();
  await expect(page.getByText('已完成')).toBeVisible();
  await expect(page.getByRole('button', { name: '导出 JSON' })).toBeEnabled();
  await expect(page.getByRole('button', { name: '导出 Excel' })).toBeEnabled();
});
```

- [ ] **Step 2: Write MVP failure E2E**

In `workstation.spec.ts`:

```typescript
test('failed algorithm task shows reason in task management', async ({ page }) => {
  await page.goto('/tasks');

  await expect(page.getByText('task_failed_001')).toBeVisible();
  await expect(page.getByText('失败')).toBeVisible();
  await expect(page.getByText('算法模块未配置')).toBeVisible();
  await expect(page.getByRole('button', { name: '重新处理' })).toBeVisible();
  await expect(page.getByText('修订采集')).toHaveCount(0);
  await expect(page.getByText('取消会话')).toHaveCount(0);
});
```

- [ ] **Step 3: Run E2E to verify RED**

Run:

```bash
cd app/frontend
npm run test:e2e
```

Expected: FAIL until MSW fixtures and pages are updated to MVP routes and statuses.

- [ ] **Step 4: Update frontend E2E fixtures**

Replace session fixtures with task and mobile upload fixtures:

```typescript
export const task001 = {
  task_id: 'task_001',
  status: 'uploading',
  created_at: '2026-05-19T10:00:00+08:00',
  page_count: 0,
  error_code: null,
  error_message: null,
  export_summary: { last_exported_at: null, formats: [], files: [] },
};

export const failedTask = {
  task_id: 'task_failed_001',
  status: 'failed',
  created_at: '2026-05-19T10:00:00+08:00',
  page_count: 3,
  error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
  error_message: '算法模块未配置',
};
```

Mock handlers:

```typescript
http.post('/api/tasks', () => HttpResponse.json({ data: { task_id: 'task_001', status: 'uploading', upload_token: 'token_001', mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001' } })),
http.post('/api/mobile-upload/:taskId/images', () => HttpResponse.json({ data: { page_id: 'page_001', task_id: 'task_001', page_no: 1, uploaded_at: '2026-05-19T10:01:00+08:00' } }, { status: 201 })),
http.post('/api/mobile-upload/:taskId/finish', () => HttpResponse.json({ data: { ...task001, status: 'review', page_count: 3 } })),
```

- [ ] **Step 5: Run E2E to verify GREEN**

Run:

```bash
cd app/frontend
npm run test:e2e
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/tests/e2e app/frontend/tests/fixtures
git rm app/frontend/tests/fixtures/sessions.ts
git commit -m "收口前端 MVP 端到端流程"
```

### Task 15: Full Acceptance Gate And Static Scan

**Files:**
- Modify only if failures identify stale references:
  - `app/backend/**`
  - `app/frontend/**`
  - `docs/PRD任务清单.md`

- [ ] **Step 1: Run backend full suite**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend unit/type/build**

Run:

```bash
cd app/frontend
npm run test
npm run typecheck
npm run build
```

Expected: all commands PASS.

- [ ] **Step 3: Run frontend E2E**

Run:

```bash
cd app/frontend
npm run test:e2e
```

Expected: PASS.

- [ ] **Step 4: Run static scan for removed concepts**

Run:

```bash
rg -n "capture-sessions|CaptureSession|SESSION_|INVALID_QUAD_POINTS|quad_points|capturing|uploaded|ready_for_review|exported|/mobile/sessions" app docs
```

Expected allowed matches:

- Historical plans/specs that explicitly describe removed behavior.
- This implementation plan.
- `docs/superpowers/specs/2026-05-19-mvp-simplification-design.md` sections that say old behavior is removed.
- `docs/PRD任务清单.md` post-MVP or `需收敛` notes until updated.

Expected disallowed matches:

- `app/backend` production code.
- `app/frontend` production code.
- Current MVP backend/frontend tests.
- `docs/Shared/state-enums.md`.
- `docs/Shared/error-codes.md`.
- Positive PRD text in `docs/产品PRD.md`.

- [ ] **Step 5: Update PRD task checklist after implementation**

In `docs/PRD任务清单.md`, update only items proven by passing tests. Example updates after all phases pass:

```markdown
| BE-MVP-01 任务创建和二维码上传入口 | 已完成 | `app/backend/routes/task.py`、`app/backend/routes/mobile.py` | 创建 `uploading` 任务并生成手机上传 URL；不再创建采集会话 |
| BE-MVP-02 图片上传和页序 | 已完成 | `app/backend/services/page_service.py` | 上传原图，页序按上传成功顺序确定；不做 quad、补拍替换、拖拽排序 |
| BE-MVP-03 简化任务生命周期 | 已完成 | `app/backend/services/task_service.py` | 状态统一为 `uploading / processing / review / done / failed` |
```

Do not mark frontend pages complete until their Vitest and E2E coverage is green.

- [ ] **Step 6: Commit acceptance cleanup**

```bash
git add docs/PRD任务清单.md app/backend app/frontend
git commit -m "完成 MVP 收敛验收清理"
```

### Task 16: Optional Dead-Code Removal After All Gates Pass

**Files:**
- Delete if unreferenced:
  - `app/backend/routes/capture_session.py`
  - `app/backend/services/session_service.py`
  - `app/backend/services/quad_validator.py`
  - stale frontend session or quad files not deleted earlier

- [ ] **Step 1: Verify files are unreferenced**

Run:

```bash
rg -n "capture_session|SessionService|quad_validator|QuadSelector|CaptureQuadScreen" app
```

Expected: matches only in files selected for deletion or historical comments.

- [ ] **Step 2: Delete unreferenced production files**

Run:

```bash
git rm app/backend/routes/capture_session.py app/backend/services/session_service.py app/backend/services/quad_validator.py
```

If a file is still referenced by an import in production or current tests, remove the import in the same commit and rerun the relevant tests.

- [ ] **Step 3: Run final verification**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
cd app/frontend
npm run test
npm run typecheck
npm run build
npm run test:e2e
```

Expected: all commands PASS.

- [ ] **Step 4: Commit dead-code removal**

```bash
git add app
git commit -m "删除旧会话和框选孤立代码"
```

---

## Execution Notes

- Implement tasks in order. Do not start frontend phase until backend MVP API contracts are green.
- Keep commits small and Chinese.
- Do not preserve old public APIs for compatibility. This MVP explicitly removes session and quad from the positive path.
- Do not implement OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则兜底抽取。
- Do not add runtime network dependencies, CDN, telemetry, or model downloads.
- If an old test fails because it asserts removed behavior, rewrite it to MVP behavior or delete it when the behavior is purely historical.

