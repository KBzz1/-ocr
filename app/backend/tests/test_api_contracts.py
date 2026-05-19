"""API 契约回归测试：MVP 公开入口和移除的旧采集会话入口。"""
import socket

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client


def test_success_responses_use_success_data_shape(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert "data" in body


def test_error_responses_use_error_shape_without_traceback(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/tasks/no-such-task")

    assert response.status_code == 404
    body = response.get_json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]
    assert "details" in body["error"]
    assert "Traceback" not in str(body)
    assert "stack" not in str(body)


def test_missing_task_returns_standard_error(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/tasks/no-such-task")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.TASK_NOT_FOUND.code


def test_legacy_capture_session_api_is_not_registered(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    assert client.post("/api/capture-sessions").status_code == 404
    assert client.get("/api/capture-sessions/session_001").status_code == 404


def test_legacy_mobile_session_api_is_not_registered(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    assert client.post("/api/mobile/session_001/pages").status_code == 404
    assert client.post("/api/mobile/session_001/finish").status_code == 404
    assert client.put("/api/mobile/session_001/pages/page_001/quad").status_code == 404


def test_offline_check_returns_local_check_shape(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/maintenance/offline-check")

    assert response.status_code == 200
    assert isinstance(response.get_json()["data"], dict)


def test_offline_check_does_not_make_network_calls(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    connect_calls = []
    real_connect = socket.socket.connect

    def _counting_connect(self_conn, target):
        connect_calls.append(target)
        return real_connect(self_conn, target)

    monkeypatch.setattr(socket.socket, "connect", _counting_connect)

    response = client.get("/api/maintenance/offline-check")

    assert response.status_code == 200
    assert connect_calls == []
