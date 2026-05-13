import pytest

from app.backend import create_backend_app
from app.backend.enums import FieldStatus
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def _seed_confirmed_task(app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task-001.json",
        {
            "task_id": "task-001",
            "session_id": "session-001",
            "status": "confirmed",
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 2,
            "page_order": ["page-1", "page-2"],
            "source": "capture_session",
            "schema_version": "1.0.0",
            "document_type": "general_medical_record",
        },
    )
    fields = [
        {
            "field_key": "chief_complaint",
            "field_name": "主诉",
            "auto_value": "auto_headache",
            "final_value": "头痛3天",
            "evidence": "第1页第2行",
            "page_no": 1,
            "confidence": 0.95,
            "status": FieldStatus.CONFIRMED.value,
            "empty_accepted": False,
            "review_note": None,
            "reviewed_at": "2026-05-13T09:55:00+00:00",
            "updated_at": "2026-05-13T09:55:00+00:00",
            "history": [],
        },
        {
            "field_key": "diagnosis",
            "field_name": "诊断",
            "auto_value": "auto_diag",
            "final_value": "上呼吸道感染",
            "evidence": "第2页第1行",
            "page_no": 2,
            "confidence": 0.8,
            "status": FieldStatus.CONFIRMED.value,
            "empty_accepted": False,
            "review_note": None,
            "reviewed_at": "2026-05-13T09:56:00+00:00",
            "updated_at": "2026-05-13T09:56:00+00:00",
            "history": [],
        },
    ]
    store.write(
        "results/task-001/review_result.json",
        {
            "task_id": "task-001",
            "schema_version": "1.0.0",
            "document_type": "general_medical_record",
            "initialized_at": "2026-05-13T09:50:00+00:00",
            "updated_at": "2026-05-13T09:56:00+00:00",
            "fields": fields,
            "summary": {
                "total_count": 2,
                "unreviewed_count": 0,
                "confirmed_count": 2,
                "modified_count": 0,
                "suspicious_count": 0,
                "empty_count": 0,
                "empty_unaccepted_count": 0,
                "missing_evidence_count": 0,
            },
        },
    )


class TestExportCheckRoute:
    def test_export_check_route_success(self, client, app):
        _seed_confirmed_task(app)

        resp = client.get("/api/tasks/task-001/export/check")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["task_id"] == "task-001"
        assert data["status"] == "confirmed"
        assert data["can_export"] is True
        assert data["summary"]["total_count"] == 2

    def test_export_check_route_rejects_unconfirmed_task(self, client, app):
        store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
        store.write(
            "tasks/task-002.json",
            {
                "task_id": "task-002",
                "session_id": "session-001",
                "status": "ready_for_review",
                "created_at": "2026-05-12T10:00:00+00:00",
                "page_count": 1,
                "page_order": ["page-1"],
                "source": "capture_session",
            },
        )

        resp = client.get("/api/tasks/task-002/export/check")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "EXPORT_VALIDATION_FAILED"

    def test_export_route_missing_task_returns_task_not_found(self, client):
        resp = client.get("/api/tasks/nonexistent/export/check")

        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "TASK_NOT_FOUND"


class TestExportJsonRoute:
    def test_export_json_route_returns_download_headers(self, client, app):
        _seed_confirmed_task(app)

        resp = client.get("/api/tasks/task-001/export/json")

        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert "task-001.review.json" in content_disp

        # Verify JSON body uses final_value
        body = resp.get_json()
        fields = body["fields"]
        chief = next(f for f in fields if f["field_key"] == "chief_complaint")
        assert chief["final_value"] == "头痛3天"
        assert "auto_value" not in chief


class TestExportExcelRoute:
    def test_export_excel_route_returns_xlsx_download_headers(self, client, app):
        _seed_confirmed_task(app)

        resp = client.get("/api/tasks/task-001/export/excel")

        assert resp.status_code == 200
        assert "spreadsheet" in resp.content_type
        content_disp = resp.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp
        assert "task-001.review.xlsx" in content_disp
