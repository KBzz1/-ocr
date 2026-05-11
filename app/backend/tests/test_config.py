import os
import pytest
import tempfile
from app.backend.config import load_config, DEFAULT_CONFIG


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
