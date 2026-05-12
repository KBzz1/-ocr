from flask import Blueprint

from ..responses import success
from . import _get_session_service

mobile_bp = Blueprint("mobile", __name__)


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    session = _get_session_service().finish(session_id)
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "locked_at": session["locked_at"],
            "task_id": session["task_id"],
        }
    )
