from flask import Blueprint, current_app, request, send_file

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _get_reextract_job_registry, _get_reextraction_service, _get_task_service, _safe_event

task_bp = Blueprint("task", __name__)


def _mobile_base_url():
    public_base_url = (current_app.config.get("BACKEND_CONFIG") or {}).get("public_base_url")
    if public_base_url:
        return public_base_url.rstrip("/")
    lan_addresses = current_app.config.get("LAN_ADDRESSES") or []
    return f"{request.scheme}://{lan_addresses[0]}" if lan_addresses else request.host_url.rstrip("/")


@task_bp.route("/api/tasks", methods=["POST"])
def create_task():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="请求体必须为 JSON 对象")
    return success(
        data=_get_task_service().create_uploading_task(
            base_url=_mobile_base_url(),
            patient_id=body.get("patient_id"),
            document_type=body.get("document_type"),
            record_date=body.get("record_date"),
            record_time=body.get("record_time"),
        ),
        status=201,
    )


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


@task_bp.route("/api/tasks/<task_id>/reextract", methods=["POST"])
def reextract_task(task_id):
    registry = _get_reextract_job_registry()
    cancellation_token = registry.register(task_id)
    try:
        result = _get_reextraction_service().reextract(task_id, cancellation_token=cancellation_token)
    except AppError as exc:
        if exc.code == ErrorCode.REEXTRACTION_CANCELLED.code:
            _safe_event(
                "task_reextract_cancelled",
                task_id=task_id,
            )
        raise
    finally:
        registry.unregister(task_id)
    _safe_event(
        "task_reextracted",
        task_id=task_id,
        source=result.get("source"),
        schema_version=result.get("schema_version"),
        prompt_version=result.get("prompt_version"),
        candidate_count=result.get("candidate_count"),
    )
    return success(data=result)


@task_bp.route("/api/tasks/<task_id>/cancel-reextract", methods=["POST"])
def cancel_reextract_task(task_id):
    # 404 if task missing, 409 if no in-flight job — keep semantics parallel
    # to /cancel-processing for the user-visible contract.
    _get_task_service().get_task(task_id)
    registry = _get_reextract_job_registry()
    cancelled = registry.cancel(task_id)
    if not cancelled:
        raise AppError(
            ErrorCode.REEXTRACTION_VALIDATION_FAILED,
            message="当前没有正在进行的重新抽取任务",
            details={"reason": "no_inflight_reextract"},
        )
    return success(data={"task_id": task_id, "cancelled": True})


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


@task_bp.route("/api/tasks/<task_id>/metadata", methods=["PATCH"])
def update_task_metadata(task_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="请求体必须为 JSON 对象")
    allowed = {"patient_id", "document_type", "record_date", "record_time"}
    provided = {key: body[key] for key in allowed if key in body}
    if not provided:
        raise AppError(
            ErrorCode.INVALID_REQUEST_PARAMS,
            message="至少提供一项可更新字段",
        )
    return success(
        data=_get_task_service().update_metadata(
            task_id,
            reextract_registry=_get_reextract_job_registry(),
            **provided,
        )
    )


@task_bp.route("/api/tasks/<task_id>/images/<page_id>", methods=["GET"])
def serve_task_image(task_id, page_id):
    task = _get_task_service().get_task(task_id)
    for img in task.get("images", []):
        if img.get("page_id") == page_id:
            path = img.get("original_image_path")
            if path:
                return send_file(path)
    raise AppError(ErrorCode.REQUEST_NOT_FOUND, message="图片不存在")
