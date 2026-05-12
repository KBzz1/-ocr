# 采集会话管理（A-lite）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现采集会话核心容器 — 创建/查询/过期判定/锁定/finish 幂等 + 最小 Task 桩

**Architecture:** 新增 SessionService（无 Flask 依赖的业务层），用已有 JsonStore 持久化到 `data/sessions/` 和 `data/tasks/`。新增 `capture_session_bp` 和 `mobile_bp` 两个 Blueprint，通过 `create_backend_app` 工厂注入。配置新增 `capture_session_ttl_minutes` 键。

**Tech Stack:** Python 3.10+, Flask, pytest, JsonStore

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/config/default.yaml` | MODIFY | 新增 `sessions.capture_session_ttl_minutes` |
| `app/backend/config.py` | MODIFY | 展平 `capture_session_ttl_minutes` |
| `app/backend/tests/test_config.py` | MODIFY | 新增 TTL 配置测试 |
| `app/backend/services/__init__.py` | CREATE | 空模块 |
| `app/backend/services/session_service.py` | CREATE | 会话业务逻辑 |
| `app/backend/tests/test_session_service.py` | CREATE | 单元测试（TDD） |
| `app/backend/routes/capture_session.py` | CREATE | POST/GET capture-sessions |
| `app/backend/routes/mobile.py` | CREATE | POST finish |
| `app/backend/__init__.py` | MODIFY | 注入 SessionService + 注册 Blueprint |
| `app/backend/tests/test_capture_session.py` | CREATE | API 集成测试 |

---

### Task 1: Config — 新增 capture_session_ttl_minutes

**Files:**
- Modify: `app/config/default.yaml`
- Modify: `app/backend/config.py`
- Modify: `app/backend/tests/test_config.py`

- [ ] **Step 1: 修改 default.yaml**

在 `app/config/default.yaml` 末尾追加：

```yaml

sessions:
  capture_session_ttl_minutes: 30
```

- [ ] **Step 2: 修改 config.py — DEFAULT_CONFIG 和 _flatten_config**

在 `app/backend/config.py` 中，`DEFAULT_CONFIG` dict 新增一项：

```python
DEFAULT_CONFIG = {
    ...
    "capture_session_ttl_minutes": 30,
}
```

在 `_flatten_config` 函数中，`flattened` 变量赋值之后、return 之前新增：

```python
    sessions_config = raw.get("sessions", {})
    if "capture_session_ttl_minutes" in sessions_config:
        flattened["capture_session_ttl_minutes"] = sessions_config["capture_session_ttl_minutes"]
```

- [ ] **Step 3: 添加配置测试**

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
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert config["capture_session_ttl_minutes"] == 15
```

- [ ] **Step 4: 运行测试验证 RED（config 测试新增的 TTL 测试失败）**

运行: `pytest app/backend/tests/test_config.py::TestSessionConfig -v`

预期: FAIL — 因为 _flatten_config 还未处理 sessions 段

- [ ] **Step 5: 运行测试验证 GREEN**

运行: `pytest app/backend/tests/test_config.py -v`

预期: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add app/config/default.yaml app/backend/config.py app/backend/tests/test_config.py
git commit -m "feat: 新增 capture_session_ttl_minutes 配置项"
```

---

### Task 2: SessionService.create() TDD

**Files:**
- Create: `app/backend/services/__init__.py`
- Create: `app/backend/services/session_service.py`
- Create: `app/backend/tests/test_session_service.py`

- [ ] **Step 1: 创建 services/__init__.py**

```bash
touch app/backend/services/__init__.py
```

- [ ] **Step 2: 编写 create 的失败单元测试**

创建 `app/backend/tests/test_session_service.py`：

```python
import os
import json
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from app.backend.storage.json_store import JsonStore
from app.backend.errors import AppError


class TestSessionServiceCreate:
    """create() 方法的单元测试 — BE-SES-001, BE-SES-002, BE-SES-003"""

    @staticmethod
    def _make_service(tmpdir, lan_addresses=None, ttl_minutes=30):
        from app.backend.services.session_service import SessionService
        store = JsonStore(tmpdir)
        return SessionService(
            store=store,
            lan_addresses=lan_addresses or ["192.168.1.5:8081"],
            ttl_minutes=ttl_minutes,
        )

    def test_create_returns_dict_with_session_id(self):
        service = self._make_service(tempfile.mkdtemp())
        session = service.create()
        assert "session_id" in session
        assert isinstance(session["session_id"], str)
        assert len(session["session_id"]) > 0

    def test_create_sets_active_status_and_timestamps(self):
        service = self._make_service(tempfile.mkdtemp())
        session = service.create()
        assert session["status"] == "active"
        assert "created_at" in session
        assert "expires_at" in session
        created = datetime.fromisoformat(session["created_at"])
        expires = datetime.fromisoformat(session["expires_at"])
        delta = expires - created
        assert timedelta(minutes=29) < delta < timedelta(minutes=31)

    def test_create_persists_to_json(self):
        tmpdir = tempfile.mkdtemp()
        service = self._make_service(tmpdir)
        session = service.create()
        filepath = os.path.join(tmpdir, "sessions", f"{session['session_id']}.json")
        assert os.path.isfile(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["session_id"] == session["session_id"]
        assert data["status"] == "active"

    def test_create_session_id_is_unique(self):
        service = self._make_service(tempfile.mkdtemp())
        s1 = service.create()
        s2 = service.create()
        assert s1["session_id"] != s2["session_id"]

    def test_qr_code_url_uses_first_lan_address(self):
        service = self._make_service(tempfile.mkdtemp(), lan_addresses=["10.0.0.1:8081"])
        session = service.create()
        expected = f"http://10.0.0.1:8081/mobile/{session['session_id']}"
        assert session["qr_code_url"] == expected

    def test_qr_code_url_null_when_no_lan(self):
        service = self._make_service(tempfile.mkdtemp(), lan_addresses=[])
        session = service.create()
        assert session["qr_code_url"] is None
```

- [ ] **Step 3: 运行测试确认 RED**

运行: `pytest app/backend/tests/test_session_service.py::TestSessionServiceCreate -v`

预期: FAIL — ImportError（SessionService 不存在）

- [ ] **Step 4: 实现 SessionService.create() 最小代码**

创建 `app/backend/services/session_service.py`：

```python
import uuid
from datetime import datetime, timezone, timedelta
from ..storage.json_store import JsonStore
from ..errors import AppError, ErrorCode


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
            "locked_at": None,
            "task_id": None,
        }

        self._store.write(f"sessions/{session_id}.json", session)
        return session
```

- [ ] **Step 5: 运行测试确认 GREEN**

运行: `pytest app/backend/tests/test_session_service.py::TestSessionServiceCreate -v`

预期: ALL PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/__init__.py app/backend/services/session_service.py app/backend/tests/test_session_service.py
git commit -m "feat: 实现 SessionService.create() 创建采集会话"
```

---

### Task 3: SessionService.get() TDD

**Files:**
- Modify: `app/backend/tests/test_session_service.py`
- Modify: `app/backend/services/session_service.py`

- [ ] **Step 1: 添加 get() 的失败测试**

在 `test_session_service.py` 末尾追加：

```python
class TestSessionServiceGet:
    """get() 方法的单元测试 — BE-SES-004, BE-SES-005"""

    @staticmethod
    def _make_service(tmpdir, lan_addresses=None, ttl_minutes=30):
        from app.backend.services.session_service import SessionService
        store = JsonStore(tmpdir)
        return SessionService(
            store=store,
            lan_addresses=lan_addresses or ["192.168.1.5:8081"],
            ttl_minutes=ttl_minutes,
        )

    def test_get_returns_session(self):
        service = self._make_service(tempfile.mkdtemp())
        created = service.create()
        fetched = service.get(created["session_id"])
        assert fetched["session_id"] == created["session_id"]
        assert fetched["status"] == "active"

    def test_get_nonexistent_raises_not_found(self):
        service = self._make_service(tempfile.mkdtemp())
        with pytest.raises(AppError) as exc_info:
            service.get("nonexistent-id")
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_get_auto_expires_when_past_expires_at(self):
        # 用负 TTL 创建已过期的会话
        service = self._make_service(tempfile.mkdtemp(), ttl_minutes=-1)
        created = service.create()
        fetched = service.get(created["session_id"])
        assert fetched["status"] == "expired"

    def test_get_auto_expire_persists_status_change(self):
        tmpdir = tempfile.mkdtemp()
        service = self._make_service(tmpdir, ttl_minutes=-1)
        created = service.create()
        service.get(created["session_id"])

        # 从文件读取验证持久化
        store = JsonStore(tmpdir)
        data = store.read(f"sessions/{created['session_id']}.json")
        assert data["status"] == "expired"
```

- [ ] **Step 2: 运行测试确认 RED**

运行: `pytest app/backend/tests/test_session_service.py::TestSessionServiceGet -v`

预期: FAIL — AttributeError: 'SessionService' object has no attribute 'get'

- [ ] **Step 3: 实现 SessionService.get()**

在 `session_service.py` 的 `SessionService` 类中，`create()` 方法后追加：

```python
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

运行: `pytest app/backend/tests/test_session_service.py -v`

预期: ALL PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_session_service.py app/backend/services/session_service.py
git commit -m "feat: 实现 SessionService.get() 查询与自动过期"
```

---

### Task 4: SessionService.finish() TDD

**Files:**
- Modify: `app/backend/tests/test_session_service.py`
- Modify: `app/backend/services/session_service.py`

- [ ] **Step 1: 添加 finish() 的失败测试**

在 `test_session_service.py` 末尾追加：

```python
class TestSessionServiceFinish:
    """finish() 方法的单元测试 — BE-SES-008 + 幂等 + 边界"""

    @staticmethod
    def _make_service(tmpdir, lan_addresses=None, ttl_minutes=30):
        from app.backend.services.session_service import SessionService
        store = JsonStore(tmpdir)
        return SessionService(
            store=store,
            lan_addresses=lan_addresses or ["192.168.1.5:8081"],
            ttl_minutes=ttl_minutes,
        )

    def test_finish_locks_active_session(self):
        service = self._make_service(tempfile.mkdtemp())
        created = service.create()
        finished = service.finish(created["session_id"])
        assert finished["status"] == "locked"

    def test_finish_sets_locked_at(self):
        service = self._make_service(tempfile.mkdtemp())
        created = service.create()
        finished = service.finish(created["session_id"])
        assert finished["locked_at"] is not None

    def test_finish_creates_task_stub(self):
        tmpdir = tempfile.mkdtemp()
        service = self._make_service(tmpdir)
        created = service.create()
        finished = service.finish(created["session_id"])
        task_id = finished["task_id"]
        assert task_id is not None

        # 验证 Task 桩文件存在且字段正确
        store = JsonStore(tmpdir)
        task = store.read(f"tasks/{task_id}.json")
        assert task["task_id"] == task_id
        assert task["session_id"] == created["session_id"]
        assert task["status"] == "uploaded"
        assert task["source"] == "capture_session"
        assert task["page_count"] == 0
        assert "created_at" in task

    def test_finish_persists_task_id_to_session(self):
        tmpdir = tempfile.mkdtemp()
        service = self._make_service(tmpdir)
        created = service.create()
        finished = service.finish(created["session_id"])

        store = JsonStore(tmpdir)
        session = store.read(f"sessions/{created['session_id']}.json")
        assert session["task_id"] == finished["task_id"]

    def test_finish_idempotent_on_locked(self):
        tmpdir = tempfile.mkdtemp()
        service = self._make_service(tmpdir)
        created = service.create()
        first = service.finish(created["session_id"])
        second = service.finish(created["session_id"])

        assert second["status"] == "locked"
        assert second["task_id"] == first["task_id"]

        # 验证只创建了一个 task 文件
        tasks_dir = os.path.join(tmpdir, "tasks")
        task_files = os.listdir(tasks_dir)
        assert len(task_files) == 1

    def test_finish_on_expired_raises_session_expired(self):
        service = self._make_service(tempfile.mkdtemp(), ttl_minutes=-1)
        created = service.create()
        with pytest.raises(AppError) as exc_info:
            service.finish(created["session_id"])
        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

    def test_finish_on_nonexistent_raises_not_found(self):
        service = self._make_service(tempfile.mkdtemp())
        with pytest.raises(AppError) as exc_info:
            service.finish("nonexistent-id")
        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code
```

- [ ] **Step 2: 运行测试确认 RED**

运行: `pytest app/backend/tests/test_session_service.py::TestSessionServiceFinish -v`

预期: FAIL — AttributeError: 'SessionService' object has no attribute 'finish'

- [ ] **Step 3: 实现 SessionService.finish()**

在 `session_service.py` 的 `SessionService` 类中，`get()` 方法后追加：

```python
    def finish(self, session_id: str) -> dict:
        session = self.get(session_id)

        if session["status"] == "locked":
            return session

        if session["status"] in ("expired", "cancelled"):
            raise AppError(ErrorCode.SESSION_EXPIRED)

        now = datetime.now(timezone.utc)
        session["status"] = "locked"
        session["locked_at"] = now.isoformat()

        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "session_id": session_id,
            "status": "uploaded",
            "created_at": now.isoformat(),
            "page_count": session["page_count"],
            "source": "capture_session",
        }
        self._store.write(f"tasks/{task_id}.json", task)

        session["task_id"] = task_id
        self._store.write(f"sessions/{session_id}.json", session)

        return session
```

- [ ] **Step 4: 运行测试确认 GREEN**

运行: `pytest app/backend/tests/test_session_service.py -v`

预期: ALL PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_session_service.py app/backend/services/session_service.py
git commit -m "feat: 实现 SessionService.finish() 锁定、Task 桩与幂等"
```

---

### Task 5: Routes + __init__.py 布线

**Files:**
- Create: `app/backend/routes/capture_session.py`
- Create: `app/backend/routes/mobile.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: 创建 capture_session_bp**

创建 `app/backend/routes/capture_session.py`：

```python
from flask import Blueprint, current_app
from ..responses import success

capture_session_bp = Blueprint("capture_session", __name__)


def _get_service():
    return current_app.config["SESSION_SERVICE"]


@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    service = _get_service()
    session = service.create()
    return success(data={
        "session_id": session["session_id"],
        "status": session["status"],
        "created_at": session["created_at"],
        "expires_at": session["expires_at"],
        "qr_code_url": session["qr_code_url"],
        "page_count": session["page_count"],
    }, status=201)


@capture_session_bp.route("/api/capture-sessions/<session_id>")
def get_session(session_id):
    service = _get_service()
    session = service.get(session_id)
    return success(data=session)
```

- [ ] **Step 2: 创建 mobile_bp**

创建 `app/backend/routes/mobile.py`：

```python
from flask import Blueprint, current_app
from ..responses import success

mobile_bp = Blueprint("mobile", __name__)


def _get_service():
    return current_app.config["SESSION_SERVICE"]


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    service = _get_service()
    session = service.finish(session_id)
    return success(data={
        "session_id": session["session_id"],
        "status": session["status"],
        "locked_at": session["locked_at"],
        "task_id": session["task_id"],
    })
```

- [ ] **Step 3: 修改 create_backend_app 工厂**

修改 `app/backend/__init__.py`，在 `register_error_handlers(app)` 之后、现有 `from .routes.system import system_bp` 之前插入 SessionService 初始化：

```python
    register_error_handlers(app)

    # 初始化 SessionService
    from .storage.json_store import JsonStore
    from .services.session_service import SessionService

    store = JsonStore(config["storage_dir"])
    session_service = SessionService(
        store=store,
        lan_addresses=app.config["LAN_ADDRESSES"],
        ttl_minutes=config["capture_session_ttl_minutes"],
    )
    app.config["SESSION_SERVICE"] = session_service

    from .routes.system import system_bp
    app.register_blueprint(system_bp)
```

然后在 `app.register_blueprint(system_bp)` 之后追加新 Blueprint 注册：

```python
    from .routes.capture_session import capture_session_bp
    from .routes.mobile import mobile_bp
    app.register_blueprint(capture_session_bp)
    app.register_blueprint(mobile_bp)
```

- [ ] **Step 4: 冒烟测试 — 启动 app 确认无 ImportError**

运行:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/backend-minimal-skeleton && python -c "from app.backend import create_backend_app; app = create_backend_app(); print('OK')"
```

预期: OK

- [ ] **Step 5: Commit**

```bash
git add app/backend/routes/capture_session.py app/backend/routes/mobile.py app/backend/__init__.py
git commit -m "feat: 注册 capture_session_bp 和 mobile_bp 路由"
```

---

### Task 6: API 集成测试

**Files:**
- Create: `app/backend/tests/test_capture_session.py`

- [ ] **Step 1: 编写 API 集成测试**

创建 `app/backend/tests/test_capture_session.py`：

```python
import os
import uuid
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from app.backend import create_backend_app
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app():
    tmpdir = tempfile.mkdtemp()
    config_dir = os.path.join(tmpdir, "config")
    os.makedirs(config_dir)

    default_yaml_path = os.path.join(config_dir, "default.yaml")
    with open(default_yaml_path, "w", encoding="utf-8") as f:
        f.write(f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmpdir}"
  log_dir: "{tmpdir}/logs"
sessions:
  capture_session_ttl_minutes: 30
""")

    app = create_backend_app(config_dir=config_dir)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestCreateSessionAPI:
    def test_create_session_returns_201(self, client):
        resp = client.post("/api/capture-sessions")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["success"] is True
        assert "session_id" in data["data"]
        assert data["data"]["status"] == "active"
        assert data["data"]["page_count"] == 0

    def test_create_session_response_has_qr_url(self, client):
        resp = client.post("/api/capture-sessions")
        data = resp.get_json()
        assert "qr_code_url" in data["data"]

    def test_create_session_has_timestamps(self, client):
        resp = client.post("/api/capture-sessions")
        data = resp.get_json()
        assert "created_at" in data["data"]
        assert "expires_at" in data["data"]


class TestGetSessionAPI:
    def test_get_session_returns_200(self, client):
        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]
        resp = client.get(f"/api/capture-sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["session_id"] == session_id
        assert data["data"]["status"] == "active"

    def test_get_nonexistent_session_returns_404(self, client):
        resp = client.get("/api/capture-sessions/nonexistent-id")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"]["code"] == "SESSION_NOT_FOUND"


class TestFinishSessionAPI:
    def test_finish_locks_session_returns_200(self, client):
        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]
        resp = client.post(f"/api/mobile/{session_id}/finish")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "locked"
        assert data["data"]["task_id"] is not None

    def test_finish_idempotent_returns_same_task_id(self, client):
        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]
        first = client.post(f"/api/mobile/{session_id}/finish")
        second = client.post(f"/api/mobile/{session_id}/finish")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.get_json()["data"]["task_id"] == second.get_json()["data"]["task_id"]

    def test_finish_nonexistent_session_returns_404(self, client):
        resp = client.post("/api/mobile/nonexistent-id/finish")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["error"]["code"] == "SESSION_NOT_FOUND"

    def test_finish_expired_session_returns_409(self, client):
        # 直接写入一个已过期的会话 JSON
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])

        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = {
            "session_id": session_id,
            "status": "expired",
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "expires_at": (now - timedelta(minutes=30)).isoformat(),
            "qr_code_url": None,
            "page_count": 0,
            "locked_at": None,
            "task_id": None,
        }
        store.write(f"sessions/{session_id}.json", session)

        resp = client.post(f"/api/mobile/{session_id}/finish")
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["error"]["code"] == "SESSION_EXPIRED"
```

- [ ] **Step 2: 运行集成测试确认 RED/GREEN**

运行: `pytest app/backend/tests/test_capture_session.py -v`

预期: ALL PASS (10 tests)

- [ ] **Step 3: Commit**

```bash
git add app/backend/tests/test_capture_session.py
git commit -m "test: 采集会话 + finish API 集成测试"
```

---

### Task 7: 全量回归 + 验证

- [ ] **Step 1: 运行全量测试套件**

运行: `pytest app/backend/tests/ -v`

预期: 所有已有测试 + 27 个新增测试全部 PASS

- [ ] **Step 2: 运行 quick API smoke test**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/backend-minimal-skeleton && python -c "
from app.backend import create_backend_app
import json

app = create_backend_app()
client = app.test_client()

# 1. 创建会话
resp = client.post('/api/capture-sessions')
assert resp.status_code == 201, f'create failed: {resp.status_code}'
data = resp.get_json()
sid = data['data']['session_id']
print(f'创建会话: {sid}')

# 2. 查询会话
resp = client.get(f'/api/capture-sessions/{sid}')
assert resp.status_code == 200
assert resp.get_json()['data']['status'] == 'active'
print('查询成功: active')

# 3. 锁定会话
resp = client.post(f'/api/mobile/{sid}/finish')
assert resp.status_code == 200
assert resp.get_json()['data']['status'] == 'locked'
task_id = resp.get_json()['data']['task_id']
print(f'锁定成功: task_id={task_id}')

# 4. 幂等 finish
resp = client.post(f'/api/mobile/{sid}/finish')
assert resp.status_code == 200
assert resp.get_json()['data']['task_id'] == task_id
print('幂等 finish: OK')

# 5. 不存在会话
resp = client.get('/api/capture-sessions/fake')
assert resp.status_code == 404
print('SESSION_NOT_FOUND: OK')

print('全量 smoke test 通过!')
"
```

预期: 全量 smoke test 通过!

- [ ] **Step 3: Final commit（如有任何修改）**

```bash
git status
```
