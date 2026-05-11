import json
import pytest
from app.backend.responses import success, error_response
from app.backend.errors import AppError, ErrorCode


class TestSuccess:
    def test_success_with_none_data(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success()
            data = json.loads(resp.get_data(as_text=True))
            assert data == {"success": True, "data": None}
            assert resp.status_code == 200

    def test_success_with_data(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success(data={"status": "running"})
            data = json.loads(resp.get_data(as_text=True))
            assert data == {"success": True, "data": {"status": "running"}}

    def test_success_custom_status(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success(status=201)
            assert resp.status_code == 201

    def test_success_content_type(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            resp = success()
            assert resp.content_type == "application/json"


class TestErrorResponse:
    def test_error_response_structure(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.TASK_NOT_FOUND)
            resp = error_response(err)
            data = json.loads(resp.get_data(as_text=True))
            assert data == {
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": "任务不存在",
                    "details": {},
                }
            }

    def test_error_response_http_status(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.SESSION_EXPIRED)
            resp = error_response(err)
            assert resp.status_code == 409

    def test_error_response_with_details(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": "created", "target": "exported"},
            )
            resp = error_response(err)
            data = json.loads(resp.get_data(as_text=True))
            assert data["error"]["details"] == {"current": "created", "target": "exported"}

    def test_error_response_content_type(self):
        from flask import Flask
        app = Flask(__name__)
        with app.test_request_context():
            err = AppError(ErrorCode.TASK_NOT_FOUND)
            resp = error_response(err)
            assert resp.content_type == "application/json"
