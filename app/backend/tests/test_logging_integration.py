import io
import json

import pytest

from app.backend import create_backend_app


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
  model_dir: "{tmp_path / 'models'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    schema_dir = tmp_path / "repo" / "app" / "config" / "schemas"
    schema_dir.mkdir(parents=True)
    (schema_dir / "medical_record.v1.yaml").write_text(
        "version: \"1.0.0\"\n"
        "document_type: general_medical_record\n"
        "field_groups:\n"
        "  - group_key: basic\n"
        "    group_label: 基本信息\n"
        "    fields:\n"
        "      - field_key: name\n"
        "        label: 姓名\n"
        "        type: string\n",
        encoding="utf-8",
    )
    (schema_dir / "copd_admission_record.v1.yaml").write_text(
        "version: \"1.0.0\"\n"
        "document_type: copd_admission_record\n"
        "field_groups:\n"
        "  - group_key: basic\n"
        "    group_label: 基本信息\n"
        "    fields:\n"
        "      - field_key: name\n"
        "        label: 姓名\n"
        "        type: string\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend.config.PROJECT_ROOT", str(tmp_path / "repo"))
    monkeypatch.setattr("app.backend.PROJECT_ROOT", str(tmp_path / "repo"))
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def events(app):
    path = app.config["LOCAL_EVENT_LOG"].current_path
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def upload_jpeg(client, task):
    return client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token={task['upload_token']}",
        data={
            "image_width": "100",
            "image_height": "100",
            "image": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "page.jpg"),
        },
        content_type="multipart/form-data",
    )


def test_startup_event_logged(app):
    names = [item["event"] for item in events(app)]
    assert "system_started" in names
    assert "algorithm_module_not_configured" in names


def test_task_upload_finish_events_logged(client, app):
    task = client.post("/api/tasks").get_json()["data"]
    upload_resp = upload_jpeg(client, task)
    assert upload_resp.status_code == 201
    finish_resp = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")
    assert finish_resp.status_code == 200

    names = [item["event"] for item in events(app)]
    assert "task_processing_started" in names
    assert "task_processing_failed" in names


def test_task_processing_failure_event_has_context_and_no_sensitive_text(client, app):
    task = client.post("/api/tasks").get_json()["data"]
    upload_jpeg(client, task)
    task_id = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}").get_json()["data"]["task_id"]

    failures = [item for item in events(app) if item["event"] == "task_processing_failed"]
    assert failures
    failure = failures[-1]
    assert failure["task_id"] == task_id
    assert failure["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    serialized = json.dumps(failure, ensure_ascii=False)
    assert "traceback" not in serialized.lower()
    assert "base64" not in serialized.lower()
    assert "110101199001011234" not in serialized


def test_review_events_logged_without_field_values(client, app):
    from app.backend.storage.json_store import JsonStore

    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task-review.json",
        {
            "task_id": "task-review",
            "status": "review",
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "images": [],
            "schema_version": "1.0.0",
            "document_type": "general_medical_record",
        },
    )
    store.write(
        "results/task-review/field_candidates.json",
        {
            "task_id": "task-review",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {
                    "field_key": "name",
                    "original_value": "张三",
                    "evidence": "第1页",
                    "page_no": 1,
                    "confidence": 0.9,
                }
            ],
        },
    )

    client.get("/api/tasks/task-review/review")
    patch_resp = client.patch("/api/tasks/task-review/review/fields/name", json={"action": "confirm"})
    assert patch_resp.status_code == 200
    confirm_resp = client.post("/api/tasks/task-review/complete")
    assert confirm_resp.status_code == 200

    records = events(app)
    names = [item["event"] for item in records]
    assert "review_field_saved" in names
    assert "review_completed" in names

    review_event = next(item for item in records if item["event"] == "review_field_saved")
    assert review_event["task_id"] == "task-review"
    assert review_event["field_key"] == "name"
    assert review_event["status"] == "confirmed"
    assert "张三" not in json.dumps(records, ensure_ascii=False)
