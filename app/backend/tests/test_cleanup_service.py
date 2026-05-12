import os

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.cleanup_service import CleanupService
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path):
    config = {
        "storage_dir": str(tmp_path / "data"),
        "export_dir": str(tmp_path / "exports"),
        "log_dir": str(tmp_path / "logs"),
    }
    store = JsonStore(config["storage_dir"])
    service = CleanupService(config=config, store=store)
    return service, store, config


def test_cleanup_plan_lists_task_scoped_paths_only(tmp_path):
    service, store, _ = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})

    plan = service.plan_task_cleanup("task-001")

    assert plan["task_id"] == "task-001"
    assert plan["requires_confirm"] is True
    assert "results/task-001" in plan["storage_paths"]
    assert "exports/task-001" in plan["export_paths"]
    assert plan["log_cleanup"] == "日志按轮转策略处理，不按任务物理删除"


def test_cleanup_requires_confirm_true(tmp_path):
    service, store, _ = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})

    with pytest.raises(AppError) as exc_info:
        service.cleanup_task("task-001", confirm=False)

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_cleanup_deletes_only_task_paths(tmp_path):
    service, store, config = make_service(tmp_path)
    store.write("tasks/task-001.json", {"task_id": "task-001", "session_id": "session-001"})
    store.write("results/task-001/review_result.json", {"ok": True})
    os.makedirs(os.path.join(config["export_dir"], "task-001"), exist_ok=True)
    with open(os.path.join(config["export_dir"], "task-001", "result.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    store.write("results/task-002/review_result.json", {"keep": True})

    result = service.cleanup_task("task-001", confirm=True)

    assert result["task_id"] == "task-001"
    assert store.read("results/task-001/review_result.json") is None
    assert store.read("results/task-002/review_result.json") == {"keep": True}


def test_rejects_unsafe_path_values(tmp_path):
    service, _, _ = make_service(tmp_path)

    for unsafe in ("", ".", "..", "../x", "/tmp/x"):
        with pytest.raises(AppError):
            service._safe_relative_path(unsafe)
