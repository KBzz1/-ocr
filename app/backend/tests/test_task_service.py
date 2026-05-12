import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path):
    from app.backend.services.task_service import TaskService
    return TaskService(JsonStore(str(tmp_path)))


def write_task(tmp_path, task_id="task-001", status="uploaded", **overrides):
    task = {
        "task_id": task_id,
        "session_id": "session-001",
        "status": status,
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2,
        "page_order": ["page-1", "page-2"],
        "source": "capture_session",
    }
    task.update(overrides)
    JsonStore(str(tmp_path)).write(f"tasks/{task_id}.json", task)
    return task


class TestTaskServiceQueries:
    def test_legacy_task_stub_is_normalized(self, tmp_path):
        write_task(tmp_path)
        service = make_service(tmp_path)

        task = service.get_task("task-001")

        assert task["error_code"] is None
        assert task["error_message"] is None
        assert task["failed_at"] is None
        assert task["processing_at"] is None
        assert task["ready_at"] is None
        assert task["page_summary"] == {"page_count": 2, "page_order": ["page-1", "page-2"]}
        assert task["document_summary"] is None
        assert task["review_summary"] == {
            "status": None,
            "unreviewed_count": None,
            "suspicious_count": None,
        }
        assert task["export_summary"] == {"last_exported_at": None, "formats": []}
        assert task["status_history"] == [
            {
                "from_status": None,
                "to_status": "uploaded",
                "changed_at": "2026-05-12T10:00:00+00:00",
                "reason": "采集会话完成采集",
            }
        ]

    def test_list_tasks_returns_all_when_no_filter(self, tmp_path):
        write_task(tmp_path, task_id="task-b", status="failed")
        write_task(tmp_path, task_id="task-a", status="uploaded")
        service = make_service(tmp_path)

        tasks = service.list_tasks()

        assert [task["task_id"] for task in tasks] == ["task-a", "task-b"]
        assert tasks[0] == {
            "task_id": "task-a",
            "session_id": "session-001",
            "status": "uploaded",
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 2,
        }

    def test_list_tasks_filters_by_status(self, tmp_path):
        write_task(tmp_path, task_id="task-1", status="uploaded")
        write_task(tmp_path, task_id="task-2", status="failed")
        service = make_service(tmp_path)

        tasks = service.list_tasks(status="failed")

        assert [task["task_id"] for task in tasks] == ["task-2"]

    def test_list_tasks_unknown_status_returns_empty_list(self, tmp_path):
        write_task(tmp_path, task_id="task-1", status="uploaded")
        service = make_service(tmp_path)

        assert service.list_tasks(status="unknown") == []

    def test_get_nonexistent_task_raises_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.get_task("missing")

        assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND.code


class TestTaskServiceTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("created", "uploading"),
            ("created", "failed"),
            ("uploading", "uploaded"),
            ("uploading", "failed"),
            ("uploaded", "processing"),
            ("uploaded", "failed"),
            ("processing", "ready_for_review"),
            ("processing", "failed"),
            ("failed", "processing"),
            ("ready_for_review", "confirmed"),
            ("ready_for_review", "processing"),
            ("ready_for_review", "failed"),
            ("confirmed", "exported"),
        ],
    )
    def test_valid_transitions_match_state_enums(self, tmp_path, current, target):
        service = make_service(tmp_path)
        service._validate_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("uploaded", "confirmed"),
            ("processing", "uploaded"),
            ("failed", "confirmed"),
            ("confirmed", "failed"),
            ("exported", "failed"),
        ],
    )
    def test_invalid_transitions_raise_invalid_transition(self, tmp_path, current, target):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service._validate_transition(current, target)

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
        assert exc_info.value.details == {"current": current, "target": target}

    def test_process_without_algorithm_marks_failed(self, tmp_path):
        write_task(tmp_path, status="uploaded")
        service = make_service(tmp_path)

        result = service.process("task-001")

        assert result["status"] == "failed"
        assert result["processing_at"] is not None
        assert result["failed_at"] is not None
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["error_message"] == "算法模块未配置"
        assert [entry["to_status"] for entry in result["status_history"]] == [
            "uploaded",
            "processing",
            "failed",
        ]

    def test_process_invalid_state_raises_invalid_transition(self, tmp_path):
        write_task(tmp_path, status="confirmed")
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.process("task-001")

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code

    def test_retry_without_algorithm_marks_failed_again(self, tmp_path):
        write_task(
            tmp_path,
            status="failed",
            error_code="ALGORITHM_MODULE_FAILED",
            error_message="旧错误",
            failed_at="2026-05-12T10:01:00+00:00",
            status_history=[
                {
                    "from_status": None,
                    "to_status": "uploaded",
                    "changed_at": "2026-05-12T10:00:00+00:00",
                    "reason": "采集会话完成采集",
                },
                {
                    "from_status": "processing",
                    "to_status": "failed",
                    "changed_at": "2026-05-12T10:01:00+00:00",
                    "reason": "旧错误",
                },
            ],
        )
        service = make_service(tmp_path)

        result = service.retry("task-001")

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["error_message"] == "算法模块未配置"
        assert result["status_history"][-2]["from_status"] == "failed"
        assert result["status_history"][-2]["to_status"] == "processing"
        assert result["status_history"][-1]["from_status"] == "processing"
        assert result["status_history"][-1]["to_status"] == "failed"

    def test_mark_ready_sets_ready_at(self, tmp_path):
        write_task(tmp_path, status="processing")
        service = make_service(tmp_path)

        result = service.mark_ready("task-001")

        assert result["status"] == "ready_for_review"
        assert result["ready_at"] is not None

    def test_mark_failed_saves_error_info(self, tmp_path):
        write_task(tmp_path, status="processing")
        service = make_service(tmp_path)

        result = service.mark_failed("task-001", "ALGORITHM_MODULE_FAILED", "算法模块异常")

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["error_message"] == "算法模块异常"
        assert result["failed_at"] is not None

    def test_mark_confirmed_and_exported(self, tmp_path):
        write_task(tmp_path, status="ready_for_review")
        service = make_service(tmp_path)

        confirmed = service.mark_confirmed("task-001")
        exported = service.mark_exported("task-001")

        assert confirmed["status"] == "confirmed"
        assert exported["status"] == "exported"
