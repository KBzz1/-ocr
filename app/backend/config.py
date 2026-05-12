"""Backend settings loader.

`app/config/` stores YAML templates and local configuration files. This module
is backend code that loads, flattens, validates, and normalizes those settings.
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "version": "0.1.0",
    "bind_host": "0.0.0.0",
    "local_host": "127.0.0.1",
    "port": 8081,
    "data_dir": "./data",
    "log_dir": "./logs",
    "model_dir": "./models",
    "storage_dir": "./data",
    "export_dir": "./exports",
    "capture_session_ttl_minutes": 30,
    "max_upload_file_size_mb": 10,
    "min_quad_area_ratio": 0.01,
    "log_max_bytes": 10 * 1024 * 1024,
    "log_backup_count": 5,
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _deep_merge(base, override):
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

    sessions_config = raw.get("sessions", {})
    if "capture_session_ttl_minutes" in sessions_config:
        flattened["capture_session_ttl_minutes"] = sessions_config["capture_session_ttl_minutes"]

    upload_config = raw.get("upload", {})
    if "max_file_size_mb" in upload_config:
        flattened["max_upload_file_size_mb"] = upload_config["max_file_size_mb"]
    if "min_quad_area_ratio" in upload_config:
        flattened["min_quad_area_ratio"] = upload_config["min_quad_area_ratio"]

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

    for key in ("data_dir", "log_dir", "storage_dir", "export_dir"):
        path = config[key]
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            raise ValueError(f"路径不可写: {path}")

    ttl = config["capture_session_ttl_minutes"]
    if not isinstance(ttl, int) or ttl <= 0:
        raise ValueError(f"采集会话 TTL 必须为正整数，当前值: {ttl}")

    max_size = config.get("max_upload_file_size_mb")
    if not isinstance(max_size, int) or max_size <= 0:
        raise ValueError(f"max_upload_file_size_mb 必须为正整数，当前值: {max_size}")
    ratio = config.get("min_quad_area_ratio")
    if not isinstance(ratio, (int, float)) or not (0 < ratio < 1):
        raise ValueError(f"min_quad_area_ratio 必须在 (0, 1) 区间内，当前值: {ratio}")

    log_max_bytes = config.get("log_max_bytes")
    if not isinstance(log_max_bytes, int) or log_max_bytes <= 0:
        raise ValueError(f"log_max_bytes 必须为正整数，当前值: {log_max_bytes}")
    log_backup_count = config.get("log_backup_count")
    if not isinstance(log_backup_count, int) or log_backup_count < 0:
        raise ValueError(f"log_backup_count 必须为非负整数，当前值: {log_backup_count}")


def load_config(config_dir: str | None = None) -> dict:
    """加载配置，合并: 硬编码默认值 < default.yaml < local.yaml(可选)。"""
    merged = dict(DEFAULT_CONFIG)

    if config_dir is None:
        config_dir = os.path.join(PROJECT_ROOT, "app", "config")
    if not os.path.isdir(config_dir):
        logger.warning("配置文件目录 %s 不存在，使用默认配置", config_dir)
        result = _normalize_paths(merged)
        _validate_config(result)
        return result

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
