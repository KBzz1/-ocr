from flask import Blueprint, request

from ..responses import success
from . import _get_task_service

task_bp = Blueprint("task", __name__)


@task_bp.route("/api/tasks", methods=["POST"])
def create_task():
    base_url = request.host_url.rstrip("/")
    return success(data=_get_task_service().create_uploading_task(base_url=base_url), status=201)


@task_bp.route("/api/tasks", methods=["GET"])
def list_tasks():
    status = request.args.get("status")
    return success(data={"tasks": _get_task_service().list_tasks(status=status)})


@task_bp.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    return success(data=_get_task_service().get_task(task_id))


@task_bp.route("/api/tasks/<task_id>/process", methods=["POST"])
def process_task(task_id):
    return success(data=_get_task_service().process(task_id))


@task_bp.route("/api/tasks/<task_id>/retry", methods=["POST"])
def retry_task(task_id):
    return success(data=_get_task_service().retry(task_id))
