import json
import io
import zipfile

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


def seed_exportable_task(app, status="review"):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    seed_exportable_task_with_id(store, "task_001", status=status)


def seed_exportable_task_with_id(store, task_id, status="review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )
    store.write(
        f"results/{task_id}/review_result.json",
        {
            "task_id": task_id,
            "schema_version": "1.0.0",
            "document_type": "general_medical_record",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "final_value": "张三",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "第1页",
                    "page_no": 1,
                }
            ],
        },
    )


def events(app):
    with open(app.config["LOCAL_EVENT_LOG"].current_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_export_check_route_allows_review_task(client, app):
    seed_exportable_task(app, status="review")

    response = client.get("/api/tasks/task_001/export/check")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "review"
    assert data["can_export"] is True


def test_export_json_route_keeps_task_status(client, app):
    seed_exportable_task(app, status="done")

    response = client.get("/api/tasks/task_001/export/json")

    assert response.status_code == 200
    assert response.content_type == "application/json"
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task = store.read("tasks/task_001.json")
    assert task["status"] == "done"
    assert "json" in task["export_summary"]["formats"]
    assert events(app)[-1]["event"] == "export_succeeded"


def test_export_excel_route_returns_xlsx_download_headers(client, app):
    seed_exportable_task(app, status="review")

    response = client.get("/api/tasks/task_001/export/excel")

    assert response.status_code == 200
    assert "spreadsheet" in response.content_type
    assert "task_001.review.xlsx" in response.headers.get("Content-Disposition", "")


def test_export_route_rejects_uploading_task(client, app):
    seed_exportable_task(app, status="uploading")

    response = client.get("/api/tasks/task_001/export/json")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "EXPORT_VALIDATION_FAILED"


def test_batch_zip_route_returns_zip_download(client, app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    seed_exportable_task_with_id(store, "task_001", status="review")
    seed_exportable_task_with_id(store, "task_002", status="done")

    response = client.post(
        "/api/tasks/export/batch-zip",
        json={"task_ids": ["task_001", "task_002"]},
    )

    assert response.status_code == 200
    assert response.content_type == "application/zip"
    assert "batch-review-export.zip" in response.headers.get("Content-Disposition", "")

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert "manifest.json" in archive.namelist()
        assert "task_001/task_001.review.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2


def test_batch_zip_route_rejects_empty_task_ids(client):
    response = client.post("/api/tasks/export/batch-zip", json={"task_ids": []})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"
