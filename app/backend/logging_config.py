"""日志配置：热日志（backend.log）与冷日志（access.log, debug.log, boot.log）分离。

热日志 = 当前会话的关键信息，文件小，适合快速扫描。
冷日志 = HTTP 访问记录、DEBUG 诊断、LLM 原始返回等历史细节。
"""

import logging
import os
import shutil
from datetime import datetime
from logging.handlers import RotatingFileHandler

HOT_LOG_MAX_BYTES = 512 * 1024      # 512 KB
COLD_LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
BACKUP_COUNT = 3


def setup_logging(log_dir: str) -> None:
    """配置日志路由。

    热日志:
      backend.log  — WARNING 及以上，包含业务错误、契约违规、模块异常等

    冷日志:
      access.log  — Werkzeug HTTP 请求日志（前端轮询噪音隔离在此）
      debug.log   — DEBUG 及以上，含 LLM 原始返回、字段规范化细节
      boot.log    — 进程 stdout/stderr 兜底（替代 shell 重定向）
    """
    os.makedirs(log_dir, exist_ok=True)

    _archive_old_hot_log(log_dir)
    _clear_stale_handlers()

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 热日志: WARNING+
    root.addHandler(_make_handler(
        os.path.join(log_dir, "backend.log"),
        logging.WARNING,
        HOT_LOG_MAX_BYTES,
    ))

    # 冷日志: DEBUG+（诊断详情）
    root.addHandler(_make_handler(
        os.path.join(log_dir, "debug.log"),
        logging.DEBUG,
        COLD_LOG_MAX_BYTES,
    ))

    # Werkzeug access → 独立的冷日志
    _isolate_werkzeug(log_dir)

    # Flask app logger 继承 root 配置即可
    logging.getLogger("app.backend").setLevel(logging.DEBUG)


def _archive_old_hot_log(log_dir: str) -> None:
    """将旧的 backend.log 归档到 archive/YYYY-MM/ 目录。"""
    src = os.path.join(log_dir, "backend.log")
    if not os.path.isfile(src) or os.path.getsize(src) == 0:
        return
    archive_dir = os.path.join(log_dir, "archive", datetime.now().strftime("%Y-%m"))
    os.makedirs(archive_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(archive_dir, f"backend.{ts}.log")
    shutil.move(src, dst)


def _clear_stale_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        handler.close()
        root.removeHandler(handler)


def _make_handler(path: str, level: int, max_bytes: int) -> logging.Handler:
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname).4s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    return handler


def _isolate_werkzeug(log_dir: str) -> None:
    """将 Werkzeug 的 HTTP 访问日志重定向到 access.log，不污染热日志。"""
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.handlers.clear()
    werkzeug_logger.propagate = False
    werkzeug_logger.addHandler(_make_handler(
        os.path.join(log_dir, "access.log"),
        logging.INFO,
        COLD_LOG_MAX_BYTES,
    ))
