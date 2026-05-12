from flask import Blueprint, current_app, request

from ..errors import AppError, ErrorCode
from ..responses import success

mobile_bp = Blueprint("mobile", __name__)


def _safe_event(event, level="INFO", **payload):
    log = current_app.config.get("LOCAL_EVENT_LOG")
    if log is not None:
        log.safe_write(event, level=level, **payload)


def _service():
    return current_app.config["SESSION_SERVICE"]


def _page_service():
    return current_app.config["PAGE_SERVICE"]


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    session = _service().finish(session_id)
    _safe_event(
        "session_finished",
        session_id=session_id,
        task_id=session["task_id"],
        page_count=len(session.get("pages", [])),
    )
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "locked_at": session["locked_at"],
            "task_id": session["task_id"],
        }
    )


@mobile_bp.route("/api/mobile/<session_id>/pages", methods=["POST"])
def upload_page(session_id: str):
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_file = request.files["image"]
    image_data = image_file.read()

    image_width_str = request.form.get("image_width")
    image_height_str = request.form.get("image_height")
    if not image_width_str or not image_height_str:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image_width 或 image_height")

    try:
        image_width = int(image_width_str)
        image_height = int(image_height_str)
    except (ValueError, TypeError):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 和 image_height 必须为整数")

    quad_points_raw = request.form.get("quad_points")

    updated = _service().add_page(session_id, upload_ref=None)
    page = updated["pages"][-1]

    result = _page_service().save(
        session_id=session_id,
        page_id=page["page_id"],
        page_no=page["page_no"],
        image_data=image_data,
        image_width=image_width,
        image_height=image_height,
        quad_points_raw=quad_points_raw,
    )

    _safe_event(
        "page_uploaded",
        session_id=session_id,
        page_id=result["page_id"],
        image_width=result.get("image_width"),
        image_height=result.get("image_height"),
    )
    return success(data=result, status=201)
