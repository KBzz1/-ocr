import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_review_service(tmp_path, schema=None):
    from app.backend.services.review_service import ReviewService

    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    if schema is None:
        schema = {
            "version": "medical_record.v1",
            "document_type": "medical_record",
            "field_groups": [
                {
                    "group_key": "history",
                    "group_label": "病史",
                    "fields": [
                        {"field_key": "chief_complaint", "label": "主诉"},
                        {"field_key": "diagnosis", "label": "初步诊断"},
                    ],
                }
            ],
        }
    return ReviewService(store, task_service, schema_provider=lambda: schema), store


def write_task(store, task_id="task-001", status="ready_for_review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "session_id": "session-001",
            "status": status,
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 2,
            "page_order": ["page-1", "page-2"],
            "source": "capture_session",
            "schema_version": "medical_record.v1",
            "document_type": "medical_record",
        },
    )


def write_candidates(store, task_id="task-001", candidates=None):
    if candidates is None:
        candidates = [
            {
                "field_key": "chief_complaint",
                "original_value": "头痛3天",
                "field_name": "主诉",
                "evidence": "第1页第2行",
                "page_no": 1,
                "confidence": 0.95,
            },
            {
                "field_key": "diagnosis",
                "original_value": "上呼吸道感染",
                "field_name": "初步诊断",
                "evidence": "第2页",
                "page_no": 2,
                "confidence": 0.8,
            },
        ]
    store.write(
        f"results/{task_id}/field_candidates.json",
        {"task_id": task_id, "stage": "field_extraction", "status": "success", "candidates": candidates},
    )


def find_field(review, field_key):
    return next(field for field in review["fields"] if field["field_key"] == field_key)


class TestReviewServiceRead:
    def test_first_read_initializes_review_result_from_candidates(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)

        review = service.get_or_init("task-001")

        assert review["task_id"] == "task-001"
        assert review["schema_version"] == "medical_record.v1"
        assert review["document_type"] == "medical_record"
        assert review["initialized_at"]
        assert review["updated_at"]
        assert [f["field_key"] for f in review["fields"]] == ["chief_complaint", "diagnosis"]

        field = find_field(review, "chief_complaint")
        assert field["field_name"] == "主诉"
        assert field["auto_value"] == "头痛3天"
        assert field["final_value"] == "头痛3天"
        assert field["status"] == "unreviewed"
        assert field["empty_accepted"] is False
        assert field["history"] == []

        assert review["summary"]["total_count"] == 2
        assert review["summary"]["unreviewed_count"] == 2
        assert review["summary"]["missing_evidence_count"] == 0

    def test_second_read_does_not_overwrite_manual_result(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        review = service.get_or_init("task-001")
        find_field(review, "chief_complaint")["final_value"] = "人工修正"
        find_field(review, "chief_complaint")["status"] = "modified"
        store.write("results/task-001/review_result.json", review)

        reopened = service.get_or_init("task-001")

        assert find_field(reopened, "chief_complaint")["final_value"] == "人工修正"
        assert find_field(reopened, "chief_complaint")["status"] == "modified"

    def test_auto_candidate_file_is_not_modified(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)

        service.get_or_init("task-001")

        candidates = store.read("results/task-001/field_candidates.json")
        assert candidates["candidates"][0]["original_value"] == "头痛3天"

    def test_missing_candidates_returns_review_validation_failed(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code

    def test_empty_candidates_returns_review_validation_failed(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store, candidates=[])

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code

    def test_non_reviewable_task_cannot_read(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store, status="failed")
        write_candidates(store)

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
