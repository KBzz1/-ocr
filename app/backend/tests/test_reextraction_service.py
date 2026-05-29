import pytest

from app.backend.enums import FieldStatus
from app.backend.errors import AppError, ErrorCode
from app.backend.services.reextraction_service import ReextractionService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class FakeFieldPort:
    def __init__(self):
        self.inputs = []

    def extract(self, input):
        self.inputs.append(input)
        return [
            {
                "field_key": "patient_name",
                "original_value": "张三",
                "evidence": "姓名：张三",
                "confidence": 0.9,
                "source_hint": "基本信息",
                "source_text": "姓名：张三",
                "source_section": "基本信息",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }
        ]


def schema():
    return {
        "version": "copd.v1",
        "document_type": "copd_admission_record",
        "field_groups": [
            {"group_key": "basic", "group_label": "基本信息", "fields": [{"field_key": "patient_name", "label": "姓名"}]}
        ],
    }


def make_service(tmp_path, field_port=None):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    port = field_port or FakeFieldPort()
    service = ReextractionService(
        store=store,
        task_service=task_service,
        field_port=port,
        schema_provider=schema,
        prompt_version_provider=lambda: "copd.prompt.v1",
    )
    return service, store, task_service, port


def write_task(store, status="review"):
    store.write(
        "tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": status,
            "created_at": "2026-05-29T10:00:00+00:00",
            "updated_at": "2026-05-29T10:00:00+00:00",
            "upload_token": "token",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )


def write_document_result(store):
    store.write(
        "results/task_001/document_result.json",
        {
            "task_id": "task_001",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "姓名：张三",
            "pages": [{"page_id": "page_001", "page_no": 1, "text": "姓名：张三"}],
        },
    )


def write_existing_review(store):
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "old",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "auto_value": "李四",
                    "final_value": "人工改过",
                    "status": FieldStatus.MODIFIED.value,
                }
            ],
        },
    )


def test_reextract_uses_saved_document_text_and_records_versions(tmp_path):
    service, store, _task_service, port = make_service(tmp_path)
    write_task(store, status="review")
    write_document_result(store)
    write_existing_review(store)

    result = service.reextract("task_001")

    assert port.inputs[0]["document_result"]["merged_text"] == "姓名：张三"
    assert port.inputs[0]["source"] == "ocr_text_only"
    assert result["schema_version"] == "copd.v1"
    assert result["prompt_version"] == "copd.prompt.v1"
    wrapper = store.read("results/task_001/field_candidates.json")
    assert wrapper["metadata"]["source"] == "ocr_text_only"
    assert wrapper["metadata"]["schema_version"] == "copd.v1"
    assert wrapper["metadata"]["prompt_version"] == "copd.prompt.v1"
    assert wrapper["candidates"][0]["original_value"] == "张三"
    review = store.read("results/task_001/review_result.json")
    assert review["fields"][0]["final_value"] == "人工改过"
    assert store.read(f"results/task_001/reextract_runs/{result['run_id']}.json")["candidate_count"] == 1


def test_reextract_done_task_reopens_review(tmp_path):
    service, store, task_service, _port = make_service(tmp_path)
    write_task(store, status="done")
    write_document_result(store)

    result = service.reextract("task_001")

    assert result["status"] == "review"
    assert task_service.get_task("task_001")["status"] == "review"


def test_reextract_requires_saved_ocr_text(tmp_path):
    service, store, _task_service, _port = make_service(tmp_path)
    write_task(store, status="review")

    with pytest.raises(AppError) as exc:
        service.reextract("task_001")

    assert exc.value.code == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code


def test_reextract_maps_invalid_candidate_contract_to_reextract_error(tmp_path):
    class InvalidFieldPort:
        def extract(self, input):
            return [
                {
                    "field_key": "patient_name",
                    "original_value": "张三",
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": "invalid",
                    "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                }
            ]

    service, store, _task_service, _port = make_service(tmp_path, field_port=InvalidFieldPort())
    write_task(store, status="review")
    write_document_result(store)

    with pytest.raises(AppError) as exc:
        service.reextract("task_001")

    assert exc.value.code == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code
    assert exc.value.details["reason"] == "invalid_candidate_contract"
