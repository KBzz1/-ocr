# app/backend/__init__.py
import socket
from datetime import datetime, timezone
from ipaddress import ip_address

from flask import Flask

from .config import load_config
from .errors import register_error_handlers


def _is_loopback_ipv4(address: str) -> bool:
    try:
        parsed = ip_address(address)
    except ValueError:
        return True
    return parsed.version == 4 and parsed.is_loopback


def _get_lan_addresses(port: int) -> list[str]:
    """返回候选局域网地址列表，排除回环地址。

    UDP connect 只让操作系统选择本机出站地址，不发送数据包，也不依赖 DNS。
    """
    addresses = []
    for target in ("10.255.255.255", "192.0.2.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 1))
                addr = sock.getsockname()[0]
            if not _is_loopback_ipv4(addr):
                addresses.append(f"{addr}:{port}")
        except OSError:
            continue

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

    from .storage.json_store import JsonStore
    from .services.session_service import SessionService

    store = JsonStore(config["storage_dir"])
    app.config["SESSION_SERVICE"] = SessionService(
        store=store,
        lan_addresses=app.config["LAN_ADDRESSES"],
        ttl_minutes=config["capture_session_ttl_minutes"],
    )

    from .services.file_validator import FileValidator
    from .services.page_service import PageService

    session_service = app.config["SESSION_SERVICE"]
    file_validator = FileValidator(
        max_size_mb=config["max_upload_file_size_mb"],
        base_dir="pages",
    )
    page_service = PageService(
        session_service=session_service,
        file_validator=file_validator,
        store=store,
        storage_dir=config["storage_dir"],
        min_quad_area_ratio=config["min_quad_area_ratio"],
    )
    app.config["PAGE_SERVICE"] = page_service

    from .services.task_service import TaskService
    app.config["TASK_SERVICE"] = TaskService(store=store)

    app.logger.warning("算法模块未配置")

    from .routes.system import system_bp
    app.register_blueprint(system_bp)

    from .routes.capture_session import capture_session_bp
    from .routes.mobile import mobile_bp
    app.register_blueprint(capture_session_bp)
    app.register_blueprint(mobile_bp)

    from .routes.task import task_bp
    app.register_blueprint(task_bp)

    return app
