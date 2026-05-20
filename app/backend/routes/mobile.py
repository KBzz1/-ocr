from flask import Blueprint, current_app, request

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _get_task_service

mobile_bp = Blueprint("mobile", __name__)


def _page_service():
    return current_app.config["PAGE_SERVICE"]


def _parse_optional_dimensions():
    width = request.form.get("image_width")
    height = request.form.get("image_height")
    try:
        return int(width) if width else None, int(height) if height else None
    except (TypeError, ValueError):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 和 image_height 必须为整数")


@mobile_bp.route("/api/mobile-upload/<task_id>", methods=["GET"])
def get_task_upload_status(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    return success(
        data={
            "task_id": task["task_id"],
            "status": task["status"],
            "page_count": task["page_count"],
            "images": task["images"],
        }
    )


@mobile_bp.route("/api/mobile-upload/<task_id>/images", methods=["POST"])
def upload_task_image(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    if task["status"] != "uploading":
        raise AppError(ErrorCode.TASK_UPLOAD_CLOSED)
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_width, image_height = _parse_optional_dimensions()
    page = _page_service().save_task_image(
        task=task,
        image_data=request.files["image"].read(),
        image_width=image_width,
        image_height=image_height,
    )
    return success(data=task_service.add_image(task_id, page), status=201)


@mobile_bp.route("/api/mobile-upload/<task_id>/finish", methods=["POST"])
def finish_task_upload(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    return success(data=task_service.finish_upload(task_id))
