# BE-09 本地日志、隐私和离线检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立本地 JSONL 事件日志、隐私脱敏、离线检查和任务级清理边界，支持院内离线排查且不泄露病历隐私。

**Architecture:** 新增 `LocalEventLog` 以白名单 JSONL 事件写入 `logs/backend-events.jsonl` 并做大小轮转；新增 `sanitize_log_payload()` 统一脱敏并拒绝完整 OCR/病历/模型输出入日志。新增 `OfflineCheckService` 与 `CleanupService`，通过 `maintenance_bp` 暴露 `/api/maintenance/offline-check` 和任务级 cleanup preview/execute API。当前只接入 master 已有事件点（启动、会话创建、上传、finish、任务处理/失败）；BE-07/BE-08 合并后再通过独立小补丁接入审核/导出摘要。

**Tech Stack:** Flask, pytest, JsonStore, pathlib/os, local JSON Lines, no network dependencies

---

## Scope and Boundaries

- 权威依据：`docs/产品PRD.md` PR-BE-010/PR-BE-001、`docs/Backend/Backend_TDD/11-logging-privacy.md`、`docs/Backend/Backend_TDD/13-deployment.md`、`docs/Backend/Backend_BDD/logging-privacy.md`、`app/backend/README.md`。
- 日志只写本地 `logs/` 或配置的 `log_dir`；不得上传、遥测或请求外部日志服务。
- 日志字段采用白名单；不得记录完整病历原文、完整 OCR 文本、完整 LLM 输出、图片 base64、身份证号、手机号、Python 调用栈。
- 离线检查只检查本地路径、schema 文件和模型目录占位；不得联网下载、探测公网、安装依赖或加载真实模型。
- 清理只做任务级计划和显式确认执行，路径必须限制在配置根目录内；不得提供清空整个 data/exports/logs 的危险入口。
- 不修改 BE-07 `review_result.json` 契约，不修改 BE-01 `run.bat`/`stop.bat` PID/健康检查逻辑。

## Files

- Create: `app/backend/services/local_event_log.py`
- Create: `app/backend/services/offline_check_service.py`
- Create: `app/backend/services/cleanup_service.py`
- Create: `app/backend/routes/maintenance.py`
- Create: `app/backend/tests/test_local_event_log.py`
- Create: `app/backend/tests/test_offline_check_service.py`
- Create: `app/backend/tests/test_cleanup_service.py`
- Create: `app/backend/tests/test_maintenance_routes.py`
- Create: `app/backend/tests/test_logging_integration.py`
- Modify: `app/backend/config.py` add `log_max_bytes` and `log_backup_count`
- Modify: `app/backend/__init__.py` instantiate services, log startup, register `maintenance_bp`
- Modify: `app/backend/routes/capture_session.py`, `app/backend/routes/mobile.py`, `app/backend/services/task_service.py` add current business event summaries only

---

### Task 0: Baseline

**Files:**
- Run only: backend tests

- [ ] **Step 1: Run existing tests**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests -q
```

Expected: PASS. If baseline fails, stop and report failures before BE-09 edits.

---

### Task 1: LocalEventLog and Sanitizer

**Files:**
- Create: `app/backend/tests/test_local_event_log.py`
- Create: `app/backend/services/local_event_log.py`
- Modify: `app/backend/config.py`

- [ ] **Step 1: Write failing LocalEventLog tests**

Create `app/backend/tests/test_local_event_log.py`:

```python
import json
import os
import re

from app.backend.services.local_event_log import LocalEventLog, sanitize_log_payload


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestSanitizeLogPayload:
    def test_redacts_sensitive_keys_and_patterns(self):
        payload = {
            "task_id": "task-001",
            "ocr_text": "完整OCR文本不应进入日志",
            "merged_text": "完整病历原文不应进入日志",
            "model_output": {"field": "长模型输出"},
            "patient_id": "110101199001011234",
            "phone": "13812345678",
            "image_base64": "data:image/jpeg;base64," + "A" * 160,
            "reason": "x" * 200,
        }

        clean = sanitize_log_payload(payload)

        serialized = json.dumps(clean, ensure_ascii=False)
        assert clean["ocr_text"] == "[redacted]"
        assert clean["merged_text"] == "[redacted]"
        assert clean["model_output"] == "[redacted]"
        assert "110101199001011234" not in serialized
        assert "13812345678" not in serialized
        assert "data:image/jpeg;base64" not in serialized
        assert clean["reason"].endswith("...[truncated]")

    def test_limits_lists_dicts_and_complex_objects(self):
        clean = sanitize_log_payload(
            {
                "items": list(range(20)),
                "nested": {str(i): i for i in range(20)},
                "object": object(),
            }
        )

        assert len(clean["items"]) == 10
        assert clean["items"][-1] == "[truncated]"
        assert len(clean["nested"]) <= 11
        assert clean["object"] == "[object]"


class TestLocalEventLog:
    def test_writes_single_json_line_with_required_fields(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write("session_created", session_id="session-001")

        records = read_jsonl(log.current_path)
        assert len(records) == 1
        assert records[0]["event"] == "session_created"
        assert records[0]["level"] == "INFO"
        assert records[0]["session_id"] == "session-001"
        assert "ts" in records[0]

    def test_rejects_unknown_event_name(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        try:
            log.write("unknown_event", task_id="task-001")
        except ValueError as exc:
            assert "unknown_event" in str(exc)
        else:
            raise AssertionError("unknown_event should be rejected")

    def test_strips_disallowed_fields_and_sensitive_values(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write(
            "task_processing_failed",
            task_id="task-001",
            error_code="ALGORITHM_MODULE_FAILED",
            stage="field_extraction",
            reason="身份证110101199001011234 手机13812345678 " + "x" * 200,
            merged_text="完整病历原文",
        )

        content = open(log.current_path, encoding="utf-8").read()
        assert "110101199001011234" not in content
        assert "13812345678" not in content
        assert "完整病历原文" not in content
        record = read_jsonl(log.current_path)[0]
        assert record["reason"].endswith("...[truncated]")
        assert "merged_text" not in record

    def test_rotates_when_file_exceeds_max_bytes(self, tmp_path):
        log = LocalEventLog(str(tmp_path), max_bytes=300, backup_count=2)
        for i in range(50):
            log.write("session_created", session_id=f"session-{i}")

        backups = [name for name in os.listdir(tmp_path) if re.match(r"backend-events\.jsonl\.\d+", name)]
        assert backups
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_local_event_log.py -q
```

Expected: FAIL because `app.backend.services.local_event_log` does not exist.

- [ ] **Step 3: Add config defaults**

Modify `app/backend/config.py`:

```python
DEFAULT_CONFIG = {
    # existing keys...
    "log_max_bytes": 10 * 1024 * 1024,
    "log_backup_count": 5,
}
```

Add validation in `_validate_config`:

```python
    log_max_bytes = config.get("log_max_bytes")
    if not isinstance(log_max_bytes, int) or log_max_bytes <= 0:
        raise ValueError(f"log_max_bytes 必须为正整数，当前值: {log_max_bytes}")
    log_backup_count = config.get("log_backup_count")
    if not isinstance(log_backup_count, int) or log_backup_count < 0:
        raise ValueError(f"log_backup_count 必须为非负整数，当前值: {log_backup_count}")
```

- [ ] **Step 4: Implement LocalEventLog**

Create `app/backend/services/local_event_log.py`:

```python
import json
import os
import re
from datetime import datetime, timezone

SENSITIVE_KEYS = {
    "text",
    "plain_text",
    "ocr_text",
    "merged_text",
    "model_output",
    "llm_output",
    "base64",
    "image_base64",
}
ID_CARD_RE = re.compile(r"\b\d{6}\d{8}\d{3}[\dXx]\b")
PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
BASE64_RE = re.compile(r"(data:image/[^;]+;base64,)?[A-Za-z0-9+/]{100,}={0,2}")

ALLOWED_EVENTS = {
    "system_started",
    "config_default_used",
    "algorithm_module_not_configured",
    "session_created",
    "session_finished",
    "page_uploaded",
    "task_processing_started",
    "task_processing_failed",
    "task_ready_for_review",
    "review_field_saved",
    "review_confirmed",
    "export_succeeded",
    "export_failed",
}

EVENT_FIELDS = {
    "system_started": {"port", "lan_addresses_count"},
    "config_default_used": {"config_key"},
    "algorithm_module_not_configured": {"stage"},
    "session_created": {"session_id"},
    "session_finished": {"session_id", "task_id", "page_count"},
    "page_uploaded": {"session_id", "page_id", "image_width", "image_height"},
    "task_processing_started": {"task_id", "session_id"},
    "task_processing_failed": {"task_id", "session_id", "error_code", "stage", "reason"},
    "task_ready_for_review": {"task_id", "schema_version"},
    "review_field_saved": {"task_id", "field_key", "status"},
    "review_confirmed": {"task_id", "field_count"},
    "export_succeeded": {"task_id", "format", "relative_path"},
    "export_failed": {"task_id", "format", "error_code"},
}


def sanitize_log_payload(payload: dict) -> dict:
    return {key: _sanitize_value(key, value) for key, value in payload.items()}


def _sanitize_value(key: str, value):
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS or any(token in lowered for token in ("ocr_text", "merged_text", "model_output", "base64")):
        return "[redacted]"
    if isinstance(value, str):
        text = ID_CARD_RE.sub("[id_card]", value)
        text = PHONE_RE.sub("[phone]", text)
        text = BASE64_RE.sub("[base64]", text)
        if len(text) > 120:
            text = text[:80] + "...[truncated]"
        return text
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float) or value is None:
        return value
    if isinstance(value, list):
        items = [_sanitize_value(key, item) for item in value[:9]]
        if len(value) > 9:
            items.append("[truncated]")
        return items
    if isinstance(value, dict):
        result = {}
        for index, (child_key, child_value) in enumerate(value.items()):
            if index >= 10:
                result["[truncated]"] = True
                break
            result[child_key] = _sanitize_value(child_key, child_value)
        return result
    return f"[{type(value).__name__}]"


class LocalEventLog:
    def __init__(self, log_dir: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        self.log_dir = os.path.abspath(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        os.makedirs(self.log_dir, exist_ok=True)
        self.current_path = os.path.join(self.log_dir, "backend-events.jsonl")

    def write(self, event: str, level: str = "INFO", **payload) -> None:
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"unknown event: {event}")
        self._rotate_if_needed()
        allowed = EVENT_FIELDS[event]
        clean = sanitize_log_payload({k: v for k, v in payload.items() if k in allowed and v is not None})
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **clean,
        }
        with open(self.current_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def safe_write(self, event: str, level: str = "INFO", **payload) -> None:
        try:
            self.write(event, level=level, **payload)
        except Exception:
            return

    def _rotate_if_needed(self) -> None:
        if not os.path.exists(self.current_path) or os.path.getsize(self.current_path) < self.max_bytes:
            return
        for index in range(self.backup_count - 1, 0, -1):
            src = f"{self.current_path}.{index}"
            dst = f"{self.current_path}.{index + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        if self.backup_count > 0:
            os.replace(self.current_path, f"{self.current_path}.1")
        else:
            os.remove(self.current_path)
```

- [ ] **Step 5: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_local_event_log.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/config.py app/backend/services/local_event_log.py app/backend/tests/test_local_event_log.py
git commit -m "feat: 新增本地 JSONL 事件日志和脱敏"
```

---

### Task 2: Offline Check Service and Maintenance Route

**Files:**
- Create: `app/backend/tests/test_offline_check_service.py`
- Create: `app/backend/tests/test_maintenance_routes.py`
- Create: `app/backend/services/offline_check_service.py`
- Create: `app/backend/routes/maintenance.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: Write failing offline check service tests**

Create `app/backend/tests/test_offline_check_service.py`:

```python
import os

from app.backend.services.offline_check_service import OfflineCheckService


def make_config(tmp_path):
    schema = tmp_path / "app" / "config" / "schemas" / "medical_record.v1.yaml"
    schema.parent.mkdir(parents=True)
    schema.write_text("version: medical_record.v1\n", encoding="utf-8")
    return {
        "storage_dir": str(tmp_path / "data"),
        "export_dir": str(tmp_path / "exports"),
        "log_dir": str(tmp_path / "logs"),
        "model_dir": str(tmp_path / "models"),
        "schema_file": str(schema),
    }


def test_offline_check_creates_local_dirs_and_reports_model_warnings(tmp_path):
    config = make_config(tmp_path)
    service = OfflineCheckService(config)

    result = service.run()

    assert result["status"] == "warning"
    assert os.path.isdir(config["storage_dir"])
    assert os.path.isdir(config["export_dir"])
    assert os.path.isdir(config["log_dir"])
    checks = {item["key"]: item for item in result["checks"]}
    assert checks["storage_dir"]["status"] == "ok"
    assert checks["schema_file"]["status"] == "ok"
    assert checks["ppstructure_models"]["status"] == "warning"
    assert checks["llm_models"]["status"] == "warning"


def test_missing_schema_is_failed(tmp_path):
    config = make_config(tmp_path)
    os.remove(config["schema_file"])

    result = OfflineCheckService(config).run()

    checks = {item["key"]: item for item in result["checks"]}
    assert result["status"] == "failed"
    assert checks["schema_file"]["status"] == "failed"


def test_offline_check_has_no_network_imports():
    import app.backend.services.offline_check_service as module

    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("requests", "urllib", "httpx", "socket.create_connection"):
        assert forbidden not in source
```

- [ ] **Step 2: Write failing maintenance route tests**

Create `app/backend/tests/test_maintenance_routes.py`:

```python
import pytest

from app.backend import create_backend_app


@pytest.fixture
def client(tmp_path, monkeypatch):
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
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
  model_dir: "{tmp_path / 'models'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    schema_dir = tmp_path / "repo" / "app" / "config" / "schemas"
    schema_dir.mkdir(parents=True)
    (schema_dir / "medical_record.v1.yaml").write_text("version: medical_record.v1\n", encoding="utf-8")
    monkeypatch.setattr("app.backend.config.PROJECT_ROOT", str(tmp_path / "repo"))
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def test_offline_check_route_returns_checks(client):
    resp = client.get("/api/maintenance/offline-check")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["status"] in ("ok", "warning", "failed")
    keys = {item["key"] for item in data["checks"]}
    assert {"storage_dir", "exports_dir", "logs_dir", "schema_file", "ppstructure_models", "llm_models"} <= keys
```

- [ ] **Step 3: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_offline_check_service.py app/backend/tests/test_maintenance_routes.py -q
```

Expected: FAIL because service and route do not exist.

- [ ] **Step 4: Implement OfflineCheckService**

Create `app/backend/services/offline_check_service.py`:

```python
import os

from ..config import PROJECT_ROOT


class OfflineCheckService:
    def __init__(self, config: dict):
        self._config = config

    def run(self) -> dict:
        schema_file = self._config.get(
            "schema_file",
            os.path.join(PROJECT_ROOT, "app", "config", "schemas", "medical_record.v1.yaml"),
        )
        model_dir = self._config["model_dir"]
        checks = [
            self._ensure_dir("storage_dir", self._config["storage_dir"], critical=True),
            self._ensure_dir("exports_dir", self._config["export_dir"], critical=True),
            self._ensure_dir("logs_dir", self._config["log_dir"], critical=True),
            self._check_file("schema_file", schema_file, critical=True),
            self._check_dir_exists("embedded_python", os.path.join(PROJECT_ROOT, "runtime", "python"), critical=False),
            self._check_dir_exists("ppstructure_models", os.path.join(model_dir, "ppstructure"), critical=False),
            self._check_dir_exists("llm_models", os.path.join(model_dir, "llm"), critical=False),
        ]
        if any(item["status"] == "failed" for item in checks):
            status = "failed"
        elif any(item["status"] == "warning" for item in checks):
            status = "warning"
        else:
            status = "ok"
        return {"status": status, "checks": checks}

    def _ensure_dir(self, key: str, path: str, critical: bool) -> dict:
        try:
            os.makedirs(path, exist_ok=True)
            return {"key": key, "status": "ok", "path": self._display(path)}
        except OSError:
            return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _check_file(self, key: str, path: str, critical: bool) -> dict:
        if os.path.isfile(path):
            return {"key": key, "status": "ok", "path": self._display(path)}
        return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _check_dir_exists(self, key: str, path: str, critical: bool) -> dict:
        if os.path.isdir(path) and os.listdir(path):
            return {"key": key, "status": "ok", "path": self._display(path)}
        return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _display(self, path: str) -> str:
        try:
            return os.path.relpath(path, PROJECT_ROOT)
        except ValueError:
            return os.path.basename(path)
```

- [ ] **Step 5: Implement maintenance route and app wiring**

Create `app/backend/routes/maintenance.py`:

```python
from flask import Blueprint, current_app, request

from ..responses import success

maintenance_bp = Blueprint("maintenance", __name__)


@maintenance_bp.route("/api/maintenance/offline-check", methods=["GET"])
def offline_check():
    return success(data=current_app.config["OFFLINE_CHECK_SERVICE"].run())


@maintenance_bp.route("/api/maintenance/tasks/<task_id>/cleanup-plan", methods=["GET"])
def cleanup_plan(task_id):
    return success(data=current_app.config["CLEANUP_SERVICE"].plan_task_cleanup(task_id))


@maintenance_bp.route("/api/maintenance/tasks/<task_id>/cleanup", methods=["POST"])
def cleanup_task(task_id):
    payload = request.get_json(silent=True) or {}
    return success(data=current_app.config["CLEANUP_SERVICE"].cleanup_task(task_id, confirm=payload.get("confirm") is True))
```

Modify `app/backend/__init__.py`:

```python
    from .services.local_event_log import LocalEventLog
    from .services.offline_check_service import OfflineCheckService

    event_log = LocalEventLog(
        config["log_dir"],
        max_bytes=config["log_max_bytes"],
        backup_count=config["log_backup_count"],
    )
    app.config["LOCAL_EVENT_LOG"] = event_log
    app.config["OFFLINE_CHECK_SERVICE"] = OfflineCheckService(config)
```

Place the snippet after `store = JsonStore(config["storage_dir"])`, then log startup:

```python
    event_log.safe_write(
        "system_started",
        port=config["port"],
        lan_addresses_count=len(app.config["LAN_ADDRESSES"]),
    )
    event_log.safe_write("algorithm_module_not_configured", level="WARNING", stage="image_processing")
```

Register the route:

```python
    from .routes.maintenance import maintenance_bp
    app.register_blueprint(maintenance_bp)
```

- [ ] **Step 6: Run partial GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_offline_check_service.py app/backend/tests/test_maintenance_routes.py::test_offline_check_route_returns_checks -q
```

Expected: The offline-check tests PASS. Cleanup route tests will be added in Task 3.

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/offline_check_service.py app/backend/routes/maintenance.py app/backend/__init__.py app/backend/tests/test_offline_check_service.py app/backend/tests/test_maintenance_routes.py
git commit -m "feat: 新增离线检查维护 API"
```

---

### Task 3: CleanupService Safe Task Cleanup

**Files:**
- Create: `app/backend/tests/test_cleanup_service.py`
- Modify: `app/backend/tests/test_maintenance_routes.py`
- Create: `app/backend/services/cleanup_service.py`
- Modify: `app/backend/__init__.py`

- [ ] **Step 1: Write failing cleanup tests**

Create `app/backend/tests/test_cleanup_service.py`:

```python
import os

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.cleanup_service import CleanupService
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path):
    config = {
        "storage_dir": str(tmp_path / "data"),
        "export_dir": str(tmp_path / "exports"),
        "log_dir": str(tmp_path / "logs"),
    }
    store = JsonStore(config["storage_dir"])
    service = CleanupService(config=config, store=store)
    return service, store, config


def test_cleanup_plan_lists_task_scoped_paths_only(tmp_path):
    service, store, _ = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})

    plan = service.plan_task_cleanup("task-001")

    assert plan["task_id"] == "task-001"
    assert plan["requires_confirm"] is True
    assert "results/task-001" in plan["storage_paths"]
    assert "exports/task-001" in plan["export_paths"]
    assert plan["log_cleanup"] == "日志按轮转策略处理，不按任务物理删除"


def test_cleanup_requires_confirm_true(tmp_path):
    service, store, _ = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})

    with pytest.raises(AppError) as exc_info:
        service.cleanup_task("task-001", confirm=False)

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_cleanup_deletes_only_task_paths(tmp_path):
    service, store, config = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})
    store.write("results/task-001/review_result.json", {"ok": True})
    os.makedirs(os.path.join(config["export_dir"], "task-001"), exist_ok=True)
    with open(os.path.join(config["export_dir"], "task-001", "result.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    store.write("results/task-002/review_result.json", {"keep": True})

    result = service.cleanup_task("task-001", confirm=True)

    assert result["task_id"] == "task-001"
    assert store.read("results/task-001/review_result.json") is None
    assert store.read("results/task-002/review_result.json") == {"keep": True}


def test_rejects_unsafe_path_values(tmp_path):
    service, _, _ = make_service(tmp_path)

    for unsafe in ("", ".", "..", "../x", "/tmp/x"):
        with pytest.raises(AppError):
            service._safe_relative_path(unsafe)
```

Append to `app/backend/tests/test_maintenance_routes.py`:

```python
def test_cleanup_route_requires_confirm(client):
    resp = client.post("/api/maintenance/tasks/task-001/cleanup", json={"confirm": False})

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_cleanup_service.py app/backend/tests/test_maintenance_routes.py::test_cleanup_route_requires_confirm -q
```

Expected: FAIL because `CleanupService` does not exist.

- [ ] **Step 3: Implement CleanupService**

Create `app/backend/services/cleanup_service.py`:

```python
import os
import shutil

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class CleanupService:
    def __init__(self, config: dict, store: JsonStore):
        self._config = config
        self._store = store

    def plan_task_cleanup(self, task_id: str) -> dict:
        task = self._store.read(f"tasks/{task_id}.json")
        session_id = task.get("session_id") if isinstance(task, dict) else None
        return {
            "task_id": task_id,
            "session_id": session_id,
            "requires_confirm": True,
            "storage_paths": [f"results/{task_id}", f"tasks/{task_id}.json"],
            "export_paths": [f"exports/{task_id}"],
            "log_cleanup": "日志按轮转策略处理，不按任务物理删除",
        }

    def cleanup_task(self, task_id: str, confirm: bool) -> dict:
        if confirm is not True:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理任务必须显式传入 confirm=true")
        plan = self.plan_task_cleanup(task_id)
        deleted = []
        failed = []
        for rel in plan["storage_paths"]:
            try:
                self._delete_under_root(self._config["storage_dir"], rel)
                deleted.append(rel)
            except OSError:
                failed.append(rel)
        for rel in plan["export_paths"]:
            export_rel = rel.removeprefix("exports/")
            try:
                self._delete_under_root(self._config["export_dir"], export_rel)
                deleted.append(rel)
            except OSError:
                failed.append(rel)
        return {"task_id": task_id, "deleted": deleted, "failed": failed, "log_cleanup": plan["log_cleanup"]}

    def _delete_under_root(self, root: str, relative_path: str) -> None:
        safe = self._safe_relative_path(relative_path)
        root_abs = os.path.abspath(root)
        target = os.path.abspath(os.path.join(root_abs, safe))
        if not target.startswith(root_abs + os.sep) and target != root_abs:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径越权")
        if os.path.islink(target):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="拒绝删除符号链接")
        if os.path.isdir(target):
            shutil.rmtree(target)
        elif os.path.isfile(target):
            os.remove(target)

    def _safe_relative_path(self, value: str) -> str:
        if not value or value in (".", os.sep) or os.path.isabs(value):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径非法")
        normalized = os.path.normpath(value)
        if normalized == "." or normalized.startswith("..") or os.path.isabs(normalized):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径越权")
        return normalized
```

- [ ] **Step 4: Wire CleanupService into app factory**

Modify `app/backend/__init__.py` after `OFFLINE_CHECK_SERVICE` is configured:

```python
    from .services.cleanup_service import CleanupService

    app.config["CLEANUP_SERVICE"] = CleanupService(config=config, store=store)
```

- [ ] **Step 5: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_cleanup_service.py app/backend/tests/test_maintenance_routes.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/cleanup_service.py app/backend/__init__.py app/backend/tests/test_cleanup_service.py app/backend/tests/test_maintenance_routes.py
git commit -m "feat: 新增任务级安全清理服务"
```

---

### Task 4: Existing Business Event Integration

**Files:**
- Create: `app/backend/tests/test_logging_integration.py`
- Modify: `app/backend/routes/capture_session.py`
- Modify: `app/backend/routes/mobile.py`
- Modify: `app/backend/services/task_service.py`

- [ ] **Step 1: Write failing integration tests**

Create `app/backend/tests/test_logging_integration.py`:

```python
import io
import json

import pytest

from app.backend import create_backend_app


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
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
  model_dir: "{tmp_path / 'models'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    schema_dir = tmp_path / "repo" / "app" / "config" / "schemas"
    schema_dir.mkdir(parents=True)
    (schema_dir / "medical_record.v1.yaml").write_text("version: medical_record.v1\n", encoding="utf-8")
    monkeypatch.setattr("app.backend.config.PROJECT_ROOT", str(tmp_path / "repo"))
    monkeypatch.setattr("app.backend.PROJECT_ROOT", str(tmp_path / "repo"))
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def events(app):
    path = app.config["LOCAL_EVENT_LOG"].current_path
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def upload_jpeg(client, session_id):
    return client.post(
        f"/api/mobile/{session_id}/pages",
        data={
            "image_width": "100",
            "image_height": "100",
            "file": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "page.jpg"),
        },
        content_type="multipart/form-data",
    )


def test_startup_event_logged(app):
    names = [item["event"] for item in events(app)]
    assert "system_started" in names
    assert "algorithm_module_not_configured" in names


def test_session_upload_finish_events_logged(client, app):
    create_resp = client.post("/api/capture-sessions")
    session_id = create_resp.get_json()["data"]["session_id"]
    upload_resp = upload_jpeg(client, session_id)
    assert upload_resp.status_code == 201
    finish_resp = client.post(f"/api/mobile/{session_id}/finish")
    assert finish_resp.status_code == 200

    names = [item["event"] for item in events(app)]
    assert "session_created" in names
    assert "page_uploaded" in names
    assert "session_finished" in names


def test_task_processing_failure_event_has_context_and_no_sensitive_text(client, app):
    create_resp = client.post("/api/capture-sessions")
    session_id = create_resp.get_json()["data"]["session_id"]
    upload_jpeg(client, session_id)
    task_id = client.post(f"/api/mobile/{session_id}/finish").get_json()["data"]["task_id"]

    client.post(f"/api/tasks/{task_id}/process")

    failures = [item for item in events(app) if item["event"] == "task_processing_failed"]
    assert failures
    failure = failures[-1]
    assert failure["task_id"] == task_id
    assert failure["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    serialized = json.dumps(failure, ensure_ascii=False)
    assert "traceback" not in serialized.lower()
    assert "base64" not in serialized.lower()
    assert "110101199001011234" not in serialized
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_logging_integration.py -q
```

Expected: FAIL because business event calls are not wired.

- [ ] **Step 3: Add event helpers and calls**

In each modified file, use a local helper so log failures never break business flow:

```python
def _event_log():
    from flask import current_app

    return current_app.config.get("LOCAL_EVENT_LOG")


def _safe_event(event, level="INFO", **payload):
    log = _event_log()
    if log is not None:
        log.safe_write(event, level=level, **payload)
```

Modify `app/backend/routes/capture_session.py` after session creation:

```python
    _safe_event("session_created", session_id=session["session_id"])
```

Modify `app/backend/routes/mobile.py` after page upload succeeds:

```python
    _safe_event(
        "page_uploaded",
        session_id=session_id,
        page_id=result["page_id"],
        image_width=result.get("image_width"),
        image_height=result.get("image_height"),
    )
```

Modify `app/backend/routes/mobile.py` after finish succeeds:

```python
    _safe_event(
        "session_finished",
        session_id=session_id,
        task_id=result["task_id"],
        page_count=result.get("page_count"),
    )
```

Modify `app/backend/services/task_service.py` in `_start_processing`, `mark_failed`, and `mark_ready`. Because services do not always run in request context, guard current_app access:

```python
def _safe_event(event, level="INFO", **payload):
    try:
        from flask import current_app

        log = current_app.config.get("LOCAL_EVENT_LOG")
        if log is not None:
            log.safe_write(event, level=level, **payload)
    except RuntimeError:
        return
```

Call:

```python
_safe_event("task_processing_started", task_id=task_id, session_id=task.get("session_id"))
_safe_event("task_processing_failed", level="ERROR", task_id=task_id, session_id=task.get("session_id"), error_code=error_code, stage=stage, reason=error_message)
_safe_event("task_ready_for_review", task_id=task_id, schema_version=task.get("schema_version"))
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_logging_integration.py -q
```

Expected: PASS.

- [ ] **Step 5: Run BE-09 regression**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests/test_local_event_log.py app/backend/tests/test_offline_check_service.py app/backend/tests/test_cleanup_service.py app/backend/tests/test_maintenance_routes.py app/backend/tests/test_logging_integration.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routes/capture_session.py app/backend/routes/mobile.py app/backend/services/task_service.py app/backend/tests/test_logging_integration.py
git commit -m "feat: 接入本地业务事件日志"
```

---

### Task 5: Final Verification

**Files:**
- Run only: backend tests and boundary scans

- [ ] **Step 1: Run full backend tests**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 2: Verify no network/log upload implementation**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be09-local-logs-privacy-spec
rg -n "requests|httpx|urllib|telemetry|upload_log|sentry|cloud|cdn|download" app/backend/services/local_event_log.py app/backend/services/offline_check_service.py app/backend/routes/maintenance.py
```

Expected: no matches, except comments explicitly stating prohibited behavior if any.

- [ ] **Step 3: Confirm no placeholder text remains**

Read this plan once end-to-end and confirm every task contains concrete paths, commands, expected output, and implementation snippets. No file changes are needed for this confirmation step.
