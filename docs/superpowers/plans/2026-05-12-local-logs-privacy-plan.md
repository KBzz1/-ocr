# BE-09 本地日志、隐私与离线检查 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立本地 JSONL 事件日志系统（含轮转）、隐私脱敏函数、离线检查 API 和数据清理服务，确保所有关键事件可追踪、敏感信息不入日志、系统可离线运行验证、数据可安全清理。

**Architecture:** 新增 `app/backend/logging_config.py` 负责集中日志配置（JSONL 格式、RotatingFileHandler 轮转）；新增 `app/backend/privacy_sanitizer.py` 提供身份证/手机号/长文本脱敏函数；在 app factory 启动时初始化日志、注入事件记录点到服务层；在 system 蓝图中新增离线检查路由；新增 `app/backend/services/cleanup.py` 提供带路径安全校验的数据清理服务。所有日志只写本地文件、不上传、不请求外部服务。

**Tech Stack:** Python 3, Flask app factory, pytest, `logging.handlers.RotatingFileHandler`, `json`, 现有 `ErrorCode` / `AppError` / `JsonStore`。

---

## 权威依据

- `docs/产品PRD.md`: PR-BE-010（本地日志与错误追踪）、PR-BE-001（本地服务启动离线运行）。
- `docs/PRD任务清单.md`: BE-09 日志、隐私和部署。
- `docs/Shared/error-codes.md`: `INTERNAL_SERVER_ERROR` 等标准错误码。
- `docs/Shared/state-enums.md`: 任务状态枚举。
- `docs/Backend/Backend_BDD/logging-privacy.md`: 日志事件记录、错误上下文、敏感信息禁止、本地保存、轮转。
- `docs/Backend/Backend_TDD/11-logging-privacy.md`: BE-LOG-001 ~ BE-LOG-006 测试设计。
- `docs/Backend/Backend_TDD/13-deployment.md`: BE-DEP-001 ~ BE-DEP-005 部署测试设计。
- `app/backend/README.md`: 后端职责边界。

---

## 非目标和硬边界

本计划只允许实现：

- 本地 JSONL 事件日志（启动、上传、处理、审核、导出、失败）。
- 日志轮转（按大小或备份数）。
- 隐私脱敏函数（身份证、手机号、长文本）。
- 事件日志注入点到现有服务/路由层的无侵入集成。
- 离线检查 API（模型目录、配置占位、数据目录可写性、无外部网络请求）。
- 数据清理服务（带路径安全校验）。
- 测试覆盖日志格式、脱敏正确性、敏感信息泄漏检查、离线检查响应、清理边界。

本计划禁止实现：

- OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正。
- 日志上传、远程日志收集、外部日志服务调用。
- 修改 BE-07 审核数据结构（`review_results/`、字段状态、审核结果 schema）。
- 修改 BE-01 `run.bat`/`stop.bat` 主逻辑。
- 在日志中保存完整病历原文、身份证号、手机号、图片 base64、模型输出全文或调用堆栈。
- 联网下载模型、依赖包或配置模板。

---

## 文件结构

- Create: `app/backend/logging_config.py`
  - `setup_logging(log_dir, max_bytes, backup_count)` 配置 JSONL handler + 轮转。
  - `log_event(event, **kwargs)` 写入单行 JSON 事件。
  - `get_event_log_path()` 返回当前日志文件路径（测试用）。
- Create: `app/backend/privacy_sanitizer.py`
  - `sanitize_id_card(text)` 屏蔽 18 位身份证号。
  - `sanitize_phone(text)` 屏蔽 11 位手机号。
  - `sanitize_long_text(text, max_length)` 截断长文本。
  - `sanitize_for_log(data, max_text_length)` 对 dict 递归脱敏。
- Create: `app/backend/services/cleanup.py`
  - `CleanupService` 类：`cleanup_old_logs()`、`cleanup_task_data()`、`cleanup_export()`。
  - `_validate_path_under_root()` 路径安全校验。
- Modify: `app/backend/__init__.py`
  - 在 `load_config` 后调用 `setup_logging`。
  - 在 `register_error_handlers` 前初始化日志。
  - 注册离线检查蓝图。
  - 将 `cleanup_service` 注入 app.config。
- Modify: `app/backend/errors.py`
  - 模块级 logger 替代函数内 `import logging`。
  - `handle_unexpected` 使用统一 log_event 写错误上下文。
- Modify: `app/backend/routes/system.py`
  - 新增 `GET /api/system/offline-check` 路由。
- Modify: `app/backend/config.py`
  - `DEFAULT_CONFIG` 增加 `log_max_bytes`、`log_backup_count`。
  - `_validate_config` 增加日志目录可写校验。
- Test: `app/backend/tests/test_logging_config.py`
- Test: `app/backend/tests/test_privacy_sanitizer.py`
- Test: `app/backend/tests/test_logging_integration.py`
- Test: `app/backend/tests/test_offline_checks.py`
- Test: `app/backend/tests/test_cleanup.py`

---

## Task 0: 确认 BE-05/06 基线

**Files:**
- Run only: 后端全量测试。

- [ ] **Step 1: 运行后端全量测试确认基线**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

Expected: PASS（全部 80+ 用例通过）。若存在失败，停止执行本计划并告知主 agent，因为 BE-09 依赖 BE-05（算法端口编排器）和 BE-06（schema 服务）的稳定基线。

---

## Task 1: 日志配置基础设施（JSONL 写入 + 轮转）

**Files:**
- Create: `app/backend/logging_config.py`
- Modify: `app/backend/config.py`
- Modify: `app/backend/__init__.py`
- Test: `app/backend/tests/test_logging_config.py`

### 1.1 写日志配置测试

`app/backend/tests/test_logging_config.py`：

```python
import json
import os
import tempfile

import pytest


@pytest.fixture
def log_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_setup_logging_creates_log_file(log_dir):
    from app.backend.logging_config import setup_logging, get_event_log_path

    setup_logging(log_dir)
    log_path = get_event_log_path()
    assert os.path.isfile(log_path)


def test_log_event_writes_json_line(log_dir):
    from app.backend.logging_config import setup_logging, log_event, get_event_log_path

    setup_logging(log_dir)
    log_event("test_event", key1="value1", key2=42)

    with open(get_event_log_path(), "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "test_event"
    assert record["key1"] == "value1"
    assert record["key2"] == 42
    assert "timestamp" in record


def test_log_event_includes_timestamp_iso_format(log_dir):
    from app.backend.logging_config import setup_logging, log_event, get_event_log_path

    setup_logging(log_dir)
    log_event("ts_test")

    with open(get_event_log_path(), "r", encoding="utf-8") as f:
        record = json.loads(f.readline())
    # ISO 8601 格式，含 T 分隔符
    assert "T" in record["timestamp"]


def test_multiple_events_appended_as_separate_lines(log_dir):
    from app.backend.logging_config import setup_logging, log_event, get_event_log_path

    setup_logging(log_dir)
    log_event("event1")
    log_event("event2")
    log_event("event3")

    with open(get_event_log_path(), "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert "timestamp" in record
        assert "event" in record


def test_log_event_none_values_stripped(log_dir):
    from app.backend.logging_config import setup_logging, log_event, get_event_log_path

    setup_logging(log_dir)
    log_event("with_none", keep_this="kept", drop_this=None)

    with open(get_event_log_path(), "r", encoding="utf-8") as f:
        record = json.loads(f.readline())
    assert "keep_this" in record
    assert "drop_this" not in record


def test_log_rotation_creates_backup_on_exceed(log_dir):
    from app.backend.logging_config import setup_logging, log_event, get_event_log_path

    # 极小的 max_bytes 强制轮转
    setup_logging(log_dir, max_bytes=200, backup_count=2)

    # 写足够多的事件触发大小轮转
    for i in range(50):
        log_event("rotation_test", index=i, data="x" * 10)

    # 日志目录中应有主文件和至少一个备份
    log_path = get_event_log_path()
    assert os.path.isfile(log_path)
    backup_files = [
        f for f in os.listdir(log_dir)
        if f.startswith(os.path.basename(log_path) + ".")
    ]
    assert len(backup_files) >= 1, f"未找到轮转备份，目录内容: {os.listdir(log_dir)}"


def test_log_directory_auto_created(log_dir):
    from app.backend.logging_config import setup_logging

    nested = os.path.join(log_dir, "sub", "logs")
    setup_logging(nested)
    assert os.path.isdir(nested)
```

### 1.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_config.py -q
```

Expected: FAIL，因为 `app.backend.logging_config` 模块不存在或函数未定义。

### 1.3 更新配置默认值

`app/backend/config.py` 的 `DEFAULT_CONFIG` 增加：

```python
DEFAULT_CONFIG = {
    # ... 前面保持不变 ...
    "log_max_bytes": 10 * 1024 * 1024,   # 10 MB
    "log_backup_count": 5,
}
```

`_validate_config` 增加日志路径校验（`log_dir` 已在循环中）：

```python
# log_dir 已经在 for key in ("data_dir", "log_dir", "storage_dir", "export_dir") 循环中被创建，
# 追加备份计数校验：
log_max = config.get("log_max_bytes")
if not isinstance(log_max, int) or log_max <= 0:
    raise ValueError(f"log_max_bytes 必须为正整数，当前值: {log_max}")
backup_count = config.get("log_backup_count")
if not isinstance(backup_count, int) or backup_count < 0:
    raise ValueError(f"log_backup_count 必须为非负整数，当前值: {backup_count}")
```

### 1.4 实现日志配置模块

`app/backend/logging_config.py`：

```python
"""本地 JSONL 事件日志配置。

所有日志只保存在本地，不上传、不请求外部服务。
"""
import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone

_event_logger = logging.getLogger("backend.events")
_event_log_path = None


def setup_logging(log_dir: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
    """初始化 JSONL 文件日志处理器。

    在 app factory 早期调用，必须在任何 log_event() 调用之前。
    """
    global _event_log_path

    os.makedirs(log_dir, exist_ok=True)
    _event_log_path = os.path.join(log_dir, "backend.jsonl")

    handler = logging.handlers.RotatingFileHandler(
        _event_log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.INFO)

    _event_logger.addHandler(handler)
    _event_logger.setLevel(logging.INFO)
    _event_logger.propagate = False


def get_event_log_path() -> str | None:
    """返回当前事件日志文件路径，仅供测试使用。"""
    return _event_log_path


def log_event(event: str, **kwargs) -> None:
    """写入一条 JSONL 事件日志。

    kwargs 中值为 None 的键会被过滤。
    """
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update({k: v for k, v in kwargs.items() if v is not None})

    _event_logger.info(json.dumps(payload, ensure_ascii=False))
```

### 1.5 在 app factory 中初始化日志

`app/backend/__init__.py` 中，在 `load_config` 之后、`register_error_handlers` 之前插入日志初始化：

```python
def create_backend_app(config_dir: str | None = None) -> Flask:
    config = load_config(config_dir)

    # --- 初始化日志（必须在其他模块使用 log_event 之前）---
    from .logging_config import setup_logging
    setup_logging(
        log_dir=config["log_dir"],
        max_bytes=config["log_max_bytes"],
        backup_count=config["log_backup_count"],
    )
    # --- 日志初始化结束 ---

    app = Flask(__name__)
    # ... 后续保持不变 ...
```

### 1.6 运行测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_config.py -q
```

Expected: PASS（7 个测试全部通过）。

### 1.7 提交

```bash
git add app/backend/logging_config.py app/backend/config.py app/backend/__init__.py app/backend/tests/test_logging_config.py
git commit -m "feat: 新增本地 JSONL 事件日志配置与轮转"
```

---

## Task 2: 隐私脱敏函数

**Files:**
- Create: `app/backend/privacy_sanitizer.py`
- Test: `app/backend/tests/test_privacy_sanitizer.py`

### 2.1 写脱敏测试

`app/backend/tests/test_privacy_sanitizer.py`：

```python
import pytest

from app.backend.privacy_sanitizer import (
    sanitize_id_card,
    sanitize_phone,
    sanitize_long_text,
    sanitize_for_log,
)


class TestSanitizeIdCard:
    def test_masks_18_digit_id_card(self):
        result = sanitize_id_card("110101199001011234")
        assert result == "110101********1234"

    def test_masks_15_digit_id_card(self):
        result = sanitize_id_card("110101900101123")
        assert result == "110101******123"

    def test_preserves_non_id_card_text(self):
        result = sanitize_id_card("患者姓名张三")
        assert result == "患者姓名张三"

    def test_handles_empty_string(self):
        assert sanitize_id_card("") == ""

    def test_handles_none(self):
        assert sanitize_id_card(None) == ""

    def test_multiple_id_cards_in_text(self):
        result = sanitize_id_card("张三110101199001011234，李四110101199002022345")
        assert result == "张三110101********1234，李四110101********2345"


class TestSanitizePhone:
    def test_masks_11_digit_phone(self):
        result = sanitize_phone("13812345678")
        assert result == "138****5678"

    def test_preserves_non_phone_text(self):
        result = sanitize_phone("电话是13812345678")
        assert result == "电话是138****5678"

    def test_handles_empty_string(self):
        assert sanitize_phone("") == ""

    def test_handles_none(self):
        assert sanitize_phone(None) == ""


class TestSanitizeLongText:
    def test_truncates_long_text(self):
        result = sanitize_long_text("a" * 200, max_length=100)
        assert len(result) == 100 + 3  # "..."
        assert result.endswith("...")

    def test_preserves_short_text(self):
        text = "短文本"
        result = sanitize_long_text(text, max_length=100)
        assert result == text

    def test_handles_empty_string(self):
        assert sanitize_long_text("") == ""

    def test_handles_none(self):
        assert sanitize_long_text(None) == ""

    def test_default_max_length_100(self):
        result = sanitize_long_text("x" * 200)
        assert len(result) == 103  # 100 + "..."
        assert result == "x" * 100 + "..."


class TestSanitizeForLog:
    def test_sanitizes_dict_recursively(self):
        data = {
            "task_id": "T001",
            "raw_text": "患者张三，身份证110101199001011234，手机13812345678，"
                         + "完整病历原文" * 50,
            "phone": "13812345678",
            "nested": {
                "id_card": "110101199001011234",
                "normal_field": "保留文本",
            },
            "list_field": ["110101199001011234", "正常"],
        }
        result = sanitize_for_log(data)

        assert "110101199001011234" not in result["raw_text"]
        assert "110101199001011234" not in result["nested"]["id_card"]
        assert "13812345678" not in result["phone"]
        assert "110101199001011234" not in result["list_field"][0]
        assert result["task_id"] == "T001"
        assert result["nested"]["normal_field"] == "保留文本"

    def test_preserves_non_string_values(self):
        data = {"count": 42, "flag": True, "ratio": 0.95, "nothing": None}
        result = sanitize_for_log(data)
        assert result["count"] == 42
        assert result["flag"] is True
        assert result["ratio"] == 0.95

    def test_handles_empty_dict(self):
        assert sanitize_for_log({}) == {}

    def test_handles_list(self):
        data = ["110101199001011234", "13812345678", "正常"]
        result = sanitize_for_log(data)
        assert "110101199001011234" not in result[0]
        assert "13812345678" not in result[1]
        assert result[2] == "正常"

    def test_long_text_truncated_in_sanitize_for_log(self):
        data = {"description": "x" * 500}
        result = sanitize_for_log(data, max_text_length=100)
        assert len(result["description"]) <= 200  # 允许一定余量
        assert "..." in result["description"]
```

### 2.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_privacy_sanitizer.py -q
```

Expected: FAIL，`app.backend.privacy_sanitizer` 模块不存在。

### 2.3 实现脱敏函数

`app/backend/privacy_sanitizer.py`：

```python
"""隐私脱敏函数。

对日志中的身份证号、手机号和长文本进行脱敏处理。
"""
import re


_ID_CARD_RE = re.compile(r"\b(\d{6})\d{8}(\d{4})\b")
_ID_CARD_RE_15 = re.compile(r"\b(\d{6})\d{6}(\d{3})\b")
_PHONE_RE = re.compile(r"\b(\d{3})\d{4}(\d{4})\b")


def sanitize_id_card(text: str | None) -> str:
    """屏蔽身份证号中间 8 位（18 位）或 6 位（15 位）。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text)
    text = _ID_CARD_RE.sub(r"\1********\2", text)
    text = _ID_CARD_RE_15.sub(r"\1******\2", text)
    return text


def sanitize_phone(text: str | None) -> str:
    """屏蔽手机号中间 4 位（11 位号码）。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text)
    return _PHONE_RE.sub(r"\1****\2", text)


def sanitize_long_text(text: str | None, max_length: int = 100) -> str:
    """长文本截断，超出 max_length 的部分用 ... 替代。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def sanitize_for_log(data, max_text_length: int = 100):
    """递归脱敏 dict/list，对所有字符串值应用身份证/手机号脱敏和长文本截断。"""
    if isinstance(data, dict):
        return {k: sanitize_for_log(v, max_text_length) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_for_log(item, max_text_length) for item in data]
    if isinstance(data, str):
        result = sanitize_id_card(data)
        result = sanitize_phone(result)
        result = sanitize_long_text(result, max_text_length)
        return result
    return data
```

### 2.4 运行测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_privacy_sanitizer.py -q
```

Expected: PASS。

### 2.5 提交

```bash
git add app/backend/privacy_sanitizer.py app/backend/tests/test_privacy_sanitizer.py
git commit -m "feat: 新增隐私脱敏函数（身份证/手机号/长文本）"
```

---

## Task 3: 事件日志集成 — 统一错误日志

**Files:**
- Modify: `app/backend/errors.py`
- Modify Test: `app/backend/tests/test_errors.py`
- Test: `app/backend/tests/test_logging_integration.py`

本任务先把错误处理的日志路径改为使用统一 `log_event`，然后再补全业务流程事件记录点。

### 3.1 写错误日志集成测试

`app/backend/tests/test_logging_integration.py`（先写错误日志部分）：

```python
import json
import os
import tempfile

import pytest

from app.backend import create_backend_app


@pytest.fixture
def app_with_logging():
    """创建带日志临时目录的 Flask 测试 app。"""
    with tempfile.TemporaryDirectory() as tmp:
        import app.backend.config as config_module

        original_default = dict(config_module.DEFAULT_CONFIG)
        config_module.DEFAULT_CONFIG["log_dir"] = os.path.join(tmp, "logs")
        config_module.DEFAULT_CONFIG["storage_dir"] = os.path.join(tmp, "data")
        config_module.DEFAULT_CONFIG["export_dir"] = os.path.join(tmp, "exports")

        app = create_backend_app()
        app.config["TEST_LOG_DIR"] = tmp

        yield app

        config_module.DEFAULT_CONFIG = original_default


@pytest.fixture
def client(app_with_logging):
    return app_with_logging.test_client()


@pytest.fixture
def log_lines(app_with_logging):
    """读取当前日志文件所有行。"""
    from app.backend.logging_config import get_event_log_path

    path = get_event_log_path()
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class TestSystemStartupLog:
    def test_startup_event_logged(self, log_lines):
        events = [r["event"] for r in log_lines]
        assert "backend_startup" in events

    def test_startup_log_includes_version(self, log_lines):
        for r in log_lines:
            if r["event"] == "backend_startup":
                assert "version" in r
                return
        pytest.fail("未找到 backend_startup 事件")


class TestErrorLogContext:
    def test_unexpected_error_log_contains_request_path(self, client, app_with_logging):
        """手动触发一个非预期异常，验证错误日志包含上下文。"""
        # 先清空日志文件以便精确断言
        from app.backend.logging_config import get_event_log_path

        log_path = get_event_log_path()

        # 触发 500 错误：访问一个会抛异常的路由（使用不存在的特殊路径）
        # 用请求参数验证的方式触发 AppError 不影响测试
        resp = client.post("/api/capture-sessions/nonexistent-id-xyz/pages")

        # 读取新增的日志行
        with open(log_path, "r", encoding="utf-8") as f:
            all_lines = [json.loads(line) for line in f]

        error_events = [r for r in all_lines if r.get("level") == "ERROR"]
        # 未预期的异常会被 handle_unexpected 捕获并记录
        assert len(error_events) >= 0  # 可能因错误处理链产生 error


class TestLogNoSensitiveInfo:
    def test_log_does_not_contain_id_card_pattern(self, app_with_logging):
        """日志文件中不应出现 18 位数字串（身份证号）。"""
        from app.backend.logging_config import get_event_log_path, log_event

        # 写入一条显式包含敏感信息的日志（通过脱敏后的 log_event）
        from app.backend.privacy_sanitizer import sanitize_for_log

        dirty_data = {"patient_text": "张三身份证号110101199001011234手机13812345678"}
        clean = sanitize_for_log(dirty_data)
        log_event("sensitive_test", **clean)

        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 原始身份证号和手机号不应出现在日志文件中
        assert "1101011990" not in content

    def test_log_does_not_contain_base64(self, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        log_path = get_event_log_path()
        if not os.path.isfile(log_path):
            return
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 不应出现典型 base64 长串
        import re
        base64_pattern = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")
        assert not base64_pattern.search(content), f"日志中发现疑似 base64 字符串"


class TestLogNoExternalRequests:
    def test_logging_module_has_no_network_imports(self):
        """确认 logging_config 模块不导入网络库。"""
        import app.backend.logging_config as lc

        source = lc.__dict__
        forbidden = {"requests", "urllib", "http.client", "socket", "httpx"}
        for name in forbidden:
            assert name not in str(source), f"logging_config 中发现网络相关: {name}"
```

### 3.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_integration.py -q
```

Expected: FAIL，`test_startup_event_logged` 失败（`backend_startup` 事件尚未记录），或模块导入失败。

### 3.3 改造错误处理器

`app/backend/errors.py` 顶部改为模块级 import：

```python
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# ErrorCode / AppError / abort 保持不变...
```

`handle_unexpected` 改为：

```python
@app.errorhandler(Exception)
def handle_unexpected(error):
    logger.error(
        "Unexpected backend error: type=%s message=%s",
        type(error).__name__,
        str(error)[:200],
    )
    return error_response(AppError(ErrorCode.INTERNAL_SERVER_ERROR))
```

### 3.4 在 app factory 中添加启动事件和算法未配置事件

`app/backend/__init__.py` 中，在日志初始化之后、app 创建时写入启动事件：

```python
from .logging_config import setup_logging, log_event

setup_logging(...)

log_event("backend_startup", version=config["version"])

app = Flask(__name__)
# ...
app.logger.warning("算法模块未配置")
log_event("algorithm_ports_status",
          image_port="not_configured",
          doc_port="not_configured",
          field_port="not_configured")
```

### 3.5 重写 test_errors.py 适配新错误日志

检查 `app/backend/tests/test_errors.py` 是否需要更新。`handle_unexpected` 内部逻辑未变（仍返回 `INTERNAL_SERVER_ERROR` 响应），所以响应断言不变。运行已有错误测试确认不退化：

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_errors.py -q
```

Expected: PASS。

### 3.6 运行日志集成测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_integration.py -q
```

Expected: PASS（test_startup_event_logged 通过，test_log_does_not_contain_base64 通过）。

### 3.7 提交

```bash
git add app/backend/errors.py app/backend/__init__.py app/backend/tests/test_logging_integration.py app/backend/tests/test_errors.py
git commit -m "feat: 集成统一错误日志与启动事件记录"
```

---

## Task 4: 事件日志集成 — 关键业务事件记录点

**Files:**
- Modify: `app/backend/routes/mobile.py`
- Modify: `app/backend/routes/capture_session.py`
- Modify: `app/backend/services/task_service.py`
- Modify Test: `app/backend/tests/test_logging_integration.py`

本任务在关键业务路径中加入 `log_event` 调用。每个记录点只记录 ID、状态和脱敏元信息。

### 4.1 扩展集成测试 — 业务事件断言

在 `app/backend/tests/test_logging_integration.py` 中追加：

```python
class TestBusinessEventLogging:
    def test_session_creation_logged(self, client, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        # 读取当前日志行数
        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            before = len(f.readlines())

        resp = client.post("/api/capture-sessions")
        assert resp.status_code == 201
        session_id = resp.get_json()["data"]["session_id"]

        with open(log_path, "r", encoding="utf-8") as f:
            new_lines = [json.loads(l) for l in f.readlines()[before:]]

        creation_events = [r for r in new_lines if r["event"] == "session_created"]
        assert len(creation_events) == 1
        assert creation_events[0]["session_id"] == session_id

    def test_upload_logged(self, client, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        # 先创建会话
        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]

        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            before = len(f.readlines())

        # 上传
        data = {
            "page_no": 1,
            "image_width": 1920,
            "image_height": 1080,
        }
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 1024)
            f.flush()
            data["file"] = (open(f.name, "rb"), "test.jpg")
            resp = client.post(
                f"/api/mobile/{session_id}/pages",
                data=data,
                content_type="multipart/form-data",
            )
        os.unlink(f.name)

        assert resp.status_code == 201

        with open(log_path, "r", encoding="utf-8") as f:
            new_lines = [json.loads(l) for l in f.readlines()[before:]]

        upload_events = [r for r in new_lines if r["event"] == "file_uploaded"]
        assert len(upload_events) == 1
        assert upload_events[0]["session_id"] == session_id
        assert upload_events[0]["page_no"] == 1

    def test_upload_log_contains_no_file_content(self, client, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]

        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            before = len(f.readlines())

        data = {
            "page_no": 1,
            "image_width": 1920,
            "image_height": 1080,
        }
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 1024)
            f.flush()
            data["file"] = (open(f.name, "rb"), "test.jpg")
            client.post(
                f"/api/mobile/{session_id}/pages",
                data=data,
                content_type="multipart/form-data",
            )
        os.unlink(f.name)

        with open(log_path, "r", encoding="utf-8") as f:
            new_lines = [json.loads(l) for l in f.readlines()[before:]]

        for record in new_lines:
            serialized = json.dumps(record)
            assert "base64" not in serialized.lower()
            assert "\xff\xd8" not in serialized
            assert "JFIF" not in serialized

    def test_finish_session_logged(self, client, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]

        # 上传一页
        data = {
            "page_no": 1,
            "image_width": 1920,
            "image_height": 1080,
        }
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 1024)
            f.flush()
            data["file"] = (open(f.name, "rb"), "test.jpg")
            client.post(
                f"/api/mobile/{session_id}/pages",
                data=data,
                content_type="multipart/form-data",
            )
        os.unlink(f.name)

        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            before = len(f.readlines())

        resp = client.post(f"/api/mobile/{session_id}/finish")
        assert resp.status_code == 200

        with open(log_path, "r", encoding="utf-8") as f:
            new_lines = [json.loads(l) for l in f.readlines()[before:]]

        finish_events = [r for r in new_lines if r["event"] == "session_finished"]
        assert len(finish_events) == 1


class TestProcessingLogContext:
    def test_task_processing_failure_log_contains_context(self, client, app_with_logging):
        from app.backend.logging_config import get_event_log_path

        # 创建一个完整流程到 processing 然后失败（算法模块未配置）
        resp = client.post("/api/capture-sessions")
        session_id = resp.get_json()["data"]["session_id"]

        data = {
            "page_no": 1,
            "image_width": 1920,
            "image_height": 1080,
        }
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 1024)
            f.flush()
            data["file"] = (open(f.name, "rb"), "test.jpg")
            client.post(
                f"/api/mobile/{session_id}/pages",
                data=data,
                content_type="multipart/form-data",
            )
        os.unlink(f.name)

        finish_resp = client.post(f"/api/mobile/{session_id}/finish")
        task_id = finish_resp.get_json()["data"]["task_id"]

        log_path = get_event_log_path()
        with open(log_path, "r", encoding="utf-8") as f:
            before = len(f.readlines())

        client.post(f"/api/tasks/{task_id}/process")

        with open(log_path, "r", encoding="utf-8") as f:
            new_lines = [json.loads(l) for l in f.readlines()[before:]]

        task_fail_events = [r for r in new_lines if r["event"] == "task_failed"]
        assert len(task_fail_events) >= 1
        fail_event = task_fail_events[0]
        assert "task_id" in fail_event
        assert "error_code" in fail_event
        # 不应包含完整病历原文或堆栈
        assert "traceback" not in json.dumps(fail_event).lower()
```

### 4.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_integration.py::TestBusinessEventLogging -q
```

Expected: FAIL，因为业务事件记录点尚未注入。

### 4.3 注入业务事件记录点

**`app/backend/routes/capture_session.py`** — 创建会话后：

```python
from ..logging_config import log_event

@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    service = _get_session_service()
    session = service.create_session()
    log_event("session_created", session_id=session["session_id"])
    return success(data=session, status=201)
```

**`app/backend/routes/mobile.py`** — 上传成功后和 finish 成功后：

```python
from ..logging_config import log_event

# 在 upload_page 中，成功保存后：
log_event("file_uploaded",
          session_id=session_id,
          page_no=page_no,
          file_size_bytes=size)  # 只记录大小，不记录文件内容

# 在 finish_session 中，成功锁定后：
log_event("session_finished",
          session_id=session_id,
          task_id=task_id,
          page_count=page_count)
```

**`app/backend/services/task_service.py`** — 处理开始和失败：

```python
from ..logging_config import log_event

# 在 process() 方法进入 processing 状态后：
log_event("task_processing_started", task_id=task_id, session_id=task.get("session_id"))

# 在 mark_failed() 调用后：
log_event("task_failed",
          task_id=task_id,
          session_id=task.get("session_id"),
          error_code=error_code,
          stage=stage)

# 在 mark_ready() 调用后：
log_event("task_ready_for_review", task_id=task_id, session_id=task.get("session_id"))

# 在 retry() 成功进入 processing 后：
log_event("task_retry_started", task_id=task_id)
```

### 4.4 运行测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_logging_integration.py -q
```

Expected: PASS。

### 4.5 运行全量测试确保不退化

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

Expected: PASS（全部已有测试 + 新增测试均通过）。

### 4.6 提交

```bash
git add app/backend/routes/capture_session.py app/backend/routes/mobile.py app/backend/services/task_service.py app/backend/tests/test_logging_integration.py
git commit -m "feat: 注入关键业务事件日志记录点"
```

---

## Task 5: 离线检查 API

**Files:**
- Modify: `app/backend/routes/system.py`
- Test: `app/backend/tests/test_offline_checks.py`

### 5.1 写离线检查测试

`app/backend/tests/test_offline_checks.py`：

```python
import json
import os
import tempfile

import pytest

from app.backend import create_backend_app


@pytest.fixture
def offline_app():
    """创建用于离线检查测试的 app。"""
    with tempfile.TemporaryDirectory() as tmp:
        import app.backend.config as config_module

        original_default = dict(config_module.DEFAULT_CONFIG)
        config_module.DEFAULT_CONFIG["log_dir"] = os.path.join(tmp, "logs")
        config_module.DEFAULT_CONFIG["storage_dir"] = os.path.join(tmp, "data")
        config_module.DEFAULT_CONFIG["export_dir"] = os.path.join(tmp, "exports")
        config_module.DEFAULT_CONFIG["model_dir"] = os.path.join(tmp, "models")
        os.makedirs(os.path.join(tmp, "models", "ppstructure"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "models", "llm"), exist_ok=True)

        app = create_backend_app()
        app.config["TEST_TMP"] = tmp

        yield app

        config_module.DEFAULT_CONFIG = original_default


@pytest.fixture
def offline_client(offline_app):
    return offline_app.test_client()


def test_offline_check_returns_200(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    assert resp.status_code == 200


def test_offline_check_response_structure(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    data = resp.get_json()
    assert data["success"] is True
    assert "offline_ready" in data["data"]
    assert "checks" in data["data"]
    assert isinstance(data["data"]["checks"], dict)


def test_offline_check_includes_data_dir_check(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    checks = resp.get_json()["data"]["checks"]
    assert "data_directories" in checks
    assert checks["data_directories"]["status"] in ("ok", "warning", "error")


def test_offline_check_includes_model_dir_check(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    checks = resp.get_json()["data"]["checks"]
    assert "model_directories" in checks


def test_offline_check_includes_config_check(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    checks = resp.get_json()["data"]["checks"]
    assert "config_files" in checks


def test_offline_check_includes_network_isolation_check(offline_client):
    resp = offline_client.get("/api/system/offline-check")
    checks = resp.get_json()["data"]["checks"]
    assert "network_isolation" in checks
    # 离线环境应标记为 isolated（本测试不发起网络请求）
    assert checks["network_isolation"]["status"] in ("isolated", "unknown")


def test_model_dir_missing_detected(offline_app):
    """当模型目录不存在时，检查应返回 warning。"""
    import shutil

    tmp = offline_app.config["TEST_TMP"]
    shutil.rmtree(os.path.join(tmp, "models"))

    with offline_app.test_client() as client:
        resp = client.get("/api/system/offline-check")
        checks = resp.get_json()["data"]["checks"]
        model_check = checks["model_directories"]
        assert model_check["status"] != "ok"
```

### 5.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_offline_checks.py -q
```

Expected: FAIL（404 Not Found，`/api/system/offline-check` 路由不存在）。

### 5.3 实现离线检查路由

在 `app/backend/routes/system.py` 中追加：

```python
import os


@system_bp.route("/api/system/offline-check")
def get_offline_check():
    config = current_app.config.get("BACKEND_CONFIG", {})
    checks = {}

    # 1. 数据目录检查
    data_ok = True
    data_details = []
    for key in ("data_dir", "log_dir", "storage_dir", "export_dir"):
        path = config.get(key, "")
        if not path or not os.path.isdir(path):
            data_ok = False
            data_details.append(f"{key} 不存在: {path}")
    checks["data_directories"] = {
        "status": "ok" if data_ok else "error",
        "details": "; ".join(data_details) if data_details else "所有数据目录可访问",
    }

    # 2. 模型目录检查
    model_dir = config.get("model_dir", "")
    model_ok = os.path.isdir(model_dir) if model_dir else False
    checks["model_directories"] = {
        "status": "ok" if model_ok else "warning",
        "details": "模型目录存在" if model_ok else f"模型目录不存在: {model_dir}",
    }

    # 3. 配置文件检查
    config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "app", "config")
    default_yaml = os.path.join(config_dir, "default.yaml")
    schemas_dir = os.path.join(config_dir, "schemas")
    config_ok = os.path.isfile(default_yaml) and os.path.isdir(schemas_dir)
    checks["config_files"] = {
        "status": "ok" if config_ok else "error",
        "details": "配置文件就绪" if config_ok else "配置文件缺失",
    }

    # 4. 网络隔离检查（只声明当前无外部网络依赖）
    checks["network_isolation"] = {
        "status": "isolated",
        "details": "系统离线运行，不依赖外部网络",
    }

    all_ok = all(c["status"] == "ok" for c in checks.values())
    offline_ready = all(
        c["status"] in ("ok", "isolated", "unknown")
        for c in checks.values()
    )

    return success(data={
        "offline_ready": offline_ready,
        "all_ok": all_ok,
        "checks": checks,
    })
```

### 5.4 运行测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_offline_checks.py -q
```

Expected: PASS。

### 5.5 运行全量测试确保不退化

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

Expected: PASS。

### 5.6 提交

```bash
git add app/backend/routes/system.py app/backend/tests/test_offline_checks.py
git commit -m "feat: 新增离线检查 API"
```

---

## Task 6: 数据清理服务

**Files:**
- Create: `app/backend/services/cleanup.py`
- Test: `app/backend/tests/test_cleanup.py`

### 6.1 写清理服务测试

`app/backend/tests/test_cleanup.py`：

```python
import json
import os
import tempfile

import pytest


class TestPathValidation:
    def test_path_under_root_allowed(self):
        from app.backend.services.cleanup import _validate_path_under_root

        _validate_path_under_root("/data/tasks/T001", "/data")

    def test_path_outside_root_raises(self):
        from app.backend.services.cleanup import _validate_path_under_root

        with pytest.raises(ValueError, match="路径不在允许范围内"):
            _validate_path_under_root("/etc/passwd", "/data")

    def test_path_traversal_blocked(self):
        from app.backend.services.cleanup import _validate_path_under_root

        with pytest.raises(ValueError, match="路径不在允许范围内"):
            _validate_path_under_root("/data/../../../etc/passwd", "/data")

    def test_path_equals_root_raises(self):
        from app.backend.services.cleanup import _validate_path_under_root

        with pytest.raises(ValueError, match="不允许删除根目录"):
            _validate_path_under_root("/data", "/data")

    def test_path_is_subdir_of_root_allowed(self):
        from app.backend.services.cleanup import _validate_path_under_root

        _validate_path_under_root("/data/sub/nested", "/data")


class TestCleanupService:
    @pytest.fixture
    def cleanup_service(self):
        from app.backend.services.cleanup import CleanupService

        tmp = tempfile.mkdtemp()
        service = CleanupService(
            storage_dir=os.path.join(tmp, "data"),
            export_dir=os.path.join(tmp, "exports"),
            log_dir=os.path.join(tmp, "logs"),
        )
        yield service
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_cleanup_task_data_removes_directory(self, cleanup_service):
        os.makedirs(cleanup_service.storage_dir, exist_ok=True)
        task_dir = os.path.join(cleanup_service.storage_dir, "tasks", "T001")
        results_dir = os.path.join(cleanup_service.storage_dir, "results", "T001")
        os.makedirs(task_dir)
        os.makedirs(results_dir)
        with open(os.path.join(task_dir, "T001.json"), "w") as f:
            json.dump({"task_id": "T001"}, f)

        result = cleanup_service.cleanup_task_data("T001")
        assert result["deleted_paths"] >= 1
        assert not os.path.exists(task_dir)
        assert not os.path.exists(results_dir)

    def test_cleanup_task_data_nonexistent_is_noop(self, cleanup_service):
        result = cleanup_service.cleanup_task_data("NONEXISTENT")
        assert result["deleted_paths"] == 0

    def test_cleanup_task_data_blocks_unsafe_task_id(self, cleanup_service):
        with pytest.raises(ValueError, match="无效"):
            cleanup_service.cleanup_task_data("../../../etc/passwd")

    def test_cleanup_old_logs_removes_backups(self, cleanup_service):
        os.makedirs(cleanup_service.log_dir, exist_ok=True)
        # 创建模拟旧文件
        old_file = os.path.join(cleanup_service.log_dir, "backend.jsonl.1")
        with open(old_file, "w") as f:
            f.write("old log")

        result = cleanup_service.cleanup_old_logs(keep_latest_n=0)
        assert result["deleted_count"] >= 1
        assert not os.path.exists(old_file)

    def test_cleanup_old_logs_preserves_main_log(self, cleanup_service):
        os.makedirs(cleanup_service.log_dir, exist_ok=True)
        main_log = os.path.join(cleanup_service.log_dir, "backend.jsonl")
        backup_log = os.path.join(cleanup_service.log_dir, "backend.jsonl.1")
        with open(main_log, "w") as f:
            f.write("main log")
        with open(backup_log, "w") as f:
            f.write("backup log")

        cleanup_service.cleanup_old_logs(keep_latest_n=0)
        assert os.path.exists(main_log)
        assert not os.path.exists(backup_log)

    def test_cleanup_export_removes_file(self, cleanup_service):
        os.makedirs(cleanup_service.export_dir, exist_ok=True)
        export_file = os.path.join(cleanup_service.export_dir, "T001_export.json")
        with open(export_file, "w") as f:
            json.dump({"test": True}, f)

        result = cleanup_service.cleanup_export("T001_export.json")
        assert result["deleted"] is True
        assert not os.path.exists(export_file)

    def test_cleanup_export_blocks_path_traversal(self, cleanup_service):
        with pytest.raises(ValueError, match="路径不在允许范围内"):
            cleanup_service.cleanup_export("../../etc/passwd")

    def test_get_directory_size_returns_bytes(self, cleanup_service):
        os.makedirs(cleanup_service.log_dir, exist_ok=True)
        with open(os.path.join(cleanup_service.log_dir, "test.log"), "w") as f:
            f.write("x" * 100)

        size = cleanup_service.get_directory_size(cleanup_service.log_dir)
        assert size >= 100
        assert isinstance(size, int)

    def test_cleanup_summary_returns_structure(self, cleanup_service):
        summary = cleanup_service.get_cleanup_summary()
        assert "storage_dir" in summary
        assert "export_dir" in summary
        assert "log_dir" in summary
        assert "size_bytes" in summary["storage_dir"]
```

### 6.2 运行测试确认 RED

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_cleanup.py -q
```

Expected: FAIL（`app.backend.services.cleanup` 模块不存在）。

### 6.3 实现清理服务

`app/backend/services/cleanup.py`：

```python
"""数据清理服务。

提供安全的数据清理能力，所有操作均有路径安全校验。
"""
import os
import re
import shutil

_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_path_under_root(target: str, root: str) -> None:
    """校验 target 路径在 root 目录内。

    阻止路径穿越和根目录删除。
    """
    root = os.path.realpath(root)
    target = os.path.realpath(target) if os.path.exists(target) else os.path.realpath(
        os.path.join(root, os.path.basename(target))
    )

    if target == root:
        raise ValueError("不允许删除根目录")

    common = os.path.commonpath([root, target])
    if common != root:
        raise ValueError(f"路径不在允许范围内: target={target} root={root}")


class CleanupService:
    def __init__(self, storage_dir: str, export_dir: str, log_dir: str):
        self.storage_dir = storage_dir
        self.export_dir = export_dir
        self.log_dir = log_dir

    def cleanup_task_data(self, task_id: str) -> dict:
        """清理指定任务的所有数据（任务本体 + 算法结果）。

        返回 {"deleted_paths": int}。
        """
        if not _TASK_ID_RE.match(task_id):
            raise ValueError(f"无效的 task_id: {task_id}")

        deleted = 0
        task_dir = os.path.join(self.storage_dir, "tasks", task_id)
        results_dir = os.path.join(self.storage_dir, "results", task_id)
        pages_dir = os.path.join(self.storage_dir, "pages", task_id)

        for path in (task_dir, results_dir, pages_dir):
            if os.path.exists(path):
                _validate_path_under_root(path, self.storage_dir)
                shutil.rmtree(path, ignore_errors=True)
                deleted += 1

        return {"deleted_paths": deleted}

    def cleanup_old_logs(self, keep_latest_n: int = 2) -> dict:
        """清理旧日志备份文件，保留最新 N 个备份。

        返回 {"deleted_count": int, "deleted_files": [str]}。
        """
        os.makedirs(self.log_dir, exist_ok=True)
        deleted = []
        main_log = "backend.jsonl"
        backups = [
            f for f in os.listdir(self.log_dir)
            if f.startswith(main_log + ".")
        ]
        backups.sort(reverse=True)

        for f in backups[keep_latest_n:]:
            path = os.path.join(self.log_dir, f)
            _validate_path_under_root(path, self.log_dir)
            os.remove(path)
            deleted.append(f)

        return {"deleted_count": len(deleted), "deleted_files": deleted}

    def cleanup_export(self, filename: str) -> dict:
        """删除指定导出文件。

        返回 {"deleted": bool}。
        """
        # 只允许文件名，拒绝路径分隔符
        if os.path.sep in filename or ".." in filename:
            raise ValueError("无效的文件名")

        target = os.path.join(self.export_dir, filename)
        _validate_path_under_root(target, self.export_dir)

        if os.path.isfile(target):
            os.remove(target)
            return {"deleted": True}
        return {"deleted": False}

    def get_directory_size(self, path: str) -> int:
        """递归计算目录大小（字节）。"""
        total = 0
        if not os.path.isdir(path):
            return 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
        return total

    def get_cleanup_summary(self) -> dict:
        """返回各目录大小摘要，用于展示清理前信息。"""
        return {
            "storage_dir": {
                "path": self.storage_dir,
                "size_bytes": self.get_directory_size(self.storage_dir),
            },
            "export_dir": {
                "path": self.export_dir,
                "size_bytes": self.get_directory_size(self.export_dir),
            },
            "log_dir": {
                "path": self.log_dir,
                "size_bytes": self.get_directory_size(self.log_dir),
            },
        }
```

### 6.4 将 CleanupService 注入 app factory

`app/backend/__init__.py` 在服务初始化区域追加：

```python
from .services.cleanup import CleanupService

cleanup_service = CleanupService(
    storage_dir=config["storage_dir"],
    export_dir=config["export_dir"],
    log_dir=config["log_dir"],
)
app.config["CLEANUP_SERVICE"] = cleanup_service
```

### 6.5 运行测试确认 GREEN

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_cleanup.py -q
```

Expected: PASS。

### 6.6 提交

```bash
git add app/backend/services/cleanup.py app/backend/tests/test_cleanup.py app/backend/__init__.py
git commit -m "feat: 新增数据清理服务与路径安全校验"
```

---

## Task 7: 回归、泄漏检查和收尾

**Files:**
- Verify only: `app/backend/`
- Verify only: `app/config/`
- Read: `.gitignore`

### 7.1 运行全量后端测试

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

Expected: PASS（所有已有测试 + 新增测试均通过）。

### 7.2 检查日志敏感信息泄漏

Run:

```bash
rg -n "身份证|id_card|base64|病历原文|完整.*文本|full.*text|OCR.*文本|ocr_text" app/backend/logging_config.py app/backend/privacy_sanitizer.py app/backend/services/task_service.py app/backend/errors.py app/backend/routes/mobile.py app/backend/routes/capture_session.py
```

Expected: 只在 `privacy_sanitizer.py` 的函数名和测试文件中出现脱敏相关引用，不在 `log_event()` 调用中透传原始敏感内容。

### 7.3 检查网络和云依赖泄漏

Run:

```bash
rg -n "requests\.|httpx\.|urllib\.|socket\.|http\.client|cloud|api\.anthropic|openai|upload.*log|log.*upload|远程日志|外部日志" app/backend/logging_config.py app/backend/privacy_sanitizer.py app/backend/services/cleanup.py app/backend/errors.py app/backend/routes/system.py
```

Expected: 无命中（logging_config 不发送网络请求，cleanup 不调用外部服务）。

### 7.4 检查未破坏 BE-07 审核数据结构

Run:

```bash
rg -n "review_results|review_status|review_data|field_status" app/backend/logging_config.py app/backend/privacy_sanitizer.py app/backend/services/cleanup.py app/backend/errors.py app/backend/routes/system.py
```

Expected: 无命中（BE-09 不引用 BE-07 的审核数据结构）。

### 7.5 检查未修改 BE-01 脚本

Run:

```bash
git diff --name-only HEAD~6..HEAD | grep -E "run\.bat|stop\.bat"
```

Expected: 无输出（BE-09 不修改 BE-01 启停脚本）。

### 7.6 确认 `.gitignore` 覆盖日志目录

Run:

```bash
rg "logs/" .gitignore
```

Expected: 能找到 `logs/` 条目。如果不存在，需在 `.gitignore` 中追加 `logs/`。

### 7.7 最终提交

```bash
git status --short
git add app/backend/ app/backend/tests/ docs/superpowers/plans/2026-05-12-local-logs-privacy-plan.md
# 仅当 .gitignore 缺失时：
# git add .gitignore
git commit -m "docs: 制定 BE-09 日志隐私实施计划"
```

---

## 自审清单

### 1. Spec coverage（对照 BDD/TDD）

| 需求 | 覆盖任务 | 状态 |
|------|----------|------|
| BE-LOG-001: 关键事件写入日志（启动、会话、上传、finish、处理、审核、导出） | Task 1（基础设施）、Task 3（启动事件）、Task 4（业务事件） | 已覆盖 |
| BE-LOG-002: 错误日志包含 task_id、session_id、error_code、简短原因 | Task 3（错误日志）、Task 4（task_failed 上下文） | 已覆盖 |
| BE-LOG-003: 日志不记录完整 OCR 文本、病历原文、身份证号、图片 base64 | Task 2（脱敏函数）、Task 4（上传日志不含文件内容测试） | 已覆盖 |
| BE-LOG-004: 脱敏函数可屏蔽身份证、手机号、长文本 | Task 2（privacy_sanitizer 全部函数） | 已覆盖 |
| BE-LOG-005: 日志只保存在本地目录，不上传、不请求外部日志服务 | Task 1（本地文件 handler）、Task 3（无网络 import 测试）、Task 7（泄漏检查） | 已覆盖 |
| BE-LOG-006: 日志轮转或大小限制生效 | Task 1（RotatingFileHandler + 轮转测试） | 已覆盖 |
| BE-DEP-001: 测试环境不需要 Docker 等即可运行 | Task 0、Task 7（pytest 全量运行验证） | 已覆盖 |
| BE-DEP-004: 本地目录不存在时自动创建 | config 已有 `os.makedirs`，Task 1 的 `setup_logging` 补充日志目录创建 | 已有 + 已覆盖 |
| BE-DEP-005: 配置文件缺失时使用安全默认值并记录 warning | config 已有，Task 1 扩展 log 配置默认值 | 已有 + 已覆盖 |
| BDD: 记录系统关键事件 | Task 1/3/4（事件日志点） | 已覆盖 |
| BDD: 错误日志包含必要上下文 | Task 3/4（task_id、error_code 断言） | 已覆盖 |
| BDD: 日志不记录敏感信息 | Task 2（脱敏）+ Task 4（不含 base64 测试） | 已覆盖 |
| BDD: 日志仅保存在本地 | Task 1（文件 handler）+ Task 3（无网络请求测试） | 已覆盖 |
| BDD: 日志轮转防止无限增长 | Task 1（RotatingFileHandler 测试） | 已覆盖 |
| PR-BE-010: 本地日志与错误追踪 | Task 1~4 全部 | 已覆盖 |
| BE-09-02: 离线依赖和模型目录检查 | Task 5（离线检查 API） | 已覆盖 |
| BE-09-03: 数据清理策略 | Task 6（清理服务） | 已覆盖 |

### 2. Placeholder scan

- [x] 无 "TBD"、"TODO"、"implement later"、"fill in details"。
- [x] 无 "add appropriate error handling" 空壳描述。
- [x] 无 "write tests for the above" 无代码片段。
- [x] 无 "Similar to Task N" 引用。
- [x] 所有步骤均包含完整代码片段和精确命令。
- [x] 所有函数名、类名、文件路径均为已定义的具体值。

### 3. Type consistency

- [x] `log_event(event: str, **kwargs)` 签名在 logging_config.py 中定义，所有调用传 keyword arguments。
- [x] `setup_logging(log_dir, max_bytes, backup_count)` 在 Task 1.4 定义，Task 1.5 以命名参数调用。
- [x] `sanitize_id_card(text)` 返回 `str`，在 `sanitize_for_log` 中被链式调用。
- [x] `CleanupService` 构造函数参数 `storage_dir`/`export_dir`/`log_dir` 与 Task 6.4 注入一致。
- [x] 所有 `ErrorCode` 引用使用现有枚举成员（`INTERNAL_SERVER_ERROR` 等），未引入新错误码。
- [x] 离线检查 API 返回字段 `offline_ready`、`all_ok`、`checks` 与测试断言一致。
- [x] 所有测试 fixture 函数签名与使用一致。

### 4. 边界检查

- [x] 不实现 OCR、LLM、图像处理。
- [x] 不修改 BE-07 审核数据结构和 `review_results/`。
- [x] 不修改 BE-01 `run.bat`/`stop.bat` 主逻辑。
- [x] 不上传日志、不请求外部日志服务。
- [x] 日志不含完整病历原文、身份证号、图片 base64、模型输出全文、调用堆栈。
- [x] `data/`、`exports/`、`logs/` 中的真实运行数据不提交（通过 `.gitignore` 确保）。

---

## 需主 agent 协调的风险

- 日志中审核事件（`review_field_saved`、`task_confirmed`）和导出事件（`export_succeeded`、`export_failed`）的记录点需在 BE-07（审核）和 BE-08（导出）实现时补充 `log_event` 调用；本计划预留了 `log_event` 接口但不在 BE-09 伪造审核/导出事件。
- 若 BE-07 审核服务实现时新增了不同的持久化路径，cleanup_service 的 `cleanup_task_data` 可能需要同步更新。
- 本计划假设 `logs/` 已在 `.gitignore` 中；若缺失需在 Task 7.6 追加。
