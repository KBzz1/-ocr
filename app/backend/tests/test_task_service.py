import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def run(self, task, task_service, schema=None):
        self.calls.append((task["task_id"], schema))
        task_service.mark_processing_stage(task["task_id"], "document_parsing", "running", page_count=1)
        return task_service.get_task(task["task_id"])


class CancellationAwareOrchestrator:
    def __init__(self):
        self.calls = []

    def run(self, task, task_service, schema=None):
        self.calls.append(task["task_id"])
        task_service.mark_ready(task["task_id"])
        return task_service.get_task(task["task_id"])


def make_service(tmp_path, orchestrator=None, schema_provider=None):
    return TaskService(
        JsonStore(str(tmp_path)),
        orchestrator=orchestrator,
        schema_provider=schema_provider,
        background_runner=lambda run: run(),
    )


def write_task(tmp_path, task_id="1", status="uploading", **overrides):
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

    assert task["task_id"] == "1"
    assert task["display_name"] == "1"
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
        task_id="2",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(tmp_path, task_id="3", status="failed")

    summaries = service.list_tasks()

    assert [summary["task_id"] for summary in summaries] == ["2", "3"]
    assert service.list_tasks(status="uploading")[0]["task_id"] == "2"


def test_get_task_normalizes_mvp_shape(tmp_path):
    write_task(
        tmp_path,
        images=[{"page_id": "page_001", "page_no": 1}],
        review_summary=None,
    )
    service = make_service(tmp_path)

    task = service.get_task("1")

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

    result = service.process("1")
    persisted = service.get_task("1")

    assert result["status"] == "processing"
    assert result["processing_summary"]["stage"] == "queued"
    assert persisted["status"] == "failed"
    assert result["processing_at"] is not None
    assert persisted["failed_at"] is not None
    assert persisted["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    assert persisted["error_message"] == "图像处理模块未配置"
    assert persisted["details"]["stage"] == "image_processing"
    assert persisted["details"]["reason"] == "module_not_configured"
    assert [entry["to_status"] for entry in persisted["status_history"]] == [
        "uploading",
        "processing",
        "failed",
    ]


def test_finish_upload_returns_processing_after_dispatching_background_run(tmp_path):
    write_task(
        tmp_path,
        images=[{"page_id": "page_001", "page_no": 1, "original_image_path": "/tmp/page.jpg"}],
    )
    orchestrator = RecordingOrchestrator()
    service = make_service(tmp_path, orchestrator=orchestrator, schema_provider=lambda: {"version": "1.0.0"})

    result = service.finish_upload("1")
    summary = service.list_tasks()[0]

    assert result["status"] == "processing"
    assert result["processing_summary"]["stage"] == "queued"
    assert result["processing_summary"]["progress_percent"] == 5
    assert orchestrator.calls == [("1", {"version": "1.0.0"})]
    assert summary["processing_summary"]["stage"] == "document_parsing"
    assert summary["processing_summary"]["progress_percent"] == 55


def test_field_extraction_stage_label_describes_llm_structuring(tmp_path):
    write_task(tmp_path, status="processing", processing_at="2026-05-19T10:00:00+00:00")
    service = make_service(tmp_path)

    updated = service.mark_processing_stage("1", "field_extraction", "running", page_count=1)

    assert updated["processing_summary"]["label"] == "正在利用LLM结构化提取"


def test_cancel_processing_marks_failed_and_releases_queued_run(tmp_path):
    pending = []

    def queue_runner(run):
        pending.append(run)

    write_task(
        tmp_path,
        task_id="1",
        images=[{"page_id": "page_001", "page_no": 1, "original_image_path": "/tmp/page-1.jpg"}],
    )
    orchestrator = CancellationAwareOrchestrator()
    service = TaskService(
        JsonStore(str(tmp_path)),
        orchestrator=orchestrator,
        background_runner=queue_runner,
    )

    started = service.finish_upload("1")
    cancelled = service.cancel_processing("1")
    pending[0]()
    persisted = service.get_task("1")

    assert started["status"] == "processing"
    assert cancelled["status"] == "failed"
    assert cancelled["error_code"] == "TASK_PROCESSING_CANCELLED"
    assert cancelled["error_message"] == "用户取消处理"
    assert persisted["status"] == "failed"
    assert orchestrator.calls == []
    assert [entry["to_status"] for entry in persisted["status_history"]] == [
        "uploading",
        "processing",
        "failed",
    ]


def test_cancel_processing_rejects_non_processing_task(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.cancel_processing("1")

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
    assert exc_info.value.details == {"current": "review", "target": "failed"}


def test_background_runner_can_serialize_processing_callbacks(tmp_path):
    pending = []

    def queue_runner(run):
        pending.append(run)

    write_task(
        tmp_path,
        task_id="1",
        images=[{"page_id": "page_001", "page_no": 1, "original_image_path": "/tmp/page-1.jpg"}],
    )
    write_task(
        tmp_path,
        task_id="2",
        images=[{"page_id": "page_001", "page_no": 1, "original_image_path": "/tmp/page-2.jpg"}],
    )
    orchestrator = RecordingOrchestrator()
    service = TaskService(
        JsonStore(str(tmp_path)),
        orchestrator=orchestrator,
        schema_provider=lambda: {"version": "1.0.0"},
        background_runner=queue_runner,
    )

    service.finish_upload("1")
    service.finish_upload("2")

    assert len(pending) == 2
    assert orchestrator.calls == []
    pending[0]()
    assert orchestrator.calls == [("1", {"version": "1.0.0"})]
    pending[1]()
    assert orchestrator.calls == [
        ("1", {"version": "1.0.0"}),
        ("2", {"version": "1.0.0"}),
    ]


def test_process_invalid_state_raises_invalid_transition(tmp_path):
    write_task(tmp_path, status="done")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.mark_failed("1", "ALGORITHM_MODULE_FAILED", "算法模块异常")

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code


def test_reopen_review_transitions_done_to_review(tmp_path):
    write_task(tmp_path, status="done")
    service = make_service(tmp_path)

    task = service.reopen_review("1")

    assert task["status"] == "review"


def test_reopen_review_rejects_non_done_task(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.reopen_review("1")

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code


def test_rename_task_updates_display_name(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    task = service.rename_task("1", "张三入院记录")

    assert task["display_name"] == "张三入院记录"
    persisted = service.get_task("1")
    assert persisted["display_name"] == "张三入院记录"

    summary = service.list_tasks()[0]
    assert summary["display_name"] == "张三入院记录"
    assert summary["task_id"] == "1"


def test_delete_task_removes_from_store(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    result = service.delete_task("1")

    assert result["task_id"] == "1"
    assert service.list_tasks() == []
    with pytest.raises(AppError) as exc_info:
        service.get_task("1")
    assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND.code


def test_delete_task_rejects_processing_status(tmp_path):
    write_task(tmp_path, status="processing")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.delete_task("1")

    assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code


def test_delete_task_nonexistent_raises_not_found(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc_info:
        service.delete_task("missing")

    assert exc_info.value.code == ErrorCode.TASK_NOT_FOUND.code


@pytest.mark.parametrize("status", ["uploading", "review", "done", "failed"])
def test_delete_task_works_for_non_processing_statuses(tmp_path, status):
    write_task(tmp_path, status=status)
    service = make_service(tmp_path)

    result = service.delete_task("1")

    assert result["task_id"] == "1"
    assert service.list_tasks() == []


class FakeDocumentProfiles:
    def __init__(self):
        self.remembered = []
        self.default_document_type = "copd_admission_record"

    def get_default_document_type(self):
        return self.default_document_type

    def to_task_document_summary(self, document_type):
        return {
            "document_type": document_type,
            "document_type_label": "入院记录" if document_type == "copd_admission_record" else "病程记录",
            "schema_version": f"{document_type}.v1",
            "prompt_version": f"{document_type}.prompt.v1",
            "extraction_profile": document_type,
        }

    def remember_last_document_type(self, document_type):
        self.remembered.append(document_type)


def test_create_task_uses_last_document_type_default(tmp_path):
    profiles = FakeDocumentProfiles()
    profiles.default_document_type = "progress_note"
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)

    task = service.create_uploading_task("http://127.0.0.1:8081")

    assert task["document_type"] == "progress_note"
    assert task["schema_version"] == "progress_note.v1"
    assert task["prompt_version"] == "progress_note.prompt.v1"


def test_change_document_type_updates_uploading_task_and_default(tmp_path):
    profiles = FakeDocumentProfiles()
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)
    task = service.create_uploading_task("http://127.0.0.1:8081")

    updated = service.change_document_type(task["task_id"], "progress_note")

    assert updated["document_type"] == "progress_note"
    assert updated["schema_version"] == "progress_note.v1"
    assert profiles.remembered == ["progress_note"]


def test_change_document_type_rejects_non_uploading_task(tmp_path):
    profiles = FakeDocumentProfiles()
    service = TaskService(JsonStore(str(tmp_path)), document_profiles=profiles)
    task = service.create_uploading_task("http://127.0.0.1:8081")
    persisted = service.get_task(task["task_id"])
    persisted["status"] = "processing"
    JsonStore(str(tmp_path)).write(f"tasks/{task['task_id']}.json", persisted)

    with pytest.raises(AppError) as exc:
        service.change_document_type(task["task_id"], "progress_note")

    assert exc.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
