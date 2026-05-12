import os
import pytest
import yaml
from app.backend import create_backend_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

    # 写入合法 schema 文件
    schema_data = {
        "version": "1.0.0",
        "document_type": "general_medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "name", "label": "姓名", "type": "string"},
                ],
            }
        ],
    }
    schema_path = schemas_dir / "medical_record.v1.yaml"
    with open(schema_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(schema_data, f)

    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
sessions:
  capture_session_ttl_minutes: 30
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    # 替换 SchemaService 的 schema_path 为临时测试文件
    import app.backend.services.schema_service as svc_mod

    original_init = svc_mod.SchemaService.__init__

    def patched_init(self, path):
        self._schema_path = str(schema_path)
        self._cached = None

    monkeypatch.setattr(svc_mod.SchemaService, "__init__", patched_init)

    app_instance = create_backend_app(config_dir=str(config_dir))
    app_instance.config["TESTING"] = True
    return app_instance


@pytest.fixture
def client(app):
    return app.test_client()


class TestSchemaAPI:
    def test_get_current_schema_returns_200(self, client):
        resp = client.get("/api/schema/current")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["version"] == "1.0.0"
        assert data["data"]["document_type"] == "general_medical_record"

    def test_response_has_field_groups_with_field_key_and_key(self, client):
        resp = client.get("/api/schema/current")
        data = resp.get_json()
        groups = data["data"]["field_groups"]
        assert len(groups) == 1
        field = groups[0]["fields"][0]
        assert field["field_key"] == "name"
        assert field["key"] == "name"
        assert field["label"] == "姓名"

    def test_response_field_groups_preserve_order(self, client):
        resp = client.get("/api/schema/current")
        groups = resp.get_json()["data"]["field_groups"]
        assert groups[0]["group_key"] == "basic"
