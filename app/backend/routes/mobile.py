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


def _sanitize_image(image: dict) -> dict:
    """只返回移动端需要的字段,不泄露 original_image_path 等本机路径。"""
    return {
        "page_id": image.get("page_id"),
        "task_id": image.get("task_id"),
        "page_no": image.get("page_no"),
        "preview_url": image.get("preview_url"),
        "image_width": image.get("image_width"),
        "image_height": image.get("image_height"),
        "uploaded_at": image.get("uploaded_at"),
    }


def _upload_status_payload(task: dict) -> dict:
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "page_count": task["page_count"],
        "images": [_sanitize_image(img) for img in task.get("images", [])],
        "document_type": task.get("document_type"),
        "document_type_label": task.get("document_type_label"),
        "schema_version": task.get("schema_version"),
    }


@mobile_bp.route("/api/mobile-upload/<task_id>", methods=["GET"])
def get_task_upload_status(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    return success(data=_upload_status_payload(task))


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


@mobile_bp.route("/api/mobile-upload/<task_id>/images/<page_id>", methods=["DELETE"])
def delete_task_image(task_id: str, page_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    removed, updated = task_service.remove_image(task_id, page_id)
    _page_service().delete_saved_page(removed)
    return success(data=_upload_status_payload(updated))


@mobile_bp.route("/api/mobile-upload/<task_id>/finish", methods=["POST"])
def finish_task_upload(task_id: str):
    task_service = _get_task_service()
    task = task_service.get_task(task_id)
    task_service.assert_upload_token(task, request.args.get("token"))
    return success(data=task_service.finish_upload(task_id))
