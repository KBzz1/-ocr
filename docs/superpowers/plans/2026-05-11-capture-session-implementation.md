# 采集会话管理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 PR-BE-002 采集会话管理：创建二维码会话、查询状态、过期判定、页面清单编辑、完成采集锁定、页序固化、finish 幂等和最小 Task 桩。

**Architecture:** `SessionService` 作为无 Flask 请求对象依赖的业务层，复用 `JsonStore` 持久化 `data/sessions/` 和 `data/tasks/`。会话 JSON 内维护轻量 `pages` 清单，用于 PR-BE-002 的新增/删除/排序/补拍和 finish 页序固化；真实图片文件、MIME/大小校验、quad_points、图片尺寸保存留给 PR-BE-003。

**Tech Stack:** Python 3.12 via conda env `manzufei_ocr`, Flask, pytest, JsonStore

---

## 范围边界

本计划覆盖：

- BE-SES-001：创建会话生成唯一 `session_id`
- BE-SES-002：创建会话记录 `created_at`、`expires_at`、`status: active`
- BE-SES-003：`POST /api/capture-sessions` 返回 201、会话信息和二维码 URL
- BE-SES-004：`GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间
- BE-SES-005：过期会话被判定为 `expired`
- BE-SES-006：过期会话写操作返回 409 和 `SESSION_EXPIRED`（本阶段用页面清单写操作验证；真实上传端点在 PR-BE-003 复用同一 guard）
- BE-SES-007：完成采集前允许新增、删除、排序、补拍页面清单
- BE-SES-008：`POST /api/mobile/{session_id}/finish` 后会话变为 `locked`
- BE-SES-009：`locked` 会话禁止新增、删除、排序页面，返回 `SESSION_LOCKED`
- BE-SES-010：完成采集后页面顺序固化，Task 桩记录固化页序
- BE-SES-011：没有已成功上传页面的会话不可完成采集，返回 `SESSION_EMPTY`

本计划不覆盖：

- 真实图片上传、文件类型/MIME/大小校验、文件名净化、图片落盘
- `quad_points`、图片宽高、原图路径、处理后图片路径
- OCR、LLM、图像预处理、裁剪、透视矫正、规则抽取
- 任务从 `uploaded` 到 `processing` / `ready_for_review` / `failed` 的生命周期编排
- 手机端前端页面和二维码图片生成

## 数据模型

### Session JSON

路径：`data/sessions/{session_id}.json`

```json
{
  "session_id": "uuid4",
  "status": "active",
  "created_at": "2026-05-12T10:00:00+00:00",
  "expires_at": "2026-05-12T10:30:00+00:00",
  "qr_code_url": "http://192.168.1.5:8081/mobile/uuid4",
  "page_count": 0,
  "pages": [],
  "locked_at": null,
  "task_id": null
}
```

页面清单项只保留 PR-BE-002 必需的顺序元数据：

```json
{
  "page_id": "uuid4",
  "page_no": 1,
  "created_at": "2026-05-12T10:01:00+00:00",
  "upload_ref": null
}
```

`upload_ref` 本阶段固定为 `null`。PR-BE-003 会把真实文件路径和采集元数据接入页面项或页面元数据文件。

PR-BE-003 上传成功后可通过 `SessionService.attach_page_upload(session_id, page_id, upload_ref)` 把页面元数据相对路径写回对应页面项。会话 `pages` 仍是唯一页序来源。

### Task 桩 JSON

路径：`data/tasks/{task_id}.json`

```json
{
  "task_id": "uuid4",
  "session_id": "uuid4",
  "status": "uploaded",
  "created_at": "2026-05-12T10:05:00+00:00",
  "page_count": 2,
  "page_order": ["page-1", "page-2"],
  "source": "capture_session"
}
```

Task 桩只表达采集已完成并形成待处理任务，不实现任务处理、算法调用、失败重试、审核或导出。

## API 契约

- `POST /api/capture-sessions`
- `GET /api/capture-sessions/{session_id}`
- `POST /api/capture-sessions/{session_id}/pages`
- `DELETE /api/capture-sessions/{session_id}/pages/{page_id}`
- `PUT /api/capture-sessions/{session_id}/pages/order`
- `POST /api/mobile/{session_id}/finish`

页面清单 API 是 PR-BE-002 的会话编辑骨架，不接收图片文件。

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/config/default.yaml` | MODIFY | 新增 `sessions.capture_session_ttl_minutes` |
| `app/backend/config.py` | MODIFY | 展平并校验 `capture_session_ttl_minutes` |
| `app/backend/tests/test_config.py` | MODIFY | TTL 配置测试 |
| `app/backend/services/__init__.py` | CREATE | service 包 |
| `app/backend/services/session_service.py` | CREATE | 会话业务逻辑 |
| `app/backend/tests/test_session_service.py` | CREATE | 单元测试 |
| `app/backend/tests/test_capture_session.py` | CREATE | API 集成测试 |
| `app/backend/routes/capture_session.py` | CREATE | 会话和页面清单 API |
| `app/backend/routes/mobile.py` | CREATE | finish API |
| `app/backend/__init__.py` | MODIFY | 注入 `SessionService` 并注册 Blueprint |

---

### Task 1: Config — capture_session_ttl_minutes

**Files:**
- Modify: `app/backend/tests/test_config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/backend/config.py`

- [ ] **Step 1: 写失败测试**

在 `app/backend/tests/test_config.py` 末尾追加：

```python
class TestSessionConfig:
    def test_default_capture_session_ttl(self):
        config = load_config()
        assert config["capture_session_ttl_minutes"] == 30

    def test_capture_session_ttl_from_yaml(self, tmp_path):
        import yaml

        default_yaml = {
            "sessions": {"capture_session_ttl_minutes": 15},
        }
        with open(tmp_path / "default.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert config["capture_session_ttl_minutes"] == 15

    def test_capture_session_ttl_must_be_positive(self, tmp_path):
        import yaml
        import pytest

        default_yaml = {
            "sessions": {"capture_session_ttl_minutes": 0},
        }
        with open(tmp_path / "default.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(default_yaml, f)

        with pytest.raises(ValueError, match="采集会话 TTL"):
            load_config(str(tmp_path))
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::TestSessionConfig -v
```

Expected: FAIL，至少 `KeyError: 'capture_session_ttl_minutes'`。

- [ ] **Step 3: 修改默认配置**

在 `app/config/default.yaml` 末尾追加：

```yaml

sessions:
  capture_session_ttl_minutes: 30
```

- [ ] **Step 4: 修改 `config.py`**

`DEFAULT_CONFIG` 新增：

```python
    "capture_session_ttl_minutes": 30,
```

`_flatten_config` 中读取 `sessions`：

```python
    sessions_config = raw.get("sessions", {})
    if "capture_session_ttl_minutes" in sessions_config:
        flattened["capture_session_ttl_minutes"] = sessions_config["capture_session_ttl_minutes"]
```

`_validate_config` 中追加：

```python
    ttl = config["capture_session_ttl_minutes"]
    if not isinstance(ttl, int) or ttl <= 0:
        raise ValueError(f"采集会话 TTL 必须为正整数，当前值: {ttl}")
```

- [ ] **Step 5: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py -v
```

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add app/config/default.yaml app/backend/config.py app/backend/tests/test_config.py
git commit -m "feat: 新增采集会话 TTL 配置"
```

---

### Task 2: SessionService create/get

**Files:**
- Create: `app/backend/services/__init__.py`
- Create: `app/backend/services/session_service.py`
- Create: `app/backend/tests/test_session_service.py`

- [ ] **Step 1: 写失败测试**

创建 `app/backend/tests/test_session_service.py`：

```python
import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path, lan_addresses=None, ttl_minutes=30):
    from app.backend.services.session_service import SessionService

    return SessionService(
        store=JsonStore(str(tmp_path)),
        lan_addresses=lan_addresses if lan_addresses is not None else ["192.168.1.5:8081"],
        ttl_minutes=ttl_minutes,
    )


class TestSessionCreateGet:
    def test_create_returns_unique_session_id(self, tmp_path):
        service = make_service(tmp_path)
        first = service.create()
        second = service.create()

        assert first["session_id"]
        assert second["session_id"]
        assert first["session_id"] != second["session_id"]

    def test_create_sets_active_status_timestamps_and_empty_pages(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        assert session["status"] == "active"
        assert session["page_count"] == 0
        assert session["pages"] == []
        assert session["locked_at"] is None
        assert session["task_id"] is None

        created = datetime.fromisoformat(session["created_at"])
        expires = datetime.fromisoformat(session["expires_at"])
        assert timedelta(minutes=29) < expires - created < timedelta(minutes=31)

    def test_create_persists_session_json(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        path = tmp_path / "sessions" / f"{session['session_id']}.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["session_id"] == session["session_id"]
        assert data["status"] == "active"

    def test_create_qr_code_url_uses_first_lan_address(self, tmp_path):
        service = make_service(tmp_path, lan_addresses=["10.0.0.2:8081", "192.168.1.5:8081"])
        session = service.create()

        assert session["qr_code_url"] == f"http://10.0.0.2:8081/mobile/{session['session_id']}"

    def test_create_qr_code_url_is_none_without_lan_address(self, tmp_path):
        service = make_service(tmp_path, lan_addresses=[])
        session = service.create()

        assert session["qr_code_url"] is None

    def test_get_returns_session(self, tmp_path):
        service = make_service(tmp_path)
        created = service.create()

        fetched = service.get(created["session_id"])

        assert fetched["session_id"] == created["session_id"]
        assert fetched["status"] == "active"

    def test_get_nonexistent_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.get("missing")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_get_auto_expires_active_session_and_persists(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        fetched = service.get(session["session_id"])

        assert fetched["status"] == "expired"
        persisted = JsonStore(str(tmp_path)).read(f"sessions/{session['session_id']}.json")
        assert persisted["status"] == "expired"
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py::TestSessionCreateGet -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.backend.services'`。

- [ ] **Step 3: 实现最小代码**

创建 `app/backend/services/__init__.py`，内容为空。

创建 `app/backend/services/session_service.py`：

```python
import uuid
from datetime import datetime, timedelta, timezone

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class SessionService:
    def __init__(self, store: JsonStore, lan_addresses: list[str], ttl_minutes: int):
        self._store = store
        self._lan_addresses = lan_addresses
        self._ttl_minutes = ttl_minutes

    def create(self) -> dict:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self._ttl_minutes)
        qr_code_url = None
        if self._lan_addresses:
            qr_code_url = f"http://{self._lan_addresses[0]}/mobile/{session_id}"

        session = {
            "session_id": session_id,
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "qr_code_url": qr_code_url,
            "page_count": 0,
            "pages": [],
            "locked_at": None,
            "task_id": None,
        }
        self._store.write(f"sessions/{session_id}.json", session)
        return session

    def get(self, session_id: str) -> dict:
        session = self._store.read(f"sessions/{session_id}.json")
        if session is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND)

        if session["status"] == "active":
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                session["status"] = "expired"
                self._store.write(f"sessions/{session_id}.json", session)

        return session
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py::TestSessionCreateGet -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/services app/backend/tests/test_session_service.py
git commit -m "feat: 实现采集会话创建与查询"
```

---

### Task 3: 页面清单编辑与写操作守卫

**Files:**
- Modify: `app/backend/tests/test_session_service.py`
- Modify: `app/backend/services/session_service.py`

- [ ] **Step 1: 写失败测试**

在 `app/backend/tests/test_session_service.py` 末尾追加：

```python
class TestSessionPages:
    def test_add_page_appends_page_and_updates_page_count(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        updated = service.add_page(session["session_id"])

        assert updated["page_count"] == 1
        assert len(updated["pages"]) == 1
        assert updated["pages"][0]["page_no"] == 1
        assert updated["pages"][0]["upload_ref"] is None

    def test_add_page_assigns_incrementing_page_no(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        first = service.add_page(session["session_id"])
        second = service.add_page(session["session_id"])

        assert [p["page_no"] for p in second["pages"]] == [1, 2]
        assert first["pages"][0]["page_id"] != second["pages"][1]["page_id"]

    def test_delete_page_removes_page_and_renumbers(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])
        service.add_page(session["session_id"])
        current = service.add_page(session["session_id"])
        remove_id = current["pages"][1]["page_id"]

        updated = service.delete_page(session["session_id"], remove_id)

        assert updated["page_count"] == 2
        assert [p["page_no"] for p in updated["pages"]] == [1, 2]
        assert remove_id not in [p["page_id"] for p in updated["pages"]]

    def test_delete_missing_page_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        with pytest.raises(AppError) as exc_info:
            service.delete_page(session["session_id"], "missing-page")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_reorder_pages_persists_requested_order_and_renumbers(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])
        service.add_page(session["session_id"])
        current = service.add_page(session["session_id"])
        order = [current["pages"][2]["page_id"], current["pages"][0]["page_id"], current["pages"][1]["page_id"]]

        updated = service.reorder_pages(session["session_id"], order)

        assert [p["page_id"] for p in updated["pages"]] == order
        assert [p["page_no"] for p in updated["pages"]] == [1, 2, 3]

    def test_reorder_with_missing_page_id_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        current = service.add_page(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.reorder_pages(session["session_id"], [current["pages"][0]["page_id"], "missing"])

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_expired_session_rejects_page_writes(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        with pytest.raises(AppError) as exc_info:
            service.add_page(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

    def test_locked_session_rejects_page_writes(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.finish(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.add_page(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_LOCKED.code
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py::TestSessionPages -v
```

Expected: FAIL，`AttributeError`，因为 `add_page` / `delete_page` / `reorder_pages` / `finish` 尚未实现。

- [ ] **Step 3: 实现页面清单方法和写操作守卫**

在 `SessionService` 中追加：

```python
    def _persist_session(self, session: dict) -> dict:
        self._store.write(f"sessions/{session['session_id']}.json", session)
        return session

    def _ensure_editable(self, session: dict) -> None:
        if session["status"] == "expired":
            raise AppError(ErrorCode.SESSION_EXPIRED)
        if session["status"] == "locked":
            raise AppError(ErrorCode.SESSION_LOCKED)
        if session["status"] == "cancelled":
            raise AppError(ErrorCode.SESSION_LOCKED)

    def _renumber_pages(self, pages: list[dict]) -> list[dict]:
        for index, page in enumerate(pages, start=1):
            page["page_no"] = index
        return pages

    def add_page(self, session_id: str, upload_ref=None) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        page = {
            "page_id": str(uuid.uuid4()),
            "page_no": len(session["pages"]) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "upload_ref": upload_ref,
        }
        session["pages"].append(page)
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def delete_page(self, session_id: str, page_id: str) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        pages = [p for p in session["pages"] if p["page_id"] != page_id]
        if len(pages) == len(session["pages"]):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        session["pages"] = self._renumber_pages(pages)
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def reorder_pages(self, session_id: str, page_ids: list[str]) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        page_by_id = {p["page_id"]: p for p in session["pages"]}
        if set(page_ids) != set(page_by_id.keys()) or len(page_ids) != len(page_by_id):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        session["pages"] = self._renumber_pages([page_by_id[page_id] for page_id in page_ids])
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)
```

此步骤暂时需要一个最小 `finish` 占位使 locked guard 测试可运行：

```python
    def finish(self, session_id: str) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)
        session["status"] = "locked"
        session["locked_at"] = datetime.now(timezone.utc).isoformat()
        return self._persist_session(session)
```

Task 4 会用失败测试驱动补齐 Task 桩、页序固化和幂等。

- [ ] **Step 4: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py::TestSessionPages -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_session_service.py app/backend/services/session_service.py
git commit -m "feat: 实现采集会话页面清单编辑守卫"
```

---

### Task 4: finish 锁定、页序固化和 Task 桩

**Files:**
- Modify: `app/backend/tests/test_session_service.py`
- Modify: `app/backend/services/session_service.py`

- [ ] **Step 1: 写失败测试**

在 `app/backend/tests/test_session_service.py` 末尾追加：

```python
class TestSessionFinish:
    def test_finish_locks_active_session_and_sets_locked_at(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        finished = service.finish(session["session_id"])

        assert finished["status"] == "locked"
        assert finished["locked_at"] is not None

    def test_finish_creates_task_stub_with_frozen_page_order(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])
        service.add_page(session["session_id"])
        current = service.get(session["session_id"])
        expected_order = [p["page_id"] for p in current["pages"]]

        finished = service.finish(session["session_id"])

        task = JsonStore(str(tmp_path)).read(f"tasks/{finished['task_id']}.json")
        assert task["task_id"] == finished["task_id"]
        assert task["session_id"] == session["session_id"]
        assert task["status"] == "uploaded"
        assert task["page_count"] == 2
        assert task["page_order"] == expected_order
        assert task["source"] == "capture_session"

    def test_finish_persists_task_id_to_session(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        finished = service.finish(session["session_id"])
        persisted = JsonStore(str(tmp_path)).read(f"sessions/{session['session_id']}.json")

        assert persisted["task_id"] == finished["task_id"]

    def test_finish_idempotent_on_locked_session(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])

        first = service.finish(session["session_id"])
        second = service.finish(session["session_id"])

        assert second["task_id"] == first["task_id"]
        assert second["locked_at"] == first["locked_at"]
        assert len(os.listdir(tmp_path / "tasks")) == 1

    def test_finish_expired_session_raises_session_expired(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        with pytest.raises(AppError) as exc_info:
            service.finish(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

    def test_finish_nonexistent_session_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.finish("missing")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py::TestSessionFinish -v
```

Expected: FAIL，因为 Task 桩和幂等尚未实现。

- [ ] **Step 3: 替换 `finish` 实现**

用以下实现替换 Task 3 中的占位 `finish`：

```python
    def finish(self, session_id: str) -> dict:
        session = self.get(session_id)

        if session["status"] == "locked":
            return session

        self._ensure_editable(session)

        now = datetime.now(timezone.utc)
        task_id = str(uuid.uuid4())
        page_order = [page["page_id"] for page in session["pages"]]
        task = {
            "task_id": task_id,
            "session_id": session_id,
            "status": "uploaded",
            "created_at": now.isoformat(),
            "page_count": len(page_order),
            "page_order": page_order,
            "source": "capture_session",
        }
        self._store.write(f"tasks/{task_id}.json", task)

        session["status"] = "locked"
        session["locked_at"] = now.isoformat()
        session["task_id"] = task_id
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_session_service.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_session_service.py app/backend/services/session_service.py
git commit -m "feat: 实现采集完成锁定与页序固化"
```

---

### Task 5: API 集成测试先行

**Files:**
- Create: `app/backend/tests/test_capture_session.py`

- [ ] **Step 1: 写 API 失败测试**

创建 `app/backend/tests/test_capture_session.py`：

```python
import os
import uuid
from datetime import datetime, timedelta, timezone

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
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]


class TestCaptureSessionAPI:
    def test_create_session_returns_201_with_qr_url(self, client):
        data = create_session(client)

        assert data["status"] == "active"
        assert data["page_count"] == 0
        assert data["qr_code_url"].startswith("http://192.168.1.5:8081/mobile/")
        assert "created_at" in data
        assert "expires_at" in data

    def test_get_session_returns_current_status_and_pages(self, client):
        created = create_session(client)

        resp = client.get(f"/api/capture-sessions/{created['session_id']}")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["session_id"] == created["session_id"]
        assert data["status"] == "active"
        assert data["page_count"] == 0
        assert data["pages"] == []

    def test_get_nonexistent_session_returns_404(self, client):
        resp = client.get("/api/capture-sessions/missing")

        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "SESSION_NOT_FOUND"

    def test_add_page_before_finish_returns_201(self, client):
        created = create_session(client)

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["page_count"] == 1
        assert data["pages"][0]["page_no"] == 1

    def test_delete_page_before_finish_returns_200(self, client):
        created = create_session(client)
        added = client.post(f"/api/capture-sessions/{created['session_id']}/pages").get_json()["data"]
        page_id = added["pages"][0]["page_id"]

        resp = client.delete(f"/api/capture-sessions/{created['session_id']}/pages/{page_id}")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["page_count"] == 0

    def test_reorder_pages_before_finish_returns_200(self, client):
        created = create_session(client)
        client.post(f"/api/capture-sessions/{created['session_id']}/pages")
        current = client.post(f"/api/capture-sessions/{created['session_id']}/pages").get_json()["data"]
        order = [current["pages"][1]["page_id"], current["pages"][0]["page_id"]]

        resp = client.put(
            f"/api/capture-sessions/{created['session_id']}/pages/order",
            json={"page_ids": order},
        )

        assert resp.status_code == 200
        assert [p["page_id"] for p in resp.get_json()["data"]["pages"]] == order
        assert [p["page_no"] for p in resp.get_json()["data"]["pages"]] == [1, 2]

    def test_finish_locks_session_and_returns_task_id(self, client):
        created = create_session(client)

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "locked"
        assert data["task_id"] is not None
        assert data["locked_at"] is not None

    def test_finish_idempotent_returns_same_task_id(self, client):
        created = create_session(client)

        first = client.post(f"/api/mobile/{created['session_id']}/finish").get_json()["data"]
        second = client.post(f"/api/mobile/{created['session_id']}/finish").get_json()["data"]

        assert second["task_id"] == first["task_id"]

    def test_locked_session_rejects_page_writes(self, client):
        created = create_session(client)
        client.post(f"/api/mobile/{created['session_id']}/finish")

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_expired_session_rejects_page_writes(self, client):
        created = create_session(client)
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])
        session = store.read(f"sessions/{created['session_id']}.json")
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store.write(f"sessions/{created['session_id']}.json", session)

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_EXPIRED"

    def test_finish_expired_session_returns_409(self, client):
        created = create_session(client)
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])
        session = store.read(f"sessions/{created['session_id']}.json")
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store.write(f"sessions/{created['session_id']}.json", session)

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_EXPIRED"
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py -v
```

Expected: FAIL，`/api/capture-sessions` 和页面清单路由不存在，返回 404。

- [ ] **Step 3: Commit 测试**

```bash
git add app/backend/tests/test_capture_session.py
git commit -m "test: 增加采集会话 API 行为测试"
```

---

### Task 6: API routes 和 app factory 布线

**Files:**
- Create: `app/backend/routes/capture_session.py`
- Create: `app/backend/routes/mobile.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: 创建 `capture_session.py`**

```python
from flask import Blueprint, current_app, request

from ..responses import success

capture_session_bp = Blueprint("capture_session", __name__)


def _service():
    return current_app.config["SESSION_SERVICE"]


@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    session = _service().create()
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "created_at": session["created_at"],
            "expires_at": session["expires_at"],
            "qr_code_url": session["qr_code_url"],
            "page_count": session["page_count"],
        },
        status=201,
    )


@capture_session_bp.route("/api/capture-sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    return success(data=_service().get(session_id))


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages", methods=["POST"])
def add_page(session_id):
    return success(data=_service().add_page(session_id), status=201)


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages/<page_id>", methods=["DELETE"])
def delete_page(session_id, page_id):
    return success(data=_service().delete_page(session_id, page_id))


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages/order", methods=["PUT"])
def reorder_pages(session_id):
    payload = request.get_json(silent=True) or {}
    page_ids = payload.get("page_ids", [])
    return success(data=_service().reorder_pages(session_id, page_ids))
```

- [ ] **Step 2: 创建 `mobile.py`**

```python
from flask import Blueprint, current_app

from ..responses import success

mobile_bp = Blueprint("mobile", __name__)


def _service():
    return current_app.config["SESSION_SERVICE"]


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    session = _service().finish(session_id)
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "locked_at": session["locked_at"],
            "task_id": session["task_id"],
        }
    )
```

- [ ] **Step 3: 修改 `create_backend_app`**

在 `app/backend/__init__.py` 中 `register_error_handlers(app)` 后初始化服务：

```python
    from .storage.json_store import JsonStore
    from .services.session_service import SessionService

    store = JsonStore(config["storage_dir"])
    app.config["SESSION_SERVICE"] = SessionService(
        store=store,
        lan_addresses=app.config["LAN_ADDRESSES"],
        ttl_minutes=config["capture_session_ttl_minutes"],
    )
```

在系统路由注册后追加：

```python
    from .routes.capture_session import capture_session_bp
    from .routes.mobile import mobile_bp
    app.register_blueprint(capture_session_bp)
    app.register_blueprint(mobile_bp)
```

- [ ] **Step 4: 运行 API 测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/routes/capture_session.py app/backend/routes/mobile.py app/backend/__init__.py
git commit -m "feat: 实现采集会话 API"
```

---

### Task 7: BDD 对照验证和全量回归

- [ ] **Step 1: 运行单元测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py app/backend/tests/test_session_service.py -v
```

Expected: PASS。

- [ ] **Step 2: 运行 API 集成测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py -v
```

Expected: PASS。

- [ ] **Step 3: 运行后端全量测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS。

- [ ] **Step 4: BDD 场景对照**

确认以下 BDD 场景均有测试覆盖：

| BDD 场景 | 覆盖测试 |
|----------|----------|
| 创建采集会话并生成二维码 | `test_create_session_returns_201_with_qr_url` |
| 查询会话信息 | `test_get_session_returns_current_status_and_pages` |
| 会话过期后拒绝上传 | `test_expired_session_rejects_page_writes` 作为上传 guard 骨架验证 |
| 采集完成前允许编辑页面列表 | `test_add_page_before_finish_returns_201`、`test_delete_page_before_finish_returns_200`、`test_reorder_pages_before_finish_returns_200` |
| 完成采集后会话锁定 | `test_finish_locks_session_and_returns_task_id` |
| 锁定后禁止编辑 | `test_locked_session_rejects_page_writes` |
| 重复完成采集幂等 | `test_finish_idempotent_returns_same_task_id` |
| 会话过期后不可完成采集 | `test_finish_expired_session_returns_409` |
| 无已上传页面时不可完成采集 | `test_finish_empty_session_returns_400`、`test_finish_empty_session_raises_session_empty`、`test_finish_placeholder_page_without_upload_ref_returns_400`、`test_finish_placeholder_page_without_upload_ref_raises_session_empty` |

同时确认 PR-BE-003 衔接测试存在：

| 衔接点 | 覆盖测试 |
|--------|----------|
| 上传元数据回写页面项 | `test_attach_page_upload_updates_upload_ref` |
| 锁定后禁止回写上传元数据 | `test_attach_upload_rejects_locked_session` |

- [ ] **Step 5: 确认没有越界实现**

检查实现中不得出现以下行为：

- 调用 OCR、LLM、图像处理、裁剪、透视矫正
- 解析或推断结构化字段
- 处理真实图片文件类型/MIME/大小
- 写入完整任务生命周期、审核结果、导出结果

Run:

```bash
rg -n "ocr|llm|crop|perspective|quad_points|image_width|image_height|processing|ready_for_review" app/backend
```

Expected: 没有本计划新增的越界实现。

- [ ] **Step 6: Commit 收尾**

如果有测试修正或计划同步修改：

```bash
git status --short
git add <changed-files>
git commit -m "test: 验证采集会话 PR-BE-002 行为"
```

---

## 执行备注

- 所有测试命令使用 `conda run -n manzufei_ocr python -m pytest ...`。
- 本计划完成后，可以进入 PR-BE-003 图片上传与文件管理：把真实图片文件和 `quad_points` 等采集元数据接入本计划中的页面清单。
- 本计划新增共享错误码 `SESSION_EMPTY`，已同步 `docs/Shared/error-codes.md` 及相关 BDD/TDD；其余会话错误继续复用 `SESSION_NOT_FOUND`、`SESSION_EXPIRED`、`SESSION_LOCKED`。
