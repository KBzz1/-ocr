from flask import Blueprint, request, send_file

from ..errors import AppError, ErrorCode, abort
from ..responses import success
from . import _get_export_service, _safe_event

export_bp = Blueprint("export", __name__)


@export_bp.route("/api/tasks/<task_id>/export/check")
def export_check(task_id: str):
    svc = _get_export_service()
    result = svc.check(task_id)
    return success(data=result)


@export_bp.route("/api/tasks/<task_id>/export/json")
def export_json(task_id: str):
    svc = _get_export_service()
    try:
        info = svc.export_json(task_id)
    except AppError as exc:
        _safe_event("export_failed", level="ERROR", task_id=task_id, format="json", error_code=exc.code)
        raise
    _safe_event("export_succeeded", task_id=task_id, format="json", relative_path=info["relative_path"])
    return send_file(
        info["path"],
        mimetype="application/json",
        as_attachment=True,
        download_name=info["filename"],
    )


@export_bp.route("/api/tasks/<task_id>/export/excel")
def export_excel(task_id: str):
    svc = _get_export_service()
    try:
        info = svc.export_excel(task_id)
    except AppError as exc:
        _safe_event("export_failed", level="ERROR", task_id=task_id, format="excel", error_code=exc.code)
        raise
    _safe_event("export_succeeded", task_id=task_id, format="excel", relative_path=info["relative_path"])
    return send_file(
        info["path"],
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=info["filename"],
    )


@export_bp.route("/api/tasks/export/batch-zip", methods=["POST"])
def export_batch_zip():
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids")
    if not isinstance(task_ids, list) or not task_ids or not all(isinstance(item, str) and item for item in task_ids):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="task_ids 必须是非空字符串列表")

    svc = _get_export_service()
    try:
        info = svc.export_batch_zip(task_ids)
    except AppError as exc:
        _safe_event("export_failed", level="ERROR", format="batch_zip", error_code=exc.code)
        raise
    _safe_event("export_succeeded", format="batch_zip", relative_path=info["relative_path"], task_count=len(task_ids))
    return send_file(
        info["path"],
        mimetype="application/zip",
        as_attachment=True,
        download_name=info["filename"],
    )


@export_bp.route("/api/tasks/export/batch-excel/templates")
def batch_excel_templates():
    svc = _get_export_service()
    return success(data={"templates": svc.batch_excel_templates()})


@export_bp.route("/api/tasks/export/batch-excel", methods=["POST"])
def export_batch_excel():
    payload = request.get_json(silent=True) or {}
    document_type = payload.get("document_type")
    if not isinstance(document_type, str) or not document_type.strip():
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="document_type 必须为非空字符串")

    svc = _get_export_service()
    try:
        report = svc.export_batch_excel(document_type)
    except AppError as exc:
        _safe_event("export_failed", level="ERROR", format="batch_excel", error_code=exc.code, document_type=document_type)
        raise
    _safe_event(
        "export_succeeded",
        format="batch_excel",
        export_id=report["export_id"],
        exported_count=report["exported_count"],
        skipped_count=report["skipped_count"],
    )
    return success(data=report)


@export_bp.route("/api/tasks/export/batch-excel/<export_id>")
def download_batch_excel(export_id: str):
    svc = _get_export_service()
    filepath = svc.batch_excel_download_path(export_id)
    if filepath is None:
        abort(ErrorCode.REQUEST_NOT_FOUND, message="导出文件不存在或已失效")
    return send_file(
        filepath,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"batch-{export_id}.xlsx",
    )
