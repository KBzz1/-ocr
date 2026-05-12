from flask import current_app


def _get_session_service():
    return current_app.config["SESSION_SERVICE"]


def _get_task_service():
    return current_app.config["TASK_SERVICE"]


def _get_review_service():
    return current_app.config["REVIEW_SERVICE"]


def _safe_event(event, level="INFO", **payload):
    """安全写入事件日志，日志写入失败不中断业务。"""
    try:
        log = current_app.config.get("LOCAL_EVENT_LOG")
        if log is not None:
            log.safe_write(event, level=level, **payload)
    except RuntimeError:
        pass
