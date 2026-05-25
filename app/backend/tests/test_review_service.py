import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_services(tmp_path):
    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    schema = {
        "version": "medical_record.v1",
        "document_type": "medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "patient_name", "label": "姓名"},
                    {"field_key": "department", "label": "科室"},
                ],
            }
        ],
    }
    review_service = ReviewService(store, task_service, schema_provider=lambda: schema)
    return review_service, task_service, store


def write_review_task(store, task_id="task_001", status="review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )


def write_candidates(store, task_id="task_001"):
    store.write(
        f"results/{task_id}/field_candidates.json",
        {
            "task_id": task_id,
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "patient_name", "original_value": "张三", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "department", "original_value": "骨科", "evidence": "第1页", "confidence": 0.8},
            ],
        },
    )


def find_field(review, field_key):
    return next(field for field in review["fields"] if field["field_key"] == field_key)


def test_review_fields_preserve_extraction_metadata(tmp_path):
    """Task 10: each field must carry source_section, extraction_status,
    verification_status, quality_flags, and ocr_correction from the candidate."""
    store = JsonStore(str(tmp_path))

    # Minimal task service stub — only get_task is called
    class _TaskSvc:
        def get_task(self, task_id):
            return {
                "task_id": task_id,
                "status": "review",
                "schema_version": "1.0.0",
                "document_type": "copd_admission_record",
            }

    store.write("results/t1/field_candidates.json", {
        "candidates": [
            {
                "field_key": "bmi",
                "original_value": "24.2kg/m2",
                "evidence": "BHI:24.2kg/m2",
                "confidence": 0.78,
                "source_hint": "体格检查",
                "source_text": "体格检查：身高体重后记录 BHI:24.2kg/m2。",
                "source_group_id": "source_group_体格检查",
                "source_section": "体格检查",
                "extraction_status": "extracted",
                "verification_status": "suspicious",
                "quality_flags": [{"flag": "value_not_in_evidence", "severity": "warning", "message": "risk"}],
                "ocr_correction": {"applied": True, "raw": "BHI", "normalized": "BMI", "reason": "unit kg/m2"},
            }
        ]
    })
    schema = {
        "version": "1.0.0",
        "document_type": "copd_admission_record",
        "field_groups": [
            {"fields": [{"field_key": "bmi", "label": "BMI"}]}
        ],
    }
    service = ReviewService(store, _TaskSvc(), schema_provider=lambda: schema)

    review = service.get_or_init("t1")
    field = review["fields"][0]

    assert field["extraction_status"] == "extracted"
    assert field["verification_status"] == "suspicious"
    assert field["quality_flags"][0]["flag"] == "value_not_in_evidence"
    assert field["ocr_correction"]["normalized"] == "BMI"
    assert field["source_hint"] == "体格检查"
    assert field["source_text"] == "体格检查：身高体重后记录 BHI:24.2kg/m2。"
    assert field["source_group_id"] == "source_group_体格检查"
    assert field["source_section"] == "体格检查"
    assert review["source_groups"] == [
        {
            "source_group_id": "source_group_体格检查",
            "source_hint": "体格检查",
            "source_text": "体格检查：身高体重后记录 BHI:24.2kg/m2。",
            "field_keys": ["bmi"],
        }
    ]


def test_first_read_initializes_review_result_from_candidates(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.get_or_init("task_001")

    assert [field["field_key"] for field in review["fields"]] == ["patient_name", "department"]
    assert find_field(review, "patient_name")["status"] == "unreviewed"
    assert review["summary"]["unreviewed_count"] == 2
    assert review["summary"]["suspicious_count"] == 0
    assert review["summary"]["failed_verification_count"] == 0
    assert review["summary"]["not_found_count"] == 0


def test_review_save_rejects_legacy_field_status(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    with pytest.raises(AppError) as exc:
        review_service.update_field(
            "task_001",
            "patient_name",
            {"value": "张三", "status": "suspicious"},
        )

    assert exc.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code


def test_update_field_accepts_mvp_status_payload(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.update_field(
        "task_001",
        "patient_name",
        {"value": "李四", "status": "modified"},
    )

    field = find_field(review, "patient_name")
    assert field["final_value"] == "李四"
    assert field["status"] == "modified"
    assert review["summary"]["modified_count"] == 1


def test_save_bulk_fields_updates_review_result(tmp_path):
    review_service, _task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)

    review = review_service.save(
        "task_001",
        {
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "confirmed"},
                {"field_key": "department", "value": "骨外科", "status": "modified"},
            ]
        },
    )

    assert find_field(review, "patient_name")["status"] == "confirmed"
    assert find_field(review, "department")["final_value"] == "骨外科"
    assert review["summary"]["confirmed_count"] == 1
    assert review["summary"]["modified_count"] == 1


def test_confirm_review_marks_task_done(tmp_path):
    review_service, task_service, store = make_services(tmp_path)
    write_review_task(store)
    write_candidates(store)
    review_service.save(
        "task_001",
        {
            "fields": [
                {"field_key": "patient_name", "value": "张三", "status": "confirmed"},
                {"field_key": "department", "value": "骨科", "status": "confirmed"},
            ]
        },
    )

    task = review_service.confirm("task_001")

    assert task["status"] == "done"
    assert task["done_at"]
    assert task_service.get_task("task_001")["review_summary"]["confirmed_count"] == 2
