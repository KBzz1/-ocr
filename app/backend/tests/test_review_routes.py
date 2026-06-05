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
        "tasks/1.json",
        {
            "task_id": "1",
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
    # 使用 schema 实际存在的字段(默认 COPD schema 包含 occupation 等 25 字段)
    store.write(
        "results/1/field_candidates.json",
        {
            "task_id": "1",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "occupation", "original_value": "退休", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "temperature", "original_value": "36.5℃", "evidence": "第2页", "confidence": 0.85},
            ],
        },
    )
    return {"task_id": "1"}


def test_get_review_initializes_result(client, review_task):
    response = client.get(f"/api/tasks/{review_task['task_id']}/review")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == "1"
    assert data["status"] == "review"
    fields = data["review_result"]["fields"]
    # BE-MVP-05-06: 字段集合与 schema 一致(默认 COPD schema 25 个字段)
    assert len(fields) >= 2
    # 候选里有的字段被正确填入
    field_by_key = {f["field_key"]: f for f in fields}
    assert field_by_key["occupation"]["final_value"] == "退休"
    assert field_by_key["temperature"]["final_value"] == "36.5℃"


def test_put_review_saves_final_fields(client, review_task):
    response = client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "occupation", "value": "工人", "status": "modified"},
                {"field_key": "temperature", "value": "36.5℃", "status": "confirmed"},
            ]
        },
    )

    assert response.status_code == 200
    fields = response.get_json()["data"]["review_result"]["fields"]
    field_by_key = {f["field_key"]: f for f in fields}
    assert field_by_key["occupation"]["status"] == "modified"
    assert field_by_key["occupation"]["final_value"] == "工人"
    assert field_by_key["temperature"]["status"] == "confirmed"


def test_complete_review_route_marks_done(client, review_task):
    client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "occupation", "value": "退休", "status": "confirmed"},
                {"field_key": "temperature", "value": "36.5℃", "status": "confirmed"},
            ]
        },
    )

    response = client.post(f"/api/tasks/{review_task['task_id']}/complete")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "done"


def test_reopen_review_transitions_done_to_review(client, app, review_task):
    client.put(
        f"/api/tasks/{review_task['task_id']}/review",
        json={
            "fields": [
                {"field_key": "occupation", "value": "退休", "status": "confirmed"},
                {"field_key": "temperature", "value": "36.5℃", "status": "confirmed"},
            ]
        },
    )
    client.post(f"/api/tasks/{review_task['task_id']}/complete")

    response = client.post(f"/api/tasks/{review_task['task_id']}/review/reopen")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "review"


def test_failed_task_cannot_enter_review_flow(client, app):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/1.json",
        {
            "task_id": "1",
            "status": "failed",
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "images": [],
        },
    )

    response = client.get("/api/tasks/1/review")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
