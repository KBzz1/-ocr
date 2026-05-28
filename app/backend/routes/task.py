from flask import Blueprint, current_app, request, send_file

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _get_task_service

task_bp = Blueprint("task", __name__)


def _mobile_base_url():
    public_base_url = (current_app.config.get("BACKEND_CONFIG") or {}).get("public_base_url")
    if public_base_url:
        return public_base_url.rstrip("/")
    lan_addresses = current_app.config.get("LAN_ADDRESSES") or []
    return f"{request.scheme}://{lan_addresses[0]}" if lan_addresses else request.host_url.rstrip("/")


@task_bp.route("/api/tasks", methods=["POST"])
def create_task():
    return success(data=_get_task_service().create_uploading_task(base_url=_mobile_base_url()), status=201)


@task_bp.route("/api/tasks", methods=["GET"])
def list_tasks():
    status = request.args.get("status")
    return success(data={"tasks": _get_task_service().list_tasks(status=status, base_url=_mobile_base_url())})


@task_bp.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    return success(data=_get_task_service().get_task(task_id))


@task_bp.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    task = _get_task_service().delete_task(task_id)
    current_app.config["CLEANUP_SERVICE"].cleanup_task(task_id, confirm=True)
    return success(data={"task_id": task_id, "deleted": True})


@task_bp.route("/api/tasks/<task_id>/process", methods=["POST"])
def process_task(task_id):
    return success(data=_get_task_service().process(task_id))


@task_bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
def retry_task(task_id):
    return success(data=_get_task_service().retry(task_id))


@task_bp.route("/api/tasks/<task_id>/cancel-processing", methods=["POST"])
def cancel_processing(task_id):
    return success(data=_get_task_service().cancel_processing(task_id))


@task_bp.route("/api/tasks/<task_id>/rename", methods=["PATCH"])
def rename_task(task_id):
    body = request.get_json(silent=True) or {}
    display_name = body.get("display_name", "").strip()
    if not display_name:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="display_name 不能为空")
    return success(data=_get_task_service().rename_task(task_id, display_name))


@task_bp.route("/api/tasks/<task_id>/images/<page_id>", methods=["GET"])
def serve_task_image(task_id, page_id):
    task = _get_task_service().get_task(task_id)
    for img in task.get("images", []):
        if img.get("page_id") == page_id:
            path = img.get("original_image_path")
            if path:
                return send_file(path)
    raise AppError(ErrorCode.REQUEST_NOT_FOUND, message="图片不存在")
