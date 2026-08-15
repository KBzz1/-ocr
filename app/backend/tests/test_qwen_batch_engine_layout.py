import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = ROOT / "algorithms" / "qwen_batch_engine"


def _tracked_files(rel: str) -> list[str]:
    """返回 rel 路径下被 git 跟踪的文件列表(相对仓库根的路径)。

    git 按路径前缀匹配,__pycache__ 等目录下任何被跟踪文件都会被列出。
    """
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--", f"algorithms/qwen_batch_engine/{rel}"],
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line]


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
    # 检查 git 跟踪状态而非磁盘存在性:__pycache__ 等运行产物在本机必然存在,
    # 只要未被提交就不算违规。
    forbidden = [
        "upstream/.git",
        "upstream/.env",
        "upstream/scripts/__pycache__",
    ]
    for rel in forbidden:
        tracked = _tracked_files(rel)
        assert not tracked, f"forbidden upstream artifact committed: {tracked[0]}"


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


def test_main_docker_image_includes_qwen_batch_runtime_dependencies():
    requirements = (ROOT / "requirements.docker.txt").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    for package in [
        "requests",
        "Pillow",
        "pdf2image",
        "tqdm",
        "opencv-python-headless",
        "numpy",
    ]:
        assert package in requirements
    assert "poppler-utils" in dockerfile
