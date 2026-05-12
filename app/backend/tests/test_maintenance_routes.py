import pytest

from app.backend import create_backend_app


@pytest.fixture
def client(tmp_path, monkeypatch):
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
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def test_offline_check_route_returns_checks(client):
    resp = client.get("/api/maintenance/offline-check")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["status"] in ("ok", "warning", "failed")
    keys = {item["key"] for item in data["checks"]}
    assert {"storage_dir", "exports_dir", "logs_dir", "schema_file", "ppstructure_models", "llm_models"} <= keys


def test_cleanup_route_requires_confirm(client):
    resp = client.post("/api/maintenance/tasks/task-001/cleanup", json={"confirm": False})

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"
