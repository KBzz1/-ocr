"""Task 4: 任务归属修改、改绑、记录类型重新处理。

PATCH /api/tasks/{task_id}/metadata 服务层契约测试。
"""
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class StubPatientService:
    def __init__(self):
        self._patients = {
            "P-A1B2C3D4": {"patient_id": "P-A1B2C3D4", "name": "测试用例", "deleted_at": None},
            "P-E5F6A7B8": {"patient_id": "P-E5F6A7B8", "name": "测试病例", "deleted_at": None},
            "P-DELETED1": {"patient_id": "P-DELETED1", "name": "测试已删除", "deleted_at": "2026-06-07T10:00:00+00:00"},
        }

    def get_bindable(self, patient_id):
        record = self._patients.get(patient_id)
        if record is None:
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        if record.get("deleted_at"):
            raise AppError(ErrorCode.PATIENT_DELETED)
        return record


class FakeDocumentProfiles:
    def __init__(self):
        self.default_document_type = "copd_admission_record"

    def get_default_document_type(self):
        return self.default_document_type

    def get_profile(self, document_type):
        return type("Profile", (), {
            "document_type": document_type,
            "schema": {
                "version": f"{document_type}.v1",
                "document_type": document_type,
                "field_groups": [],
            },
            "prompt_version": f"{document_type}.prompt.v1",
            "field_port": object(),
        })()

    def to_task_document_summary(self, document_type):
        labels = {
            "copd_admission_record": "入院记录",
            "progress_note": "病程记录",
        }
        return {
            "document_type": document_type,
            "document_type_label": labels.get(document_type, document_type),
            "schema_version": f"{document_type}.v1",
            "prompt_version": f"{document_type}.prompt.v1",
            "extraction_profile": document_type,
        }


class RecordingOrchestrator:
    def __init__(self):
        self.calls = []

    def run(self, task, task_service, schema=None):
        self.calls.append((task["task_id"], task.get("document_type"), schema))
        return task_service.mark_ready(task["task_id"])


def make_service(tmp_path, *, orchestrator=None, document_profiles=None):
    return TaskService(
        store=JsonStore(str(tmp_path)),
        orchestrator=orchestrator,
        schema_provider=lambda: {"version": "copd.v1", "document_type": "copd_admission_record"},
        background_runner=lambda task_id, run: run(),
        patient_service=StubPatientService(),
        document_profiles=document_profiles,
    )


def write_task(tmp_path, task_id="1", status="uploading", **overrides):
    base = {
        "task_id": task_id,
        "status": status,
        "created_at": "2026-06-07T10:00:00+00:00",
        "updated_at": "2026-06-07T10:00:00+00:00",
        "upload_token": "token_001",
        "images": [],
        "error_code": None,
        "error_message": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        "patient_id": "P-A1B2C3D4",
        "patient_snapshot": {"patient_id": "P-A1B2C3D4", "name": "测试用例"},
        "record_date": "2026-06-07",
        "record_time": None,
        "deleted_at": None,
        "metadata_history": [],
        "document_type": "copd_admission_record",
        "document_type_label": "入院记录",
        "schema_version": "copd_admission_record.v1",
        "prompt_version": "copd_admission_record.prompt.v1",
        "extraction_profile": "copd_admission_record",
    }
    base.update(overrides)
    JsonStore(str(tmp_path)).write(f"tasks/{task_id}.json", base)
    return base


def test_update_metadata_rejects_processing_task(tmp_path):
    write_task(tmp_path, status="processing")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.update_metadata("1", patient_id="P-E5F6A7B8")

    assert exc.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
    assert exc.value.details == {"current": "processing", "target": "metadata_change"}


def test_update_metadata_rejects_empty_payload(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.update_metadata("1")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_update_metadata_rejects_unknown_task(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.update_metadata("missing", patient_id="P-A1B2C3D4")

    assert exc.value.code == ErrorCode.TASK_NOT_FOUND.code


def test_rebind_patient_preserves_images_and_review_results(tmp_path):
    store = JsonStore(str(tmp_path))
    write_task(
        tmp_path,
        status="review",
        images=[{"page_id": "p1", "page_no": 1, "original_image_path": "/tmp/p1.jpg"}],
    )
    store.write(
        "results/1/review_result.json",
        {
            "task_id": "1",
            "schema_version": "copd.v1",
            "fields": [{"field_key": "occupation", "final_value": "教师"}],
        },
    )
    service = make_service(tmp_path)

    updated = service.update_metadata("1", patient_id="P-E5F6A7B8")

    assert updated["patient_id"] == "P-E5F6A7B8"
    assert updated["patient_snapshot"] == {"patient_id": "P-E5F6A7B8", "name": "测试病例"}
    assert updated["status"] == "review"
    assert updated["images"] == [{"page_id": "p1", "page_no": 1, "original_image_path": "/tmp/p1.jpg"}]
    assert store.read("results/1/review_result.json") == {
        "task_id": "1",
        "schema_version": "copd.v1",
        "fields": [{"field_key": "occupation", "final_value": "教师"}],
    }


def test_update_metadata_changes_record_date_and_time_in_uploading(tmp_path):
    write_task(tmp_path, status="uploading")
    service = make_service(tmp_path)

    updated = service.update_metadata("1", record_date="2026-07-01", record_time="14:00")

    assert updated["record_date"] == "2026-07-01"
    assert updated["record_time"] == "14:00"
    assert updated["status"] == "uploading"


def test_update_metadata_rejects_deleted_patient(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.update_metadata("1", patient_id="P-DELETED1")

    assert exc.value.code == ErrorCode.PATIENT_DELETED.code


def test_update_metadata_rejects_invalid_record_date(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    with pytest.raises(AppError) as exc:
        service.update_metadata("1", record_date="2026-13-45")

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_update_metadata_appends_history_entries_with_exact_shape(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)

    updated = service.update_metadata("1", patient_id="P-E5F6A7B8", record_date="2026-08-01")

    history = JsonStore(str(tmp_path)).read("tasks/1.json")["metadata_history"]
    keys = {entry["field"] for entry in history}
    assert keys == {"patient_id", "record_date"}
    for entry in history:
        assert set(entry.keys()) == {"field", "from_value", "to_value", "changed_at"}


def test_get_task_does_not_expose_metadata_history(tmp_path):
    write_task(tmp_path, status="review")
    service = make_service(tmp_path)
    service.update_metadata("1", patient_id="P-E5F6A7B8")

    task = service.get_task("1")
    [summary] = service.list_tasks()

    assert "metadata_history" not in task
    assert "metadata_history" not in summary


def test_change_document_type_in_uploading_does_not_trigger_processing(tmp_path):
    write_task(tmp_path, status="uploading")
    orchestrator = RecordingOrchestrator()
    service = make_service(tmp_path, orchestrator=orchestrator, document_profiles=FakeDocumentProfiles())

    updated = service.update_metadata("1", document_type="progress_note")

    assert updated["status"] == "uploading"
    assert updated["document_type"] == "progress_note"
    assert updated["document_type_label"] == "病程记录"
    assert orchestrator.calls == []


def test_change_document_type_after_review_reuses_ocr_and_reextracts_fields(tmp_path):
    """处理后修改 document_type:复用已保存 OCR 文本,只重新走 field 抽取。"""
    store = JsonStore(str(tmp_path))
    write_task(tmp_path, status="review", images=[{"page_id": "p1", "page_no": 1, "original_image_path": "/tmp/p1.jpg"}])
    store.write(
        "results/1/document_result.json",
        {
            "task_id": "1",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "姓名：张三",
            "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "姓名：张三"}],
        },
    )
    store.write(
        "results/1/review_result.json",
        {
            "task_id": "1",
            "schema_version": "copd.v1",
            "fields": [{"field_key": "occupation", "final_value": "教师"}],
        },
    )

    class DocOnlyOrchestrator:
        def __init__(self):
            self.doc_calls = 0
            self.field_calls = 0
            self.last_document_type = None

        def run(self, task, task_service, schema=None):
            # 模拟真实 orchestrator:遇到成功 document_result 跳过 doc 解析,
            # 仅跑 field 抽取并 mark_ready。
            from app.backend.services.algorithm_ports.results import AlgorithmResultStore
            doc = AlgorithmResultStore(store).read_success_document_result(task["task_id"])
            if doc is None:
                self.doc_calls += 1
            self.field_calls += 1
            self.last_document_type = task.get("document_type")
            return task_service.mark_ready(task["task_id"])

    orchestrator = DocOnlyOrchestrator()
    service = make_service(tmp_path, orchestrator=orchestrator, document_profiles=FakeDocumentProfiles())

    updated = service.update_metadata("1", document_type="progress_note")

    assert updated["status"] in ("processing", "review")
    assert updated["document_type"] == "progress_note"
    assert updated["schema_version"] == "progress_note.v1"
    assert orchestrator.doc_calls == 0
    assert orchestrator.field_calls == 1
    assert orchestrator.last_document_type == "progress_note"
    # 旧 review_result.json 必须被归档,不能继续影响新审核
    assert not store.exists("results/1/review_result.json")
    # 归档应位于 record_type_change_archive 子目录下
    archived = store.list_json("results/1/record_type_change_archive")
    assert len(archived) == 1
    assert archived[0]["fields"][0]["field_key"] == "occupation"


def test_change_document_type_missing_ocr_rejected_without_modifying_task(tmp_path):
    write_task(tmp_path, status="review")
    store = JsonStore(str(tmp_path))
    store.write(
        "results/1/review_result.json",
        {"task_id": "1", "schema_version": "copd.v1", "fields": [{"field_key": "occupation"}]},
    )
    service = make_service(tmp_path, document_profiles=FakeDocumentProfiles())

    with pytest.raises(AppError) as exc:
        service.update_metadata("1", document_type="progress_note")

    assert exc.value.code == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code
    # 任务不应被修改
    persisted = store.read("tasks/1.json")
    assert persisted["document_type"] == "copd_admission_record"
    assert persisted["status"] == "review"
    # 旧 review 不应被归档/删除
    assert store.exists("results/1/review_result.json")


def test_change_document_type_blocked_by_active_reextract(tmp_path):
    write_task(tmp_path, status="review")
    store = JsonStore(str(tmp_path))
    store.write(
        "results/1/document_result.json",
        {
            "task_id": "1",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "x",
            "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "x"}],
        },
    )
    store.write(
        "results/1/review_result.json",
        {"task_id": "1", "schema_version": "copd.v1", "fields": [{"field_key": "occupation"}]},
    )

    from app.backend.services.reextract_jobs import ReextractJobRegistry
    registry = ReextractJobRegistry()
    registry.register("1")

    service = make_service(tmp_path, document_profiles=FakeDocumentProfiles())

    with pytest.raises(AppError) as exc:
        service.update_metadata("1", document_type="progress_note", reextract_registry=registry)

    assert exc.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
    # review_result 应当保持不变
    persisted = store.read("results/1/review_result.json")
    assert persisted["fields"][0]["field_key"] == "occupation"


def test_update_metadata_in_done_state_preserves_review_results_when_only_rebinding(tmp_path):
    write_task(tmp_path, status="done")
    store = JsonStore(str(tmp_path))
    store.write(
        "results/1/review_result.json",
        {"task_id": "1", "fields": [{"field_key": "occupation", "final_value": "教师"}]},
    )
    service = make_service(tmp_path)

    updated = service.update_metadata("1", patient_id="P-E5F6A7B8")

    assert updated["status"] == "done"
    assert updated["patient_id"] == "P-E5F6A7B8"
    # 仅改绑不应影响 review 结果
    assert store.read("results/1/review_result.json")["fields"][0]["field_key"] == "occupation"
