import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path, orchestrator=None, schema_provider=None):
    return TaskService(
        JsonStore(str(tmp_path)),
        orchestrator=orchestrator,
        schema_provider=schema_provider,
    )


def write_task(tmp_path, task_id="task_001", status="uploading", **overrides):
    task = {
        "task_id": task_id,
        "status": status,
        "created_at": "2026-05-19T10:00:00+00:00",
        "updated_at": "2026-05-19T10:00:00+00:00",
        "upload_token": "token_001",
        "images": [],
        "error_code": None,
        "error_message": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
    }
    task.update(overrides)
    JsonStore(str(tmp_path)).write(f"tasks/{task_id}.json", task)
    return task


def test_create_uploading_task_has_upload_token_and_empty_images(tmp_path):
    service = make_service(tmp_path)

    task = service.create_uploading_task(base_url="http://192.168.1.5:8081")

    assert task["task_id"].startswith("task_")
    assert task["status"] == "uploading"
    assert task["upload_token"]
    assert task["mobile_upload_url"] == (
        f"http://192.168.1.5:8081/mobile/upload/{task['task_id']}?token={task['upload_token']}"
    )
    assert task["images"] == []
    assert task["error_code"] is None
    assert task["export_summary"] == {"last_exported_at": None, "formats": [], "files": []}


def test_list_tasks_does_not_expose_session_id(tmp_path):
    service = make_service(tmp_path)
    created = write_task(
        tmp_path,
        images=[{"page_id": "page_001", "page_no": 1}],
        session_id="legacy_session",
    )

    [summary] = service.list_tasks()

    assert summary["task_id"] == created["task_id"]
    assert summary["status"] == "uploading"
    assert summary["page_count"] == 1
    assert "session_id" not in summary


def test_list_tasks_hides_empty_uploading_placeholders(tmp_path):
    service = make_service(tmp_path)
    service.create_uploading_task(base_url="http://127.0.0.1:8081")
    write_task(
        tmp_path,
        task_id="task_002",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(tmp_path, task_id="task_003", status="failed")

    summaries = service.list_tasks()

    assert [summary["task_id"] for summary in summaries] == ["task_002", "task_003"]
    assert service.list_tasks(status="uploading")[0]["task_id"] == "task_002"


def test_get_task_normalizes_mvp_shape(tmp_path):
    write_task(
        tmp_path,
        images=[{"page_id": "page_001", "page_no": 1}],
        review_summary=None,
    )
    service = make_service(tmp_path)

    task = service.get_task("task_001")

    assert task["status"] == "uploading"
    assert task["page_count"] == 1
    assert task["images"] == [{"page_id": "page_001", "page_no": 1}]
    assert task["review_summary"] is None
    assert "session_id" not in task


def test_get_nonexistent_task_raises_not_found(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.get_task("missing")

    assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND.code


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("uploading", "processing"),
        ("uploading", "failed"),
        ("processing", "review"),
        ("processing", "failed"),
        ("review", "done"),
        ("review", "processing"),
        ("done", "processing"),
        ("failed", "processing"),
    ],
)
def test_valid_transitions_match_mvp_state_enums(tmp_path, current, target):
    service = make_service(tmp_path)
    service._validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("uploading", "review"),
        ("processing", "done"),
        ("done", "failed"),
        ("failed", "uploading"),
    ],
)
def test_invalid_transitions_raise_invalid_transition(tmp_path, current, target):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service._validate_transition(current, target)

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
    assert exc_info.value.details == {"current": current, "target": target}


def test_process_without_algorithm_marks_failed(tmp_path):
    write_task(tmp_path, status="uploading")
    service = make_service(tmp_path)

    result = service.process("task_001")

    assert result["status"] == "failed"
    assert result["processing_at"] is not None
    assert result["failed_at"] is not None
    assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    assert result["error_message"] == "图像处理模块未配置"
    assert result["details"]["stage"] == "image_processing"
    assert result["details"]["reason"] == "module_not_configured"
    assert [entry["to_status"] for entry in result["status_history"]] == [
        "uploading",
        "processing",
        "failed",
    ]


def test_process_invalid_state_raises_invalid_transition(tmp_path):
    write_task(tmp_path, status="done")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.mark_failed("task_001", "ALGORITHM_MODULE_FAILED", "算法模块异常")

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
