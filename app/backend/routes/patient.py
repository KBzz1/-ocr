"""患者档案路由。

本任务只提供创建、搜索、详情、改名四个入口;删除由 Task 6 在逻辑删除阶段补齐。
"""
from flask import Blueprint, current_app, request

from ..errors import AppError, ErrorCode
from ..responses import success
from ..enums import TaskStatus
from . import _get_patient_query_service, _get_task_service, _safe_event

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
    record = service.create(
        name,
        gender=body.get("gender"),
        age=body.get("age"),
    )
    _safe_event("patient_created", patient_id=record["patient_id"])
    return success(data=service.to_public(record), status=201)


@patient_bp.route("/api/patients", methods=["GET"])
def list_patients():
    query = request.args.get("query", "")
    items = _get_patient_query_service().list_patients(query)
    return success(data={"patients": items})


@patient_bp.route("/api/patients/<patient_id>", methods=["GET"])
def get_patient(patient_id):
    service = _get_patient_service()
    return success(data=service.to_public(service.get(patient_id)))


@patient_bp.route("/api/patients/<patient_id>/records", methods=["GET"])
def get_patient_records(patient_id):
    return success(data=_get_patient_query_service().get_detail(patient_id))


@patient_bp.route("/api/patients/<patient_id>", methods=["PATCH"])
def update_patient(patient_id):
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not isinstance(name, str):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="name 必须为字符串")
    service = _get_patient_service()
    record = service.rename(patient_id, name)
    service.refresh_snapshots_for_active_tasks(patient_id)
    _safe_event("patient_renamed", patient_id=record["patient_id"])
    return success(data=service.to_public(record))


@patient_bp.route("/api/patients/<patient_id>/demographics", methods=["PATCH"])
def update_patient_demographics(patient_id: str):
    """局部更新患者人口学字段（gender/age）。

    - 字段缺失表示不更新；显式空字符串/0 表示清空
    - 校验失败返回 INVALID_REQUEST_PARAMS
    - 不触发姓名历史与 patient_snapshot 刷新
    """
    body = request.get_json(silent=True) or {}
    service = _get_patient_service()
    record = service.update_demographics(
        patient_id,
        gender=body.get("gender") if "gender" in body else None,
        age=body.get("age") if "age" in body else None,
    )
    _safe_event(
        "patient_demographics_updated",
        patient_id=record["patient_id"],
    )
    return success(data=service.to_public(record))


@patient_bp.route("/api/patients/<patient_id>", methods=["DELETE"])
def delete_patient(patient_id):
    """逻辑删除患者。

    - 默认 delete_tasks=false:只标记患者已删除,任务保留
    - delete_tasks=true:同时逻辑删除关联任务
    - 含 processing 任务且 delete_tasks=true 时返回 INVALID_TASK_TRANSITION
    """
    raw = request.args.get("delete_tasks", "false")
    if raw == "true":
        delete_tasks = True
    elif raw == "false":
        delete_tasks = False
    else:
        raise AppError(
            ErrorCode.INVALID_REQUEST_PARAMS,
            message="delete_tasks 必须为 'true' 或 'false'",
        )

    service = _get_patient_service()
    patient = service.get(patient_id, include_deleted=True)

    deleted_task_ids: set[str] = set()
    if delete_tasks:
        task_service = _get_task_service()
        tasks_to_delete = task_service.list_for_patient(patient_id)
        for task in tasks_to_delete:
            if task["status"] == TaskStatus.PROCESSING.value:
                raise AppError(
                    ErrorCode.INVALID_TASK_TRANSITION,
                    details={"current": task["status"], "target": "deleted"},
                )
        for task in tasks_to_delete:
            task_service.delete_task(task["task_id"])
            deleted_task_ids.add(task["task_id"])
        # 所有关联任务删除成功后再标记患者删除,避免中途失败留下半删除患者。
        record = service.mark_deleted(patient_id)
    else:
        # 仅删除患者时,只对仍指向该患者且未删除的任务刷新 patient_snapshot
        record = service.mark_deleted(patient_id)
        service.refresh_snapshots_for_active_tasks(patient_id)

    _safe_event(
        "patient_deleted",
        patient_id=patient_id,
        delete_tasks=delete_tasks,
        task_count=len(deleted_task_ids),
    )
    return success(
        data={
            "patient_id": patient_id,
            "deleted": True,
            "tasks_deleted": delete_tasks,
            "deleted_task_count": len(deleted_task_ids),
        }
    )
