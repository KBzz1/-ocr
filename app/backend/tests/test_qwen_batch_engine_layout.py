from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = ROOT / "algorithms" / "qwen_batch_engine"


def test_qwen_batch_engine_layout_exists():
    assert (ENGINE_ROOT / "upstream" / "scripts" / "process.py").is_file()
    assert (ENGINE_ROOT / "upstream" / "config.yaml").is_file()
    assert (ENGINE_ROOT / "overlay" / "CHANGELOG.md").is_file()
    assert (ENGINE_ROOT / "adapter" / "README.md").is_file()
    assert (ENGINE_ROOT / "VERSION").is_file()


def test_qwen_batch_engine_version_records_upstream_commit():
    version_text = (ENGINE_ROOT / "VERSION").read_text(encoding="utf-8")
    assert "upstream_commit=a746ba9d061d2af8878485f1f837e4d10e2bd755" in version_text
    assert "schema_version=qwen_batch_admission_record.v2" in version_text


def test_qwen_batch_engine_does_not_commit_runtime_or_secret_files():
    forbidden = [
        ENGINE_ROOT / "upstream" / ".git",
        ENGINE_ROOT / "upstream" / ".env",
        ENGINE_ROOT / "upstream" / "scripts" / "__pycache__",
    ]
    for path in forbidden:
        assert not path.exists(), f"forbidden upstream artifact committed: {path}"


def test_qwen_batch_snapshot_contains_minimum_audit_files():
    snapshot = ENGINE_ROOT / "snapshots" / "2026-06-26-a746ba9"
    expected = [
        "upstream_commit.txt",
        "schema_template.yaml",
        "prompt_system.txt",
        "prompt_user_template.txt",
        "model_config.yaml",
        "runtime_config.yaml",
        "smoke_result.md",
    ]
    for filename in expected:
        assert (snapshot / filename).is_file(), f"missing snapshot file: {filename}"
