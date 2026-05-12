from flask import current_app


def _get_session_service():
    return current_app.config["SESSION_SERVICE"]
