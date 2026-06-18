import pytest
import yaml
from app.backend import create_backend_app
from app.backend.services.schema_service import SchemaService


@pytest.fixture
def schema_path(tmp_path):
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir()

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
    path = schemas_dir / "medical_record.v1.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(schema_data, f)
    return path


@pytest.fixture
def app(tmp_path, monkeypatch, schema_path):
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
    app_instance = create_backend_app(config_dir=str(config_dir))
    app_instance.config["TESTING"] = True
    app_instance.config["SCHEMA_SERVICE"] = SchemaService(str(schema_path))
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

    def test_invalid_schema_returns_500_without_path_details(self, client, app, tmp_path):
        invalid_path = tmp_path / "invalid-schema.yaml"
        invalid_path.write_text("version: '1.0.0'\nfield_groups: []\n", encoding="utf-8")
        app.config["SCHEMA_SERVICE"] = SchemaService(str(invalid_path))

        resp = client.get("/api/schema/current")

        assert resp.status_code == 500
        error = resp.get_json()["error"]
        assert error["code"] == "INTERNAL_SERVER_ERROR"
        assert str(tmp_path) not in error["message"]
        assert str(tmp_path) not in str(error["details"])


def test_schema_api_returns_admission_record_structured_fields(tmp_path, monkeypatch):
    """默认入院记录 schema 通过 schema API 返回固定章节顺序。"""
    import os

    from app.backend import create_backend_app
    from app.backend.config import PROJECT_ROOT

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app_instance = create_backend_app(config_dir=str(config_dir))
    # 显式指向仓库固定字段 schema，避免依赖加载顺序
    admission_schema_path = os.path.join(
        PROJECT_ROOT, "app", "config", "schemas",
        "admission_record_structured_fields.v1.yaml",
    )
    app_instance.config["SCHEMA_SERVICE"] = SchemaService(admission_schema_path)
    app_instance.config["TESTING"] = True
    client = app_instance.test_client()

    resp = client.get("/api/schema/current")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["version"] == "admission_record_structured_fields.v1"
    group_labels = [g["group_label"] for g in data["field_groups"]]
    assert group_labels == [
        "主诉",
        "现病史",
        "既往史",
        "个人史",
        "家族史",
        "体格检查",
        "辅助检查",
        "诊断",
    ]
    # 旧小字段不得出现
    field_keys = [
        f["field_key"] for g in data["field_groups"] for f in g["fields"]
    ]
    assert "copd_history_years" not in field_keys
    assert "blood_gas_pao2" not in field_keys
    assert "ct_features" not in field_keys
