import os
import pytest
import tempfile
from app.backend.settings import load_config, DEFAULT_CONFIG


class TestDefaultConfig:
    def test_load_without_config_dir(self):
        config = load_config()
        assert config["port"] == 8081
        assert config["bind_host"] == "0.0.0.0"
        assert config["local_host"] == "127.0.0.1"
        assert config["version"] == "0.1.0"
        assert "data_dir" in config
        assert "log_dir" in config
        assert "model_dir" in config
        assert "storage_dir" in config
        assert "export_dir" in config

    def test_default_paths_are_absolute(self):
        config = load_config()
        assert os.path.isabs(config["data_dir"])
        assert os.path.isabs(config["log_dir"])
        assert os.path.isabs(config["export_dir"])


class TestYamlLoading:
    def test_default_yaml_overrides_defaults(self, tmp_path):
        import yaml

        default_yaml = {
            "app": {"version": "2.0.0"},
            "server": {"port": 9999},
        }
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert config["version"] == "2.0.0"
        assert config["port"] == 9999

    def test_local_yaml_overrides_default_yaml(self, tmp_path):
        import yaml

        default_yaml = {
            "app": {"version": "2.0.0"},
            "server": {"port": 9999},
        }
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        local_yaml = {"server": {"port": 5555}}
        with open(tmp_path / "local.yaml", "w") as f:
            yaml.dump(local_yaml, f)

        config = load_config(str(tmp_path))
        assert config["version"] == "2.0.0"  # from default.yaml
        assert config["port"] == 5555         # from local.yaml

    def test_missing_directory_uses_defaults(self):
        config = load_config("/nonexistent/path")
        assert config["port"] == 8081

    def test_paths_normalized_to_absolute(self, tmp_path):
        import yaml

        default_yaml = {"paths": {"data_dir": "./my_data"}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert os.path.isabs(config["data_dir"])


class TestValidation:
    def test_invalid_port_raises(self, tmp_path):
        import yaml

        default_yaml = {"server": {"port": 70000}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="端口号"):
            load_config(str(tmp_path))

    def test_path_not_writable_raises(self, tmp_path):
        import yaml

        blocking_file = tmp_path / "not_a_dir"
        blocking_file.write_text("block", encoding="utf-8")
        default_yaml = {"paths": {"data_dir": str(blocking_file / "child")}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="路径不可写"):
            load_config(str(tmp_path))

    def test_storage_dir_not_writable_raises(self, tmp_path):
        import yaml

        blocking_file = tmp_path / "not_a_dir"
        blocking_file.write_text("block", encoding="utf-8")
        default_yaml = {"paths": {"storage_dir": str(blocking_file / "child")}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="路径不可写"):
            load_config(str(tmp_path))

    def test_export_dir_not_writable_raises(self, tmp_path):
        import yaml

        blocking_file = tmp_path / "not_a_dir"
        blocking_file.write_text("block", encoding="utf-8")
        default_yaml = {"paths": {"export_dir": str(blocking_file / "child")}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        with pytest.raises(ValueError, match="路径不可写"):
            load_config(str(tmp_path))


class TestDeepMerge:
    def test_nested_dicts_are_merged_not_replaced(self, tmp_path):
        import yaml

        default_yaml = {"paths": {"data_dir": "./data", "log_dir": "./logs"}}
        with open(tmp_path / "default.yaml", "w") as f:
            yaml.dump(default_yaml, f)

        local_yaml = {"paths": {"data_dir": "./my_data"}}
        with open(tmp_path / "local.yaml", "w") as f:
            yaml.dump(local_yaml, f)

        config = load_config(str(tmp_path))
        assert "log_dir" in config
        assert "log" in config["log_dir"] or config["log_dir"] == ""


class TestSessionConfig:
    def test_default_capture_session_ttl(self):
        config = load_config()
        assert config["capture_session_ttl_minutes"] == 30

    def test_capture_session_ttl_from_yaml(self, tmp_path):
        import yaml

        default_yaml = {
            "sessions": {"capture_session_ttl_minutes": 15},
        }
        with open(tmp_path / "default.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(default_yaml, f)

        config = load_config(str(tmp_path))
        assert config["capture_session_ttl_minutes"] == 15

    def test_capture_session_ttl_must_be_positive(self, tmp_path):
        import yaml
        import pytest

        default_yaml = {
            "sessions": {"capture_session_ttl_minutes": 0},
        }
        with open(tmp_path / "default.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(default_yaml, f)

        with pytest.raises(ValueError, match="采集会话 TTL"):
            load_config(str(tmp_path))


def test_upload_max_file_size_mb_default(tmp_path):
    from app.backend.config import load_config
    config = load_config(str(tmp_path / "nonexistent"))
    assert config["max_upload_file_size_mb"] == 10


def test_upload_min_quad_area_ratio_default(tmp_path):
    from app.backend.config import load_config
    config = load_config(str(tmp_path / "nonexistent"))
    assert config["min_quad_area_ratio"] == 0.01


def test_flatten_upload_config(tmp_path):
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("""
upload:
  max_file_size_mb: 20
  min_quad_area_ratio: 0.02
""", encoding="utf-8")
    config = load_config(str(config_dir))
    assert config["max_upload_file_size_mb"] == 20
    assert config["min_quad_area_ratio"] == 0.02


def test_max_upload_file_size_mb_must_be_positive(tmp_path):
    import pytest
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("upload:\n  max_file_size_mb: -5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_upload_file_size_mb"):
        load_config(str(config_dir))


def test_min_quad_area_ratio_must_be_between_0_and_1(tmp_path):
    import pytest
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("upload:\n  min_quad_area_ratio: 2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="min_quad_area_ratio"):
        load_config(str(config_dir))
