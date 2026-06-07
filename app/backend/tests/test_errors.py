from app.backend.errors import ErrorCode


def test_mvp_error_codes_include_upload_errors():
    assert ErrorCode.TASK_UPLOAD_CLOSED.code == "TASK_UPLOAD_CLOSED"
    assert ErrorCode.TASK_UPLOAD_CLOSED.http_status == 409
    assert ErrorCode.TASK_EMPTY.code == "TASK_EMPTY"
    assert ErrorCode.TASK_EMPTY.http_status == 400


def test_patient_error_codes_are_registered():
    assert ErrorCode.PATIENT_NOT_FOUND.code == "PATIENT_NOT_FOUND"
    assert ErrorCode.PATIENT_NOT_FOUND.http_status == 404
    assert ErrorCode.PATIENT_DELETED.code == "PATIENT_DELETED"
    assert ErrorCode.PATIENT_DELETED.http_status == 409


def test_session_and_quad_error_codes_are_not_public_contract():
    codes = {item.code for item in ErrorCode}
    assert "SESSION_NOT_FOUND" not in codes
    assert "SESSION_EXPIRED" not in codes
    assert "SESSION_LOCKED" not in codes
    assert "SESSION_EMPTY" not in codes
    assert "SESSION_CANCELLED" not in codes
    assert "SESSION_UNLOCK_NOT_ALLOWED" not in codes
    assert "INVALID_QUAD_POINTS" not in codes
