from flask import Blueprint, request

from ..responses import success
from . import _get_review_service, _get_task_service

review_bp = Blueprint("review", __name__)


@review_bp.route("/api/tasks/<task_id>/review", methods=["GET"])
def get_review(task_id):
    task = _get_task_service().get_task(task_id)
    review = _get_review_service().get_or_init(task_id)
    return success(data={"task_id": task_id, "status": task["status"], "review_result": review})


@review_bp.route("/api/tasks/<task_id>/review/fields/<field_key>", methods=["PATCH"])
def update_review_field(task_id, field_key):
    payload = request.get_json(silent=True) or {}
    review = _get_review_service().update_field(task_id, field_key, payload)
    return success(data={"task_id": task_id, "review_result": review})


@review_bp.route("/api/tasks/<task_id>/review/confirm", methods=["POST"])
def confirm_review(task_id):
    task = _get_review_service().confirm(task_id)
    return success(data=task)
