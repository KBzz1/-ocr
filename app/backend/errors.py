from enum import Enum


class ErrorCode(Enum):
    REQUEST_NOT_FOUND = ("REQUEST_NOT_FOUND", 404, "请求路径不存在")
    INTERNAL_SERVER_ERROR = ("INTERNAL_SERVER_ERROR", 500, "服务器内部错误")
    SESSION_NOT_FOUND = ("SESSION_NOT_FOUND", 404, "采集会话不存在")
    SESSION_EXPIRED = ("SESSION_EXPIRED", 409, "采集会话已过期")
    SESSION_LOCKED = ("SESSION_LOCKED", 409, "采集会话已完成采集，禁止编辑")
    SESSION_EMPTY = ("SESSION_EMPTY", 400, "采集会话没有已上传页面")
    UNSUPPORTED_FILE_TYPE = ("UNSUPPORTED_FILE_TYPE", 400, "不支持的文件类型")
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", 400, "文件超过大小限制")
    INVALID_REQUEST_PARAMS = ("INVALID_REQUEST_PARAMS", 400, "请求参数缺失、类型错误、格式错误或取值非法")
    INVALID_QUAD_POINTS = ("INVALID_QUAD_POINTS", 400, "框选坐标格式非法")
    TASK_NOT_FOUND = ("TASK_NOT_FOUND", 404, "任务不存在")
    ALGORITHM_MODULE_NOT_CONFIGURED = ("ALGORITHM_MODULE_NOT_CONFIGURED", 500, "算法模块未配置")
    ALGORITHM_MODULE_FAILED = ("ALGORITHM_MODULE_FAILED", 500, "外部算法模块异常")
    ALGORITHM_CONTRACT_INVALID = ("ALGORITHM_CONTRACT_INVALID", 500, "外部算法模块返回结构不符合契约")
    INVALID_TASK_TRANSITION = ("INVALID_TASK_TRANSITION", 400, "非法任务状态流转")
    REVIEW_VALIDATION_FAILED = ("REVIEW_VALIDATION_FAILED", 400, "审核确认校验失败")
    SESSION_CANCELLED = ("SESSION_CANCELLED", 409, "采集会话已取消")
    SESSION_UNLOCK_NOT_ALLOWED = ("SESSION_UNLOCK_NOT_ALLOWED", 409, "当前任务状态不允许修订采集")
    EXPORT_VALIDATION_FAILED = ("EXPORT_VALIDATION_FAILED", 400, "导出请求非法或任务状态不允许导出")
    EXPORT_FAILED = ("EXPORT_FAILED", 500, "导出文件写入失败")

    @property
    def code(self):
        return self.value[0]

    @property
    def http_status(self):
        return self.value[1]

    @property
    def default_message(self):
        return self.value[2]


class AlgorithmErrorCode(Enum):
    ALGORITHM_MODULE_NOT_CONFIGURED = "ALGORITHM_MODULE_NOT_CONFIGURED"
    ALGORITHM_MODULE_FAILED = "ALGORITHM_MODULE_FAILED"
    ALGORITHM_CONTRACT_INVALID = "ALGORITHM_CONTRACT_INVALID"


class AppError(Exception):
    def __init__(self, error_code: ErrorCode, message=None, details=None):
        resolved_message = message or error_code.default_message
        super().__init__(resolved_message)
        self.code = error_code.code
        self.message = resolved_message
        self.http_status = error_code.http_status
        self.details = details or {}

    def __str__(self):
        return f"[{self.code}] {self.message}"


def abort(error_code: ErrorCode, message=None, details=None):
    raise AppError(error_code, message=message, details=details)


def register_error_handlers(app):
    from flask import jsonify
    from werkzeug.exceptions import HTTPException as WerkzeugHTTPException

    from .responses import error_response

    @app.errorhandler(AppError)
    def handle_app_error(error):
        return error_response(error)

    @app.errorhandler(WerkzeugHTTPException)
    def handle_http_exception(error):
        if error.code == 404:
            app_error = AppError(ErrorCode.REQUEST_NOT_FOUND)
            return error_response(app_error)
        return jsonify({
            "error": {
                "code": ErrorCode.INTERNAL_SERVER_ERROR.code,
                "message": error.description or str(error),
                "details": {},
            }
        }), error.code

    @app.errorhandler(Exception)
    def handle_unexpected(error):
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Unexpected backend error: %s", type(error).__name__)
        return error_response(AppError(ErrorCode.INTERNAL_SERVER_ERROR))
