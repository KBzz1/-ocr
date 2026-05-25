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


def test_static_dir_default_normalized(tmp_path):
    """static_dir 默认值归一化为项目内 app/frontend/dist。"""
    from app.backend.config import load_config

    config = load_config(str(tmp_path / "nonexistent"))

    assert "static_dir" in config
    assert os.path.isabs(config["static_dir"])
    assert config["static_dir"].endswith(os.path.join("app", "frontend", "dist"))


def test_load_config_supports_copd_extractor_settings(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  enable_copd_extractor: true
  llm_model_path: ./models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
  llm_context_tokens: 8192
  llm_max_tokens: 1024
  llm_extraction_batch_size: 25
  llm_enable_verification: false
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["enable_copd_extractor"] is True
    assert config["llm_model_path"].endswith("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf")
    assert config["llm_context_tokens"] == 8192
    assert config["llm_max_tokens"] == 1024
    assert config["llm_extraction_batch_size"] == 25
    assert config["llm_enable_verification"] is False


def test_load_config_supports_local_ocr_settings(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  enable_local_ocr: true
  local_ocr_python_executable: /opt/conda/envs/manzufei_ocr/bin/python
  local_ocr_script_path: ./app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py
  local_ocr_work_root: /tmp/manzufei_ocr_ocr_runs
  local_ocr_max_new_tokens: 1024
  local_ocr_timeout_seconds: 1200
  local_ocr_device: gpu:0
  local_ocr_max_pixels: 200000
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["enable_local_ocr"] is True
    assert config["local_ocr_python_executable"] == "/opt/conda/envs/manzufei_ocr/bin/python"
    assert config["local_ocr_script_path"].endswith("paddleocr_vl_batch_runner.py")
    assert config["local_ocr_work_root"] == "/tmp/manzufei_ocr_ocr_runs"
    assert config["local_ocr_max_new_tokens"] == 1024
    assert config["local_ocr_timeout_seconds"] == 1200
    assert config["local_ocr_device"] == "gpu:0"
    assert config["local_ocr_max_new_tokens"] == 1024
    assert config["local_ocr_max_pixels"] == 200000


def test_local_ocr_timeout_must_be_positive(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  local_ocr_timeout_seconds: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local_ocr_timeout_seconds"):
        load_config(str(config_dir))


def test_local_ocr_generation_limits_must_be_positive_when_set(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  local_ocr_max_new_tokens: -1
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local_ocr_max_new_tokens"):
        load_config(str(config_dir))


def test_llm_extraction_batch_size_must_be_positive(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  llm_extraction_batch_size: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="llm_extraction_batch_size"):
        load_config(str(config_dir))


def test_static_dir_overridable_via_local_yaml(tmp_path):
    """paths.static_dir 可通过 local.yaml 覆盖。"""
    import yaml
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default = {"paths": {"static_dir": "./app/frontend/dist"}}
    local = {"paths": {"static_dir": "./custom_dist"}}
    with open(config_dir / "default.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(default, f)
    with open(config_dir / "local.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(local, f)

    config = load_config(str(config_dir))

    assert os.path.isabs(config["static_dir"])
    assert config["static_dir"].endswith("custom_dist")
