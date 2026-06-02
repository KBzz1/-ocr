# 后端最小骨架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 Flask 后端最小骨架——配置加载、状态枚举、统一错误响应、健康检查端点。

**Architecture:** Flask app factory (`create_backend_app`) + YAML 配置三层合并（默认值 < default.yaml < local.yaml）+ 全局 errorhandler 统一 JSON 响应。所有模块先写测试，运行 RED 后再实现。

**Tech Stack:** Flask 3.x, PyYAML, pytest, Python 3.10+

---

### Task 1: 目录结构 + 依赖清单 + .gitignore

**Files:**
- Create: `app/backend/__init__.py`
- Create: `app/backend/tests/__init__.py`
- Create: `app/backend/routes/__init__.py`
- Create: `app/backend/storage/__init__.py`
- Create: `requirements.txt`
- Modify: `.gitignore`（追加 `app/config/local.yaml`）

- [ ] **Step 1: 创建所有空 `__init__.py`**

```bash
mkdir -p app/backend/tests app/backend/routes app/backend/storage
touch app/backend/__init__.py
touch app/backend/tests/__init__.py
touch app/backend/routes/__init__.py
touch app/backend/storage/__init__.py
```

- [ ] **Step 2: 创建受控依赖清单**

```txt
# requirements.txt
Flask>=3.0,<4.0
PyYAML>=6.0,<7.0
pytest>=8.0,<9.0
```

- [ ] **Step 3: 安装依赖**

```bash
python -m pip install -r requirements.txt
```

离线部署时应将 `requirements.txt` 对应 wheel 包预置到 `runtime/python/` 可访问的位置，不在运行时联网下载。

- [ ] **Step 4: 更新 `.gitignore`，追加 `app/config/local.yaml`**

在 `.gitignore` 末尾添加一行：

```
# 本地配置覆盖
app/config/local.yaml
```

- [ ] **Step 5: 验证目录结构**

```bash
find app/backend -type f | sort
```

Expected:
```
app/backend/__init__.py
app/backend/routes/__init__.py
app/backend/storage/__init__.py
app/backend/tests/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add app/backend/ app/config/ .gitignore requirements.txt
git commit -m "chore: 创建后端目录骨架与依赖清单"
```

---

### Task 2: enums.py — 状态枚举

**Files:**
- Create: `app/backend/tests/test_enums.py`
- Create: `app/backend/enums.py`

- [ ] **Step 1: 写失败测试 — TaskStatus 成员值正确**

```python
# app/backend/tests/test_enums.py
import pytest
from app.backend.enums import TaskStatus, SessionStatus, FieldStatus


class TestTaskStatus:
    def test_member_values(self):
        assert TaskStatus.CREATED.value == "created"
        assert TaskStatus.UPLOADING.value == "uploading"
        assert TaskStatus.UPLOADED.value == "uploaded"
        assert TaskStatus.PROCESSING.value == "processing"
        assert TaskStatus.READY_FOR_REVIEW.value == "ready_for_review"
        assert TaskStatus.CONFIRMED.value == "confirmed"
        assert TaskStatus.EXPORTED.value == "exported"
        assert TaskStatus.FAILED.value == "failed"

    def test_allowed_transitions_from_created(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.CREATED)
        assert TaskStatus.UPLOADING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 2

    def test_allowed_transitions_from_ready_for_review(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.READY_FOR_REVIEW)
        assert TaskStatus.CONFIRMED in targets
        assert TaskStatus.PROCESSING in targets
        assert TaskStatus.FAILED in targets
        assert len(targets) == 3

    def test_allowed_transitions_from_exported_is_empty(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.EXPORTED)
        assert targets == []

    def test_allowed_transitions_from_failed(self):
        targets = TaskStatus.allowed_transitions(TaskStatus.FAILED)
        assert TaskStatus.PROCESSING in targets
        assert len(targets) == 1

    def test_valid_transition_returns_true(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CREATED, TaskStatus.UPLOADING) is True
        assert TaskStatus.is_valid_transition(TaskStatus.PROCESSING, TaskStatus.FAILED) is True
        assert TaskStatus.is_valid_transition(TaskStatus.FAILED, TaskStatus.PROCESSING) is True

    def test_invalid_transition_returns_false(self):
        assert TaskStatus.is_valid_transition(TaskStatus.CREATED, TaskStatus.EXPORTED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.EXPORTED, TaskStatus.CREATED) is False
        assert TaskStatus.is_valid_transition(TaskStatus.CONFIRMED, TaskStatus.CREATED) is False

    def test_allowed_transitions_with_string_arg(self):
        """应接受字符串形式的状态值。"""
        targets = TaskStatus.allowed_transitions("created")
        assert TaskStatus.UPLOADING in targets


class TestSessionStatus:
    def test_member_values(self):
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.EXPIRED.value == "expired"
        assert SessionStatus.LOCKED.value == "locked"
        assert SessionStatus.CANCELLED.value == "cancelled"

    def test_allowed_transitions_from_active(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.ACTIVE)
        assert SessionStatus.LOCKED in targets
        assert SessionStatus.CANCELLED in targets
        assert SessionStatus.EXPIRED in targets
        assert len(targets) == 3

    def test_allowed_transitions_from_locked_is_empty(self):
        targets = SessionStatus.allowed_transitions(SessionStatus.LOCKED)
        assert targets == []

    def test_valid_transition(self):
        assert SessionStatus.is_valid_transition(SessionStatus.ACTIVE, SessionStatus.LOCKED) is True
        assert SessionStatus.is_valid_transition(SessionStatus.LOCKED, SessionStatus.ACTIVE) is False


class TestFieldStatus:
    def test_member_values(self):
        assert FieldStatus.UNREVIEWED.value == "unreviewed"
        assert FieldStatus.CONFIRMED.value == "confirmed"
        assert FieldStatus.MODIFIED.value == "modified"
        assert FieldStatus.SUSPICIOUS.value == "suspicious"
        assert FieldStatus.EMPTY.value == "empty"
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_enums.py -v
```

Expected: 全部 FAIL（ModuleNotFoundError: No module named 'app.backend.enums'）

- [ ] **Step 3: 实现 `enums.py`**

```python
# app/backend/enums.py
from enum import Enum


TASK_STATUS_TRANSITIONS = {
    "created": ["uploading", "failed"],
    "uploading": ["uploaded", "failed"],
    "uploaded": ["processing", "failed"],
    "processing": ["ready_for_review", "failed"],
    "ready_for_review": ["confirmed", "processing", "failed"],
    "confirmed": ["exported"],
    "exported": [],
    "failed": ["processing"],
}

SESSION_STATUS_TRANSITIONS = {
    "active": ["locked", "cancelled", "expired"],
    "expired": [],
    "locked": [],
    "cancelled": [],
}


class TaskStatus(Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    EXPORTED = "exported"
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
        current = cls._resolve(current)
        target = cls._resolve(target)
        return target in cls.allowed_transitions(current)


class SessionStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LOCKED = "locked"
    CANCELLED = "cancelled"

    @classmethod
    def _resolve(cls, value):
        if isinstance(value, cls):
            return value
        return cls(value)

    @classmethod
    def allowed_transitions(cls, current):
        current = cls._resolve(current)
        return [cls(v) for v in SESSION_STATUS_TRANSITIONS.get(current.value, [])]

    @classmethod
    def is_valid_transition(cls, current, target):
        current = cls._resolve(current)
        target = cls._resolve(target)
        return target in cls.allowed_transitions(current)


class FieldStatus(Enum):
    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    SUSPICIOUS = "suspicious"
    EMPTY = "empty"
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_enums.py -v
```

Expected: 全部 PASS（11 passed）

- [ ] **Step 5: Commit**

```bash
git add app/backend/enums.py app/backend/tests/test_enums.py
git commit -m "feat: 实现 TaskStatus / SessionStatus / FieldStatus 状态枚举与合法流转校验"
```

---

### Task 3: errors.py — ErrorCode / AppError / 全局 errorhandler

**Files:**
- Create: `app/backend/tests/test_errors.py`
- Create: `app/backend/errors.py`
- Create: `app/backend/responses.py` 待 Task 4 创建（test_errors.py 只测试 ErrorCode、AppError 异常对象属性，不依赖 responses.py）

- [ ] **Step 1: 写失败测试**

```python
# app/backend/tests/test_errors.py
import pytest
from app.backend.errors import (
    ErrorCode,
    AlgorithmErrorCode,
    AppError,
)


class TestErrorCode:
    def test_code_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.code == "SESSION_NOT_FOUND"
        assert ErrorCode.TASK_NOT_FOUND.code == "TASK_NOT_FOUND"
        assert ErrorCode.SESSION_EXPIRED.code == "SESSION_EXPIRED"

    def test_http_status_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.http_status == 404
        assert ErrorCode.SESSION_EXPIRED.http_status == 409
        assert ErrorCode.EXPORT_FAILED.http_status == 500

    def test_default_message_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.default_message == "采集会话不存在"
        assert ErrorCode.TASK_NOT_FOUND.default_message == "任务不存在"
        assert ErrorCode.INVALID_TASK_TRANSITION.default_message == "非法任务状态流转"

    def test_all_codes_defined(self):
        """确保 spec 中所有 11 个 ErrorCode 均已定义。"""
        codes = {e.code for e in ErrorCode}
        assert "SESSION_NOT_FOUND" in codes
        assert "SESSION_EXPIRED" in codes
        assert "SESSION_LOCKED" in codes
        assert "UNSUPPORTED_FILE_TYPE" in codes
        assert "FILE_TOO_LARGE" in codes
        assert "INVALID_QUAD_POINTS" in codes
        assert "TASK_NOT_FOUND" in codes
        assert "INVALID_TASK_TRANSITION" in codes
        assert "REVIEW_VALIDATION_FAILED" in codes
        assert "EXPORT_VALIDATION_FAILED" in codes
        assert "EXPORT_FAILED" in codes
        assert len(codes) == 11


class TestAlgorithmErrorCode:
    def test_member_values(self):
        assert AlgorithmErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.value == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert AlgorithmErrorCode.ALGORITHM_MODULE_FAILED.value == "ALGORITHM_MODULE_FAILED"
        assert AlgorithmErrorCode.ALGORITHM_CONTRACT_INVALID.value == "ALGORITHM_CONTRACT_INVALID"


class TestAppError:
    def test_with_default_message(self):
        err = AppError(ErrorCode.TASK_NOT_FOUND)
        assert err.code == "TASK_NOT_FOUND"
        assert err.message == "任务不存在"
        assert err.http_status == 404
        assert err.details == {}

    def test_with_custom_message(self):
        err = AppError(ErrorCode.TASK_NOT_FOUND, message="任务 task_001 不存在")
        assert err.message == "任务 task_001 不存在"
        assert err.code == "TASK_NOT_FOUND"

    def test_with_details(self):
        err = AppError(
            ErrorCode.INVALID_TASK_TRANSITION,
            details={"current": "created", "target": "exported"},
        )
        assert err.details == {"current": "created", "target": "exported"}

    def test_is_exception(self):
        err = AppError(ErrorCode.SESSION_NOT_FOUND)
        assert isinstance(err, Exception)


class TestAbort:
    def test_abort_raises_app_error(self):
        from app.backend.errors import abort

        with pytest.raises(AppError) as exc_info:
            abort(ErrorCode.SESSION_EXPIRED, message="会话已过期")
        assert exc_info.value.code == "SESSION_EXPIRED"
        assert exc_info.value.message == "会话已过期"
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_errors.py -v
```

Expected: 全部 FAIL

- [ ] **Step 3: 实现 `errors.py`**

```python
# app/backend/errors.py
from enum import Enum


class ErrorCode(Enum):
    SESSION_NOT_FOUND = ("SESSION_NOT_FOUND", 404, "采集会话不存在")
    SESSION_EXPIRED = ("SESSION_EXPIRED", 409, "采集会话已过期")
    SESSION_LOCKED = ("SESSION_LOCKED", 409, "采集会话已完成采集，禁止编辑")
    UNSUPPORTED_FILE_TYPE = ("UNSUPPORTED_FILE_TYPE", 400, "不支持的文件类型")
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", 400, "文件超过大小限制")
    INVALID_QUAD_POINTS = ("INVALID_QUAD_POINTS", 400, "框选坐标格式非法")
    TASK_NOT_FOUND = ("TASK_NOT_FOUND", 404, "任务不存在")
    INVALID_TASK_TRANSITION = ("INVALID_TASK_TRANSITION", 400, "非法任务状态流转")
    REVIEW_VALIDATION_FAILED = ("REVIEW_VALIDATION_FAILED", 400, "审核确认校验失败")
    EXPORT_VALIDATION_FAILED = ("EXPORT_VALIDATION_FAILED", 400, "导出前完整性校验失败")
    EXPORT_FAILED = ("EXPORT_FAILED", 500, "导出文件写入失败")

    @property
    def code(self):
        return self.value[0]

    @property
    def http_status(self):
        return self.value[1]

    @property
    def default_message(self):
        return self.value[2]


class AlgorithmErrorCode(Enum):
    ALGORITHM_MODULE_NOT_CONFIGURED = "ALGORITHM_MODULE_NOT_CONFIGURED"
    ALGORITHM_MODULE_FAILED = "ALGORITHM_MODULE_FAILED"
    ALGORITHM_CONTRACT_INVALID = "ALGORITHM_CONTRACT_INVALID"


class AppError(Exception):
    def __init__(self, error_code: ErrorCode, message=None, details=None):
        self.code = error_code.code
        self.message = message or error_code.default_message
        self.http_status = error_code.http_status
        self.details = details or {}

    def __str__(self):
        return f"[{self.code}] {self.message}"


def abort(error_code: ErrorCode, message=None, details=None):
    raise AppError(error_code, message=message, details=details)


def register_error_handlers(app):
    from flask import jsonify
    from werkzeug.exceptions import HTTPException as WerkzeugHTTPException

    from .responses import error_response

    @app.errorhandler(AppError)
    def handle_app_error(error):
        return error_response(error)

    @app.errorhandler(WerkzeugHTTPException)
    def handle_http_exception(error):
        return jsonify({
            "error": {
                "code": "HTTP_ERROR",
                "message": error.description or str(error),
                "details": {},
            }
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error")
        return jsonify({
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "details": {},
            }
        }), 500
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_errors.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/errors.py app/backend/tests/test_errors.py
git commit -m "feat: 实现 ErrorCode / AlgorithmErrorCode / AppError 异常与 abort 快捷函数"
```

---

### Task 4: responses.py — 统一 JSON 响应 helper

**Files:**
- Create: `app/backend/tests/test_responses.py`
- Create: `app/backend/responses.py`

- [ ] **Step 1: 写失败测试**

```python
# app/backend/tests/test_responses.py
import json
import pytest
from app.backend.responses import success, error_response
from app.backend.errors import AppError, ErrorCode


class TestSuccess:
    def test_success_with_none_data(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success()
            data = json.loads(resp.get_data(as_text=True))
            assert data == {"success": True, "data": None}
            assert resp.status_code == 200

    def test_success_with_data(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success(data={"status": "running"})
            data = json.loads(resp.get_data(as_text=True))
            assert data == {"success": True, "data": {"status": "running"}}

    def test_success_custom_status(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success(status=201)
            assert resp.status_code == 201

    def test_success_content_type(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success()
            assert resp.content_type == "application/json"


class TestErrorResponse:
    def test_error_response_structure(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.TASK_NOT_FOUND)
            resp = error_response(err)
            data = json.loads(resp.get_data(as_text=True))
            assert data == {
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "任务不存在",
                    "details": {},
                }
            }

    def test_error_response_http_status(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.SESSION_EXPIRED)
            resp = error_response(err)
            assert resp.status_code == 409

    def test_error_response_with_details(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": "created", "target": "exported"},
            )
            resp = error_response(err)
            data = json.loads(resp.get_data(as_text=True))
            assert data["error"]["details"] == {"current": "created", "target": "exported"}

    def test_error_response_content_type(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.TASK_NOT_FOUND)
            resp = error_response(err)
            assert resp.content_type == "application/json"
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_responses.py -v
```

Expected: 全部 FAIL

- [ ] **Step 3: 实现 `responses.py`**

```python
# app/backend/responses.py
from flask import jsonify


def success(data=None, status=200):
    resp = jsonify({"success": True, "data": data})
    resp.status_code = status
    return resp


def error_response(app_error):
    resp = jsonify({
        "error": {
            "code": app_error.code,
            "message": app_error.message,
            "details": app_error.details,
        }
    })
    resp.status_code = app_error.http_status
    return resp
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_responses.py -v
```

Expected: 全部 PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add app/backend/responses.py app/backend/tests/test_responses.py
git commit -m "feat: 实现 success / error_response 统一 JSON 响应 helper"
```

---

### Task 5: settings.py + default.yaml — 配置加载

**Files:**
- Create: `app/backend/tests/test_settings.py`
- Create: `app/backend/settings.py`
- Create: `app/config/default.yaml`
- Modify: `app/config/README.md`

- [ ] **Step 1: 写失败测试**

```python
# app/backend/tests/test_settings.py
import os
import pytest
import tempfile
from app.backend.settings import load_config, DEFAULT_CONFIG


class TestDefaultConfig:
    def test_load_without_config_dir(self):
        """不传 config_dir 时返回默认值。"""
        config = load_config()
        assert config["port"] == 8080
        assert config["bind_host"] == "0.0.0.0"
        assert config["local_host"] == "127.0.0.1"
        assert config["version"] == "0.1.0"
        assert "data_dir" in config
        assert "log_dir" in config
        assert "model_dir" in config
        assert "storage_dir" in config
        assert "export_dir" in config

    def test_default_paths_are_absolute(self):
        config = load_config()
        assert os.path.isabs(config["data_dir"])
        assert os.path.isabs(config["log_dir"])
        assert os.path.isabs(config["export_dir"])


class TestYamlLoading:
    def test_default_yaml_overrides_defaults(self, tmp_path):
        import yaml

        default_yaml = {
            "app": {"version": "2.0.0"},
            "server": {"port": 9999},
        }
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert config["version"] == "2.0.0"
        assert config["port"] == 9999

    def test_local_yaml_overrides_default_yaml(self, tmp_path):
        import yaml

        default_yaml = {
            "app": {"version": "2.0.0"},
            "server": {"port": 9999},
        }
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        local_yaml = {"server": {"port": 5555}}
        with open(tmp_path / "local.yaml", "w") as f:
            yaml.dump(local_yaml, f)

        config = load_config(str(tmp_path))
        assert config["version"] == "2.0.0"  # from default.yaml
        assert config["port"] == 5555         # from local.yaml

    def test_missing_directory_uses_defaults(self):
        config = load_config("/nonexistent/path")
        assert config["port"] == 8080

    def test_paths_normalized_to_absolute(self, tmp_path):
        """data_dir 相对路径应转为基于项目根的绝对路径。"""
        import yaml

        default_yaml = {"paths": {"data_dir": "./my_data"}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert os.path.isabs(config["data_dir"])


class TestValidation:
    def test_invalid_port_raises(self, tmp_path):
        import yaml

        default_yaml = {"server": {"port": 70000}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="端口号"):
            load_config(str(tmp_path))

    def test_path_not_writable_raises(self, tmp_path):
        import yaml

        blocking_file = tmp_path / "not_a_dir"
        blocking_file.write_text("block", encoding="utf-8")
        default_yaml = {"paths": {"data_dir": str(blocking_file / "child")}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="路径不可写"):
            load_config(str(tmp_path))


class TestDeepMerge:
    def test_nested_dicts_are_merged_not_replaced(self, tmp_path):
        import yaml

        default_yaml = {"paths": {"data_dir": "./data", "log_dir": "./logs"}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        local_yaml = {"paths": {"data_dir": "./my_data"}}
        with open(tmp_path / "local.yaml", "w") as f:
            yaml.dump(local_yaml, f)

        config = load_config(str(tmp_path))
        # local 覆盖了 data_dir，但 log_dir 保留 default 的值
        assert "log_dir" in config
        assert "log" in config["log_dir"] or config["log_dir"] == ""
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_settings.py -v
```

Expected: 全部 FAIL（ModuleNotFoundError: No module named 'app.backend.settings'）

- [ ] **Step 3: 实现 `settings.py`**

```python
# app/backend/settings.py
import os
import yaml
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "version": "0.1.0",
    "bind_host": "0.0.0.0",
    "local_host": "127.0.0.1",
    "port": 8080,
    "data_dir": "./data",
    "log_dir": "./logs",
    "model_dir": "./models",
    "storage_dir": "./data",
    "export_dir": "./exports",
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _deep_merge(base, override):
    """深度合并两个 dict，override 的值覆盖 base。"""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _flatten_config(raw: dict) -> dict:
    """将嵌套 YAML 结构展平为扁平 dict，只返回 YAML 中显式出现的键。"""
    flattened = {}
    app_config = raw.get("app", {})
    server_config = raw.get("server", {})
    paths_config = raw.get("paths", {})

    if "version" in app_config:
        flattened["version"] = app_config["version"]
    if "bind_host" in server_config:
        flattened["bind_host"] = server_config["bind_host"]
    if "port" in server_config:
        flattened["port"] = server_config["port"]
    if "data_dir" in paths_config:
        flattened["data_dir"] = paths_config["data_dir"]
        flattened["storage_dir"] = paths_config["data_dir"]
    if "log_dir" in paths_config:
        flattened["log_dir"] = paths_config["log_dir"]
    if "model_dir" in paths_config:
        flattened["model_dir"] = paths_config["model_dir"]
    if "storage_dir" in paths_config:
        flattened["storage_dir"] = paths_config["storage_dir"]
    if "export_dir" in paths_config:
        flattened["export_dir"] = paths_config["export_dir"]
    return flattened


def _normalize_paths(config: dict) -> dict:
    """将相对路径转为基于 PROJECT_ROOT 的绝对路径。"""
    for key in ("data_dir", "log_dir", "model_dir", "storage_dir", "export_dir"):
        path = config[key]
        if not os.path.isabs(path):
            path = os.path.join(PROJECT_ROOT, path)
        config[key] = os.path.normpath(path)
    return config


def _validate_config(config: dict):
    """校验 port 范围和路径可写性。"""
    port = config["port"]
    if not isinstance(port, int) or port < 1024 or port > 65535:
        raise ValueError(f"端口号必须在 1024-65535 之间，当前值: {port}")

    for key in ("data_dir", "log_dir"):
        path = config[key]
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            raise ValueError(f"路径不可写: {path}")


def load_config(config_dir: str | None = None) -> dict:
    """加载配置，合并: 硬编码默认值 < default.yaml < local.yaml(可选)。"""
    merged = dict(DEFAULT_CONFIG)

    if config_dir is None:
        config_dir = os.path.join(PROJECT_ROOT, "app", "config")
    if not os.path.isdir(config_dir):
        logger.warning("配置文件目录 %s 不存在，使用默认配置", config_dir)
        return _normalize_paths(merged)

    # 加载 default.yaml
    default_yaml_path = os.path.join(config_dir, "default.yaml")
    if os.path.isfile(default_yaml_path):
        with open(default_yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        merged = _deep_merge(merged, _flatten_config(raw))
    else:
        logger.warning("default.yaml 缺失，使用默认配置")

    # 加载 local.yaml（可选覆盖）
    local_yaml_path = os.path.join(config_dir, "local.yaml")
    if os.path.isfile(local_yaml_path):
        with open(local_yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        merged = _deep_merge(merged, _flatten_config(raw))

    result = _normalize_paths(merged)
    _validate_config(result)
    return result
```

- [ ] **Step 4: 实现 `app/config/default.yaml`**

```yaml
# app/config/default.yaml
# 安全默认/占位配置，不包含真实部署参数、本机路径、密钥或患者数据。

app:
  version: "0.1.0"

server:
  bind_host: "0.0.0.0"
  port: 8080

paths:
  data_dir: "./data"
  log_dir: "./logs"
  export_dir: "./exports"
  model_dir: "./models"
```

- [ ] **Step 5: 更新 `app/config/README.md`**

将开头描述从“当前只建立目录和职责，不提交真实运行配置”调整为：

```markdown
应用配置命名空间。允许提交安全默认模板（如 `default.yaml`），但不得提交真实运行配置。
```

并保留原有约束：不提交本机私有路径、患者数据、密钥、模型权重或真实部署参数。

- [ ] **Step 6: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_settings.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add app/backend/settings.py app/backend/tests/test_settings.py app/config/default.yaml app/config/README.md
git commit -m "feat: 实现 YAML 配置加载 — 三层合并、路径归一化、port/路径校验"
```

---

### Task 6: storage/json_store.py — JSON 文件存储

**Files:**
- Create: `app/backend/tests/test_json_store.py`
- Create: `app/backend/storage/json_store.py`

- [ ] **Step 1: 写失败测试**

```python
# app/backend/tests/test_json_store.py
import json
import os
import pytest
from app.backend.storage.json_store import JsonStore


class TestJsonStoreInit:
    def test_creates_base_dir(self, tmp_path):
        base = tmp_path / "store"
        JsonStore(str(base))
        assert base.is_dir()

    def test_existing_dir_ok(self, tmp_path):
        store = JsonStore(str(tmp_path))
        assert store._base_dir == str(tmp_path)


class TestReadWrite:
    def test_write_and_read_dict(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("tasks/task_001.json", {"status": "created", "pages": 3})
        data = store.read("tasks/task_001.json")
        assert data == {"status": "created", "pages": 3}

    def test_read_with_default(self, tmp_path):
        store = JsonStore(str(tmp_path))
        data = store.read("nonexistent.json", default={"fallback": True})
        assert data == {"fallback": True}

    def test_read_nonexistent_without_default(self, tmp_path):
        store = JsonStore(str(tmp_path))
        data = store.read("nonexistent.json")
        assert data is None

    def test_atomic_write_does_not_leave_tmp(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("data.json", {"key": "value"})
        # 不应残留 .tmp 文件
        tmp_files = list(tmp_path.glob("*.tmp"))
        nested_tmp = list(tmp_path.glob("**/*.tmp"))
        assert len(tmp_files) == 0
        assert len(nested_tmp) == 0

    def test_write_creates_parent_dir(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("a/b/c/data.json", {"x": 1})
        assert (tmp_path / "a" / "b" / "c" / "data.json").is_file()


class TestExists:
    def test_exists_returns_true(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("test.json", {"a": 1})
        assert store.exists("test.json") is True

    def test_exists_returns_false(self, tmp_path):
        store = JsonStore(str(tmp_path))
        assert store.exists("nonexistent.json") is False


class TestDelete:
    def test_delete_removes_file(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("test.json", {"a": 1})
        store.delete("test.json")
        assert not store.exists("test.json")

    def test_delete_nonexistent_does_not_raise(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.delete("nonexistent.json")  # 不抛异常


class TestPathSecurity:
    def test_rejects_parent_traversal(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.write("../outside.json", {"bad": True})

    def test_rejects_absolute_path(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.read("/etc/passwd")

    def test_rejects_double_dot_middle(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.write("tasks/../../outside.json", {"bad": True})
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_json_store.py -v
```

Expected: 全部 FAIL

- [ ] **Step 3: 实现 `storage/json_store.py`**

```python
# app/backend/storage/json_store.py
import json
import os


class JsonStore:
    """基于本地目录的 JSON 文件读写工具。

    - 路径安全：relative_path 校验，拒绝 ../ 越权和绝对路径
    - 原子写入：先写 .tmp 临时文件，再 os.replace
    - 目录自动创建
    """

    def __init__(self, base_dir: str):
        self._base_dir = os.path.abspath(base_dir)
        os.makedirs(self._base_dir, exist_ok=True)

    def _resolve(self, relative_path: str) -> str:
        """校验并返回安全的绝对路径。"""
        # 拒绝绝对路径
        if os.path.isabs(relative_path):
            raise ValueError(f"路径越权: 不允许绝对路径 {relative_path}")

        resolved = os.path.normpath(os.path.join(self._base_dir, relative_path))
        # 确保解析后的路径仍在 base_dir 下
        if not resolved.startswith(self._base_dir + os.sep) and resolved != self._base_dir:
            raise ValueError(f"路径越权: {relative_path}")

        return resolved

    def read(self, relative_path: str, default=None):
        filepath = self._resolve(relative_path)
        if not os.path.isfile(filepath):
            return default
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def write(self, relative_path: str, data):
        filepath = self._resolve(relative_path)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        tmp_path = filepath + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    def delete(self, relative_path: str):
        filepath = self._resolve(relative_path)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass

    def exists(self, relative_path: str) -> bool:
        filepath = self._resolve(relative_path)
        return os.path.isfile(filepath)
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_json_store.py -v
```

Expected: 全部 PASS（14 passed）

- [ ] **Step 5: Commit**

```bash
git add app/backend/storage/json_store.py app/backend/tests/test_json_store.py
git commit -m "feat: 实现 JsonStore — 路径安全校验、原子写入、目录自动创建"
```

---

### Task 7: routes/system.py — 健康检查端点

**Files:**
- Create: `app/backend/tests/test_system.py`
- Create: `app/backend/routes/system.py`

这个任务需要 Flask 测试客户端。先在测试中手动构建一个最小 Flask app 来测试 system blueprint；`create_backend_app` 在 Task 8 中接入。

- [ ] **Step 1: 写失败测试**

```python
# app/backend/tests/test_system.py
import json
import pytest
from flask import Flask
from app.backend.routes.system import system_bp


def _make_app(config_overrides=None):
    """为测试构建最小 Flask app，只挂载 system_bp。"""
    app = Flask(__name__)
    app.config["BACKEND_CONFIG"] = {
        "version": "0.1.0",
        "bind_host": "0.0.0.0",
        "port": 8080,
        "data_dir": "/tmp/test_data",
        "log_dir": "/tmp/test_logs",
        "export_dir": "/tmp/test_exports",
        "model_dir": "/tmp/test_models",
        "storage_dir": "/tmp/test_data",
        "local_host": "127.0.0.1",
        **(config_overrides or {}),
    }
    app.config["STARTED_AT"] = "2026-05-11T12:00:00+00:00"
    app.config["LAN_ADDRESSES"] = []
    from app.backend.errors import register_error_handlers
    register_error_handlers(app)
    app.register_blueprint(system_bp)
    return app


class TestSystemStatus:
    def test_returns_200(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

    def test_response_structure(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)
        assert data["success"] is True
        assert "data" in data
        assert data["data"]["status"] == "running"
        assert data["data"]["version"] == "0.1.0"
        assert "started_at" in data["data"]
        assert "lan_addresses" in data["data"]

    def test_content_type_is_json(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        assert resp.content_type == "application/json"

    def test_lan_addresses_excludes_localhost(self):
        """127.0.0.1 不应作为手机端可用的默认地址。"""
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)
        for addr in data["data"]["lan_addresses"]:
            assert not addr.startswith("127.0.0.1")


class TestErrorHandling:
    def test_404_returns_json_not_html(self):
        app = _make_app()
        client = app.test_client()
        resp = client.get("/api/nonexistent")
        data = json.loads(resp.data)
        assert "error" in data
        assert data["error"]["code"] == "HTTP_ERROR"
        assert resp.content_type == "application/json"

    def test_500_returns_json_without_stacktrace(self):
        app = Flask(__name__)
        app.config["BACKEND_CONFIG"] = {
            "version": "0.1.0",
            "bind_host": "0.0.0.0",
            "port": 8080,
        }
        app.config["STARTED_AT"] = "2026-05-11T12:00:00+00:00"
        app.config["LAN_ADDRESSES"] = []

        @app.route("/api/will-crash")
        def will_crash():
            raise RuntimeError("boom")

        from app.backend.errors import register_error_handlers
        register_error_handlers(app)

        client = app.test_client()
        resp = client.get("/api/will-crash")
        data = json.loads(resp.data)
        assert resp.status_code == 500
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "RuntimeError" not in json.dumps(data)
        assert "traceback" not in json.dumps(data)
        assert "stack" not in json.dumps(data)
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_system.py -v
```

Expected: 全部 FAIL（ModuleNotFoundError: No module named 'app.backend.routes.system'）

- [ ] **Step 3: 实现 `routes/system.py`**

```python
# app/backend/routes/system.py
from flask import Blueprint, current_app
from ..responses import success

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/system/status")
def get_system_status():
    config = current_app.config.get("BACKEND_CONFIG", {})
    return success(
        data={
            "status": "running",
            "version": config.get("version", "unknown"),
            "started_at": current_app.config.get("STARTED_AT", ""),
            "lan_addresses": current_app.config.get("LAN_ADDRESSES", []),
        }
    )
```

- [ ] **Step 4: 运行测试确认 GREEN**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_system.py -v
```

Expected: 全部 PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add app/backend/routes/system.py app/backend/tests/test_system.py
git commit -m "feat: 实现 GET /api/system/status 健康检查端点"
```

---

### Task 8: __init__.py + main.py — App 工厂 + 启动入口

**Files:**
- Modify: `app/backend/tests/test_system.py`
- Modify: `app/backend/__init__.py`（create_backend_app 工厂）
- Create: `app/backend/main.py`

- [ ] **Step 1: 补充 app 工厂和局域网地址选择测试**

在 `app/backend/tests/test_system.py` 末尾追加：

```python

class TestLanAddressSelection:
    def test_get_lan_addresses_excludes_loopback_and_deduplicates(self, monkeypatch):
        from app.backend import _get_lan_addresses
        import socket

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda hostname, port, family: [
                (family, None, None, "", ("127.0.0.1", 0)),
                (family, None, None, "", ("192.168.1.20", 0)),
                (family, None, None, "", ("192.168.1.20", 0)),
                (family, None, None, "", ("10.0.0.8", 0)),
            ],
        )

        assert _get_lan_addresses(8080) == ["192.168.1.20:8080", "10.0.0.8:8080"]

    def test_get_lan_addresses_returns_empty_when_lookup_fails(self, monkeypatch):
        from app.backend import _get_lan_addresses
        import socket

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")

        def raise_os_error(hostname, port, family):
            raise OSError("network unavailable")

        monkeypatch.setattr(socket, "getaddrinfo", raise_os_error)
        assert _get_lan_addresses(8080) == []


class TestCreateBackendApp:
    def test_create_backend_app_registers_system_route(self, tmp_path, monkeypatch):
        import socket
        from app.backend import create_backend_app

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda hostname, port, family: [
                (family, None, None, "", ("192.168.1.20", 0)),
            ],
        )

        app = create_backend_app(str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["data"]["lan_addresses"] == ["192.168.1.20:8080"]
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/test_system.py -v
```

Expected: 新增测试 FAIL（`_get_lan_addresses` / `create_backend_app` 尚未实现）

- [ ] **Step 3: 实现 `app/backend/__init__.py`**

```python
# app/backend/__init__.py
import socket
from datetime import datetime, timezone

from flask import Flask

from .settings import load_config
from .errors import register_error_handlers


def _get_lan_addresses(port: int) -> list[str]:
    """返回候选局域网地址列表，排除 127.x.x.x。"""
    addresses = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127."):
                addresses.append(f"{addr}:{port}")
    except Exception:
        pass

    # 去重并保持顺序
    seen = set()
    unique = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)
    return unique


def create_backend_app(config_dir: str | None = None) -> Flask:
    config = load_config(config_dir)

    app = Flask(__name__)
    app.config["BACKEND_CONFIG"] = config
    app.config["STARTED_AT"] = datetime.now(timezone.utc).isoformat()
    app.config["LAN_ADDRESSES"] = _get_lan_addresses(config["port"])

    register_error_handlers(app)

    from .routes.system import system_bp
    app.register_blueprint(system_bp)

    return app
```

- [ ] **Step 4: 实现 `app/backend/main.py`**

```python
# app/backend/main.py
"""后端开发/调试启动入口。在生产部署中使用 run.bat。"""
import os
import sys

# 确保项目根在 sys.path 上
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.backend import create_backend_app


def main():
    app = create_backend_app()
    config = app.config["BACKEND_CONFIG"]
    print(f"后端服务启动中...")
    print(f"  本地访问: http://{config['local_host']}:{config['port']}")
    print(f"  健康检查: http://{config['local_host']}:{config['port']}/api/system/status")
    app.run(host=config["bind_host"], port=config["port"], debug=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 启动验证（手动）**

```bash
cd /home/kbzz1/manzufei_ocr && timeout 3 python -m app.backend.main || true
```

Expected: 看到 "后端服务启动中..." 和访问地址提示，无 import 错误。

- [ ] **Step 6: 运行全部测试确认无回归**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add app/backend/__init__.py app/backend/main.py app/backend/tests/test_system.py
git commit -m "feat: 实现 create_backend_app 工厂与 main.py 启动入口"
```

---

### Task 9: 集成验证 — 全量测试 + 启动检查

- [ ] **Step 1: 运行全量测试**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/ -v
```

Expected: 全部 PASS（约 61 个测试）

- [ ] **Step 2: 验证 health check（后台启动 Flask 后 curl）**

```bash
cd /home/kbzz1/manzufei_ocr && python -m app.backend.main &
sleep 2
curl -s http://127.0.0.1:8080/api/system/status | python -m json.tool
kill %1 2>/dev/null
```

Expected:
```json
{
    "success": true,
    "data": {
        "status": "running",
        "version": "0.1.0",
        "started_at": "...",
        "lan_addresses": [...]
    }
}
```

- [ ] **Step 3: 运行所有测试确认最终状态**

```bash
cd /home/kbzz1/manzufei_ocr && python -m pytest app/backend/tests/ -v
```

Expected: 全部 PASS
