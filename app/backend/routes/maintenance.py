from flask import Blueprint, current_app, request

from ..responses import success

maintenance_bp = Blueprint("maintenance", __name__)


@maintenance_bp.route("/api/maintenance/offline-check", methods=["GET"])
def offline_check():
    return success(data=current_app.config["OFFLINE_CHECK_SERVICE"].run())


@maintenance_bp.route("/api/maintenance/tasks/<task_id>/cleanup-plan", methods=["GET"])
def cleanup_plan(task_id):
    return success(data=current_app.config["CLEANUP_SERVICE"].plan_task_cleanup(task_id))


@maintenance_bp.route("/api/maintenance/tasks/<task_id>/cleanup", methods=["POST"])
def cleanup_task(task_id):
    payload = request.get_json(silent=True) or {}
    return success(data=current_app.config["CLEANUP_SERVICE"].cleanup_task(task_id, confirm=payload.get("confirm") is True))
