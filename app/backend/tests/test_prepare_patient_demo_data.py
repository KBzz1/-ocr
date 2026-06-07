"""prepare_patient_demo_data 一次性开发整理脚本测试。

测试不操作真实 data/ 目录,只用 tmp_path。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.backend.storage.json_store import JsonStore
from scripts.maintenance.prepare_patient_demo_data import prepare_demo_data


FIXED_NOW = "2026-06-07T10:00:00+08:00"


def _write_task(store, task_id, status, **overrides):
    base = {
        "task_id": task_id,
        "status": status,
        "created_at": FIXED_NOW,
        "updated_at": FIXED_NOW,
        "images": [],
        "deleted_at": None,
    }
    base.update(overrides)
    store.write(f"tasks/{task_id}.json", base)


def test_prepare_demo_data_keeps_one_visible_task_and_binds_test_patient(tmp_path):
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")
    _write_task(store, "2", "failed")

    summary = prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=True,
    )

    visible = [t for t in store.list_json("tasks") if not t.get("deleted_at")]
    assert len(visible) == 1
    assert visible[0]["task_id"] == "1"
    assert visible[0]["document_type"] == "copd_admission_record"
    assert visible[0]["record_date"] == "2026-06-07"
    assert summary["hidden_task_count"] == 1
    assert summary["patient_id"].startswith("P-")
    patient = store.read(f"patients/{summary['patient_id']}.json")
    assert patient["name"] == "测试用例"
    assert store.exists("tasks/2.json")
    assert store.read("tasks/2.json")["deleted_at"] is not None


def test_prepare_demo_data_preserves_files_and_results_dirs(tmp_path):
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")
    _write_task(store, "2", "failed")
    store.write("results/1/field_candidates.json", {"task_id": "1", "candidates": []})
    store.write("pages/1/page_001.json", {"page_id": "page_001", "path": "pages/1/page_001.bin"})

    prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=True,
    )

    assert store.exists("results/1/field_candidates.json")
    assert store.exists("pages/1/page_001.json")
    assert store.exists("tasks/1.json")
    assert store.exists("tasks/2.json")


def test_prepare_demo_data_is_idempotent(tmp_path):
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")
    _write_task(store, "2", "failed")

    first = prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=True,
    )
    second = prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=True,
    )

    assert first["patient_id"] == second["patient_id"]
    assert second["hidden_task_count"] == 0
    visible_patients = [
        item for item in store.list_json("patients") if item.get("name") == "测试用例"
    ]
    assert len(visible_patients) == 1


def test_prepare_demo_data_dry_run_does_not_modify(tmp_path):
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")
    _write_task(store, "2", "failed")

    prepare_demo_data(
        storage_dir=str(tmp_path),
        keep_task_id="1",
        record_date="2026-06-07",
        apply=False,
    )

    assert store.read("tasks/1.json").get("patient_id") is None
    assert store.read("tasks/2.json").get("deleted_at") is None
    assert store.list_json("patients") == []


def test_prepare_demo_data_fails_when_keep_task_missing(tmp_path):
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")

    with pytest.raises(SystemExit):
        prepare_demo_data(
            storage_dir=str(tmp_path),
            keep_task_id="999",
            record_date="2026-06-07",
            apply=True,
        )


def test_cli_rejects_apply_without_confirm(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/maintenance/prepare_patient_demo_data.py"),
            "--storage-dir",
            str(tmp_path),
            "--keep-task-id",
            "1",
            "--record-date",
            "2026-06-07",
            "--apply",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "--confirm-dev-data" in result.stderr or "confirm-dev-data" in result.stderr


def test_cli_dry_run_prints_dev_banner_and_summary(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    store = JsonStore(str(tmp_path))
    _write_task(store, "1", "done")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/maintenance/prepare_patient_demo_data.py"),
            "--storage-dir",
            str(tmp_path),
            "--keep-task-id",
            "1",
            "--record-date",
            "2026-06-07",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "DEV TOOL ONLY" in result.stderr
    payload = json.loads(result.stdout)
    assert payload["kept_task_id"] == "1"
    assert payload["applied"] is False


def test_cli_does_not_echo_task_records(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[3]
    store = JsonStore(str(tmp_path))
    _write_task(
        store,
        "1",
        "done",
        display_name="李雷住院号110101199001011234手机13800138000",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/maintenance/prepare_patient_demo_data.py"),
            "--storage-dir",
            str(tmp_path),
            "--keep-task-id",
            "1",
            "--record-date",
            "2026-06-07",
        ],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "110101199001011234" not in combined
    assert "13800138000" not in combined
