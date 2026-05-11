# app/backend/routes/system.py
from ipaddress import ip_address

from flask import Blueprint, current_app
from ..responses import success

system_bp = Blueprint("system", __name__)


def _is_loopback_address(value: str) -> bool:
    host = value.rsplit(":", 1)[0]
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return True


@system_bp.route("/api/system/status")
def get_system_status():
    config = current_app.config.get("BACKEND_CONFIG", {})
    raw = current_app.config.get("LAN_ADDRESSES", [])
    lan_addresses = [a for a in raw if not _is_loopback_address(a)]
    return success(
        data={
            "status": "running",
            "version": config.get("version", "unknown"),
            "started_at": current_app.config.get("STARTED_AT", ""),
            "lan_addresses": lan_addresses,
        }
    )
