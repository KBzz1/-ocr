import pytest
from app.backend.errors import (
    ErrorCode,
    AlgorithmErrorCode,
    AppError,
)


class TestErrorCode:
    def test_code_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.code == "SESSION_NOT_FOUND"
        assert ErrorCode.TASK_NOT_FOUND.code == "TASK_NOT_FOUND"
        assert ErrorCode.SESSION_EXPIRED.code == "SESSION_EXPIRED"
        assert ErrorCode.SESSION_EMPTY.code == "SESSION_EMPTY"

    def test_http_status_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.http_status == 404
        assert ErrorCode.SESSION_EXPIRED.http_status == 409
        assert ErrorCode.SESSION_EMPTY.http_status == 400
        assert ErrorCode.EXPORT_FAILED.http_status == 500

    def test_default_message_attribute(self):
        assert ErrorCode.SESSION_NOT_FOUND.default_message == "采集会话不存在"
        assert ErrorCode.SESSION_EMPTY.default_message == "采集会话没有已上传页面"
        assert ErrorCode.TASK_NOT_FOUND.default_message == "任务不存在"
        assert ErrorCode.INVALID_TASK_TRANSITION.default_message == "非法任务状态流转"

    def test_all_codes_defined(self):
        codes = {e.code for e in ErrorCode}
        assert "SESSION_NOT_FOUND" in codes
        assert "SESSION_EXPIRED" in codes
        assert "SESSION_LOCKED" in codes
        assert "SESSION_EMPTY" in codes
        assert "UNSUPPORTED_FILE_TYPE" in codes
        assert "FILE_TOO_LARGE" in codes
        assert "INVALID_QUAD_POINTS" in codes
        assert "TASK_NOT_FOUND" in codes
        assert "INVALID_TASK_TRANSITION" in codes
        assert "REVIEW_VALIDATION_FAILED" in codes
        assert "EXPORT_VALIDATION_FAILED" in codes
        assert "EXPORT_FAILED" in codes
        assert "REQUEST_NOT_FOUND" in codes
        assert "INTERNAL_SERVER_ERROR" in codes
        assert len(codes) == 14


class TestAlgorithmErrorCode:
    def test_member_values(self):
        assert AlgorithmErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.value == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert AlgorithmErrorCode.ALGORITHM_MODULE_FAILED.value == "ALGORITHM_MODULE_FAILED"
        assert AlgorithmErrorCode.ALGORITHM_CONTRACT_INVALID.value == "ALGORITHM_CONTRACT_INVALID"


class TestAppError:
    def test_with_default_message(self):
        err = AppError(ErrorCode.TASK_NOT_FOUND)
        assert err.code == "TASK_NOT_FOUND"
        assert err.message == "任务不存在"
        assert err.http_status == 404
        assert err.details == {}

    def test_with_custom_message(self):
        err = AppError(ErrorCode.TASK_NOT_FOUND, message="任务 task_001 不存在")
        assert err.message == "任务 task_001 不存在"
        assert err.code == "TASK_NOT_FOUND"

    def test_with_details(self):
        err = AppError(
            ErrorCode.INVALID_TASK_TRANSITION,
            details={"current": "created", "target": "exported"},
        )
        assert err.details == {"current": "created", "target": "exported"}

    def test_is_exception(self):
        err = AppError(ErrorCode.SESSION_NOT_FOUND)
        assert isinstance(err, Exception)

    def test_exception_args_contains_message(self):
        err = AppError(ErrorCode.TASK_NOT_FOUND)
        assert err.args == ("任务不存在",)


class TestAbort:
    def test_abort_raises_app_error(self):
        from app.backend.errors import abort

        with pytest.raises(AppError) as exc_info:
            abort(ErrorCode.SESSION_EXPIRED, message="会话已过期")
        assert exc_info.value.code == "SESSION_EXPIRED"
        assert exc_info.value.message == "会话已过期"
