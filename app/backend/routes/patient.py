"""患者档案路由。

本任务只提供创建、搜索、详情、改名四个入口;删除由 Task 6 在逻辑删除阶段补齐。
"""
from flask import Blueprint, current_app, request

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _safe_event

patient_bp = Blueprint("patient", __name__)


def _get_patient_service():
    return current_app.config["PATIENT_SERVICE"]


@patient_bp.route("/api/patients", methods=["POST"])
def create_patient():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="name 必须为非空字符串")
    service = _get_patient_service()
    record = service.create(name)
    _safe_event("patient_created", patient_id=record["patient_id"])
    return success(data=service.to_public(record), status=201)


@patient_bp.route("/api/patients", methods=["GET"])
def list_patients():
    query = request.args.get("query", "")
    service = _get_patient_service()
    items = [service.to_public(item) for item in service.list(query)]
    return success(data={"patients": items})


@patient_bp.route("/api/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id):
    service = _get_patient_service()
    return success(data=service.to_public(service.get(patient_id)))


@patient_bp.route("/api/patients/<patient_id>", methods=["PATCH"])
def update_patient(patient_id):
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not isinstance(name, str):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="name 必须为字符串")
    service = _get_patient_service()
    record = service.rename(patient_id, name)
    _safe_event("patient_renamed", patient_id=record["patient_id"])
    return success(data=service.to_public(record))
