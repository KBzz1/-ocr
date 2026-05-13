from flask import Blueprint, send_file

from ..errors import AppError
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
