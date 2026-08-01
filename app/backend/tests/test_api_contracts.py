"""API 契约回归测试：MVP 公开入口和移除的旧采集会话入口。"""
import socket

from app.backend.enums import FieldStatus
from app.backend.errors import ErrorCode
from app.backend.storage.json_store import JsonStore
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


def _write_batch_excel_seed(tmp_path):
    store = JsonStore(str(tmp_path))
    task = {
        "task_id": "1",
        "display_name": "1",
        "status": "review",
        "created_at": "2026-07-01T10:00:00+00:00",
        "updated_at": "2026-07-01T10:00:00+00:00",
        "upload_token": "token",
        "images": [],
        "page_count": 1,
        "error_code": None,
        "error_message": None,
        "failed_at": None,
        "review_summary": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        "document_type": "copd_admission_record",
        "document_type_label": "入院记录",
        "schema_version": "1.0.0",
        "prompt_version": "prompt.v1",
        "patient_id": "p1",
        "patient_snapshot": {"patient_id": "p1", "name": "张三"},
        "record_date": "2026-07-01",
        "record_time": None,
        "deleted_at": None,
        "metadata_history": [],
        "status_history": [],
    }
    store.write("tasks/1.json", task)
    store.write("results/1/review_result.json", {
        "task_id": "1",
        "schema_version": "1.0.0",
        "document_type": "copd_admission_record",
        "fields": [{"field_key": "chief_complaint", "field_name": "主诉",
                    "final_value": "反复咳嗽", "status": FieldStatus.CONFIRMED.value}],
    })
    return store


def test_batch_excel_templates_endpoint(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, enable_copd_extractor=True)

    response = client.get("/api/tasks/export/batch-excel/templates")

    assert response.status_code == 200
    templates = response.get_json()["data"]["templates"]
    assert len(templates) >= 1
    assert {"document_type", "label"} <= set(templates[0].keys())


def test_batch_excel_generate_and_download(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, enable_copd_extractor=True)
    _write_batch_excel_seed(tmp_path)

    response = client.post("/api/tasks/export/batch-excel", json={"document_type": "copd_admission_record"})

    assert response.status_code == 200
    report = response.get_json()["data"]
    assert report["exported_count"] == 1
    assert report["skipped_count"] == 0
    download_url = report["download_url"]

    download = client.get(download_url)
    assert download.status_code == 200
    assert download.data[:2] == b"PK"
    assert download.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_batch_excel_missing_document_type(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, enable_copd_extractor=True)

    response = client.post("/api/tasks/export/batch-excel", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_batch_excel_unknown_template(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, enable_copd_extractor=True)

    response = client.post("/api/tasks/export/batch-excel", json={"document_type": "not_registered"})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.EXPORT_VALIDATION_FAILED.code


def test_batch_excel_download_unknown_export_id(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, enable_copd_extractor=True)

    response = client.get("/api/tasks/export/batch-excel/0123456789abcdef0123456789abcdef")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.REQUEST_NOT_FOUND.code
