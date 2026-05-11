# app/backend/__init__.py
import socket
from datetime import datetime, timezone

from flask import Flask

from .config import load_config
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
