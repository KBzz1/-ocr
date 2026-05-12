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


def upload_jpeg(client, session_id):
    return client.post(
        f"/api/mobile/{session_id}/pages",
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


def test_session_upload_finish_events_logged(client, app):
    create_resp = client.post("/api/capture-sessions")
    session_id = create_resp.get_json()["data"]["session_id"]
    upload_resp = upload_jpeg(client, session_id)
    assert upload_resp.status_code == 201
    finish_resp = client.post(f"/api/mobile/{session_id}/finish")
    assert finish_resp.status_code == 200

    names = [item["event"] for item in events(app)]
    assert "session_created" in names
    assert "page_uploaded" in names
    assert "session_finished" in names


def test_task_processing_failure_event_has_context_and_no_sensitive_text(client, app):
    create_resp = client.post("/api/capture-sessions")
    session_id = create_resp.get_json()["data"]["session_id"]
    upload_jpeg(client, session_id)
    task_id = client.post(f"/api/mobile/{session_id}/finish").get_json()["data"]["task_id"]

    client.post(f"/api/tasks/{task_id}/process")

    failures = [item for item in events(app) if item["event"] == "task_processing_failed"]
    assert failures
    failure = failures[-1]
    assert failure["task_id"] == task_id
    assert failure["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    serialized = json.dumps(failure, ensure_ascii=False)
    assert "traceback" not in serialized.lower()
    assert "base64" not in serialized.lower()
    assert "110101199001011234" not in serialized
