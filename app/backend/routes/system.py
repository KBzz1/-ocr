# app/backend/routes/system.py
from flask import Blueprint, current_app
from ..responses import success

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/system/status")
def get_system_status():
    config = current_app.config.get("BACKEND_CONFIG", {})
    raw = current_app.config.get("LAN_ADDRESSES", [])
    lan_addresses = [a for a in raw if not a.startswith("127.0.0.1:")]
    return success(
        data={
            "status": "running",
            "version": config.get("version", "unknown"),
            "started_at": current_app.config.get("STARTED_AT", ""),
            "lan_addresses": lan_addresses,
        }
    )
