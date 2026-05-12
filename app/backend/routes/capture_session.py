from flask import Blueprint, current_app, request

from ..responses import success

capture_session_bp = Blueprint("capture_session", __name__)


def _service():
    return current_app.config["SESSION_SERVICE"]


@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    session = _service().create()
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "created_at": session["created_at"],
            "expires_at": session["expires_at"],
            "qr_code_url": session["qr_code_url"],
            "page_count": session["page_count"],
        },
        status=201,
    )


@capture_session_bp.route("/api/capture-sessions/<session_id>", methods=["GET"])
def get_session(session_id):
    return success(data=_service().get(session_id))


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages", methods=["POST"])
def add_page(session_id):
    return success(data=_service().add_page(session_id), status=201)


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages/<page_id>", methods=["DELETE"])
def delete_page(session_id, page_id):
    return success(data=_service().delete_page(session_id, page_id))


@capture_session_bp.route("/api/capture-sessions/<session_id>/pages/order", methods=["PUT"])
def reorder_pages(session_id):
    payload = request.get_json(silent=True) or {}
    page_ids = payload.get("page_ids", [])
    return success(data=_service().reorder_pages(session_id, page_ids))
