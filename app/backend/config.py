"""Backend settings loader.

`app/config/` stores YAML templates and local configuration files. This module
is backend code that loads, flattens, validates, and normalizes those settings.
"""

import os
import yaml
import logging
import sys
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "version": "0.1.0",
    "bind_host": "0.0.0.0",
    "local_host": "127.0.0.1",
    "port": 8081,
    "public_base_url": None,
    "data_dir": "./data",
    "log_dir": "./logs",
    "model_dir": "./models",
    "storage_dir": "./data",
    "export_dir": "./exports",
    "static_dir": "./app/frontend/dist",
    "capture_session_ttl_minutes": 30,
    "max_upload_file_size_mb": 10,
    "min_quad_area_ratio": 0.01,
    "log_max_bytes": 10 * 1024 * 1024,
    "log_backup_count": 5,
    "enable_copd_extractor": False,
    "llm_model_path": "./models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
    "llm_context_tokens": 8192,
    "llm_max_tokens": 1024,
    "llm_extraction_batch_size": 25,
    "llm_enable_verification": True,
    "enable_local_ocr": False,
    "local_ocr_python_executable": sys.executable,
    "local_ocr_script_path": "./app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py",
    "local_ocr_work_root": None,
    "local_ocr_max_new_tokens": 1024,
    "local_ocr_timeout_seconds": 180,
    "local_ocr_device": None,
    "local_ocr_max_pixels": 501760,
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
    if "public_base_url" in server_config:
        flattened["public_base_url"] = server_config["public_base_url"]
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
    if "static_dir" in paths_config:
        flattened["static_dir"] = paths_config["static_dir"]

    sessions_config = raw.get("sessions", {})
    if "capture_session_ttl_minutes" in sessions_config:
        flattened["capture_session_ttl_minutes"] = sessions_config["capture_session_ttl_minutes"]

    upload_config = raw.get("upload", {})
    if "max_file_size_mb" in upload_config:
        flattened["max_upload_file_size_mb"] = upload_config["max_file_size_mb"]
    if "min_quad_area_ratio" in upload_config:
        flattened["min_quad_area_ratio"] = upload_config["min_quad_area_ratio"]

    algorithms_config = raw.get("algorithms", {})
    if "enable_copd_extractor" in algorithms_config:
        flattened["enable_copd_extractor"] = algorithms_config["enable_copd_extractor"]
    if "llm_model_path" in algorithms_config:
        flattened["llm_model_path"] = algorithms_config["llm_model_path"]
    if "llm_context_tokens" in algorithms_config:
        flattened["llm_context_tokens"] = algorithms_config["llm_context_tokens"]
    if "llm_max_tokens" in algorithms_config:
        flattened["llm_max_tokens"] = algorithms_config["llm_max_tokens"]
    if "llm_extraction_batch_size" in algorithms_config:
        flattened["llm_extraction_batch_size"] = algorithms_config["llm_extraction_batch_size"]
    if "llm_enable_verification" in algorithms_config:
        flattened["llm_enable_verification"] = algorithms_config["llm_enable_verification"]
    if "enable_local_ocr" in algorithms_config:
        flattened["enable_local_ocr"] = algorithms_config["enable_local_ocr"]
    if "local_ocr_python_executable" in algorithms_config:
        flattened["local_ocr_python_executable"] = algorithms_config["local_ocr_python_executable"]
    if "local_ocr_script_path" in algorithms_config:
        flattened["local_ocr_script_path"] = algorithms_config["local_ocr_script_path"]
    if "local_ocr_work_root" in algorithms_config:
        flattened["local_ocr_work_root"] = algorithms_config["local_ocr_work_root"]
    if "local_ocr_max_new_tokens" in algorithms_config:
        flattened["local_ocr_max_new_tokens"] = algorithms_config["local_ocr_max_new_tokens"]
    if "local_ocr_timeout_seconds" in algorithms_config:
        flattened["local_ocr_timeout_seconds"] = algorithms_config["local_ocr_timeout_seconds"]
    if "local_ocr_device" in algorithms_config:
        flattened["local_ocr_device"] = algorithms_config["local_ocr_device"]
    if "local_ocr_max_pixels" in algorithms_config:
        flattened["local_ocr_max_pixels"] = algorithms_config["local_ocr_max_pixels"]

    return flattened


def _normalize_paths(config: dict) -> dict:
    """将相对路径转为基于 PROJECT_ROOT 的绝对路径。"""
    for key in (
        "data_dir",
        "log_dir",
        "model_dir",
        "storage_dir",
        "export_dir",
        "static_dir",
        "llm_model_path",
        "local_ocr_script_path",
        "local_ocr_work_root",
    ):
        path = config.get(key)
        if path and not os.path.isabs(path):
            path = os.path.join(PROJECT_ROOT, path)
        if path:
            config[key] = os.path.normpath(path)
    return config


def _validate_config(config: dict):
    """校验 port 范围和路径可写性。"""
    port = config["port"]
    if not isinstance(port, int) or port < 1024 or port > 65535:
        raise ValueError(f"端口号必须在 1024-65535 之间，当前值: {port}")

    public_base_url = config.get("public_base_url")
    if public_base_url is not None:
        parsed_public_base_url = urlparse(public_base_url) if isinstance(public_base_url, str) else None
        if (
            not isinstance(public_base_url, str)
            or parsed_public_base_url is None
            or parsed_public_base_url.scheme not in {"http", "https"}
            or not parsed_public_base_url.hostname
            or any(char.isspace() for char in public_base_url)
        ):
            raise ValueError(f"public_base_url 必须是 http(s) URL，当前值: {public_base_url}")

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

    ocr_timeout = config.get("local_ocr_timeout_seconds")
    if not isinstance(ocr_timeout, int) or ocr_timeout <= 0:
        raise ValueError(f"local_ocr_timeout_seconds 必须为正整数，当前值: {ocr_timeout}")

    for key in ("local_ocr_max_new_tokens", "local_ocr_max_pixels"):
        value = config.get(key)
        if value is not None and (not isinstance(value, int) or value <= 0):
            raise ValueError(f"{key} 必须为空或正整数，当前值: {value}")

    extraction_batch_size = config.get("llm_extraction_batch_size")
    if not isinstance(extraction_batch_size, int) or extraction_batch_size <= 0:
        raise ValueError(f"llm_extraction_batch_size 必须为正整数，当前值: {extraction_batch_size}")
    if not isinstance(config.get("llm_enable_verification"), bool):
        raise ValueError(f"llm_enable_verification 必须为布尔值，当前值: {config.get('llm_enable_verification')}")


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

    public_base_url = os.environ.get("MANZUFEI_PUBLIC_BASE_URL", "").strip()
    if public_base_url:
        merged["public_base_url"] = public_base_url

    result = _normalize_paths(merged)
    _validate_config(result)
    return result
