import os

from app.backend.services.offline_check_service import OfflineCheckService


def make_config(tmp_path):
    schema = tmp_path / "app" / "config" / "schemas" / "medical_record.v1.yaml"
    schema.parent.mkdir(parents=True)
    schema.write_text("version: medical_record.v1\n", encoding="utf-8")
    return {
        "storage_dir": str(tmp_path / "data"),
        "export_dir": str(tmp_path / "exports"),
        "log_dir": str(tmp_path / "logs"),
        "model_dir": str(tmp_path / "models"),
        "schema_file": str(schema),
    }


def test_offline_check_creates_local_dirs_and_reports_model_warnings(tmp_path):
    config = make_config(tmp_path)
    service = OfflineCheckService(config)

    result = service.run()

    assert result["status"] == "warning"
    assert os.path.isdir(config["storage_dir"])
    assert os.path.isdir(config["export_dir"])
    assert os.path.isdir(config["log_dir"])
    checks = {item["key"]: item for item in result["checks"]}
    assert checks["storage_dir"]["status"] == "ok"
    assert checks["schema_file"]["status"] == "ok"
    assert checks["ppstructure_models"]["status"] == "warning"
    assert checks["llm_models"]["status"] == "warning"


def test_missing_schema_is_failed(tmp_path):
    config = make_config(tmp_path)
    os.remove(config["schema_file"])

    result = OfflineCheckService(config).run()

    checks = {item["key"]: item for item in result["checks"]}
    assert result["status"] == "failed"
    assert checks["schema_file"]["status"] == "failed"


def test_offline_check_has_no_network_imports():
    import app.backend.services.offline_check_service as module

    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in ("requests", "urllib", "httpx", "socket.create_connection"):
        assert forbidden not in source
