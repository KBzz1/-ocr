from flask import current_app


def _get_session_service():
    return current_app.config["SESSION_SERVICE"]


def _get_task_service():
    return current_app.config["TASK_SERVICE"]
