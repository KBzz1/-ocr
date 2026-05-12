from flask import Blueprint, current_app

from ..responses import success

mobile_bp = Blueprint("mobile", __name__)


def _service():
    return current_app.config["SESSION_SERVICE"]


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    session = _service().finish(session_id)
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "locked_at": session["locked_at"],
            "task_id": session["task_id"],
        }
    )
