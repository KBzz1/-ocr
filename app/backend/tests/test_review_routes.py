import pytest

from app.backend import create_backend_app
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


@pytest.fixture
def review_task(app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": "review",
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
        "results/task_001/field_candidates.json",
        {
            "task_id": "task_001",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "patient_name", "original_value": "张三", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "department", "original_value": "骨科", "evidence": "第1页", "confidence": 0.8},
            ],
        },
    )
    return {"task_id": "task_001"}


def test_get_review_initializes_result(client, review_task):
    response = client.get(f"/api/tasks/{review_task['task_id']}/review")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == "task_001"
    assert data["status"] == "review"
    assert data["review_result"]["summary"]["unreviewed_count"] == 2


def test_put_review_saves_final_fields(client, review_task):
    response = client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "modified"},
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    assert response.status_code == 200
    fields = response.get_json()["data"]["review_result"]["fields"]
    assert {field["status"] for field in fields} <= {"unreviewed", "confirmed", "modified"}


def test_complete_review_route_marks_done(client, review_task):
    client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "confirmed"},
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    response = client.post(f"/api/tasks/{review_task['task_id']}/complete")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "done"


def test_failed_task_cannot_enter_review_flow(client, app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": "failed",
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "images": [],
        },
    )

    response = client.get("/api/tasks/task_001/review")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
