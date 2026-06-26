"""Tests for QwenBatchProcessingOrchestrator -- orchestrates Qwen batch pipeline."""

from app.backend.services.algorithm_ports.qwen_batch_orchestrator import (
    QwenBatchProcessingOrchestrator,
)
from app.backend.storage.json_store import JsonStore


class TaskService:
    def __init__(self):
        self.failed = None
        self.ready = False
        self.stages = []

    def mark_processing_stage(self, task_id, stage, status, page_count=None):
        self.stages.append((stage, status, page_count))

    def mark_ready(self, task_id):
        self.ready = True
        return {"task_id": task_id, "status": "review"}

    def mark_failed(self, task_id, code, message, stage=None, details=None):
        self.failed = {"code": code, "message": message, "stage": stage, "details": details}
        return {"task_id": task_id, "status": "failed", "error_code": code}

    def is_processing_cancelled(self, task_id):
        return False


def _candidate():
    return {
        "field_key": "chief_complaint",
        "original_value": "咳嗽",
        "evidence": [
            {"id": "s1-s1", "text": "主诉：咳嗽", "start_offset": 0, "end_offset": 5}
        ],
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    }


def test_qwen_batch_orchestrator_persists_document_and_fields(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {
                "status": "success",
                "document_result": {
                    "merged_text": "主诉：咳嗽",
                    "pages": [
                        {
                            "page_id": "p1",
                            "page_no": 1,
                            "status": "success",
                            "text": "主诉：咳嗽",
                        }
                    ],
                },
                "review_fields": [_candidate()],
            }

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run(
        {
            "task_id": "task_001",
            "images": [
                {"page_id": "p1", "page_no": 1, "original_image_path": "/tmp/p1.jpg"}
            ],
        },
        service,
        schema={"version": "qwen_batch_admission_record.v1"},
    )

    assert result["status"] == "review"
    assert (
        store.read("results/task_001/document_result.json")["merged_text"]
        == "主诉：咳嗽"
    )
    assert (
        store.read("results/task_001/field_candidates.json")["candidates"][0][
            "field_key"
        ]
        == "chief_complaint"
    )


def test_qwen_batch_orchestrator_marks_failed_for_empty_ocr(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {
                "status": "success",
                "document_result": {"merged_text": "", "pages": []},
                "review_fields": [_candidate()],
            }

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run(
        {"task_id": "task_001", "images": []}, service, schema={}
    )

    assert result["status"] == "failed"
    assert service.failed["details"]["reason"] == "empty_ocr_text"


def test_qwen_batch_orchestrator_marks_failed_for_batch_error(tmp_path):
    store = JsonStore(str(tmp_path))

    class Port:
        def run(self, task):
            return {
                "status": "failed",
                "error": {"reason": "upstream_failed", "message": "runner failed"},
            }

    service = TaskService()
    orchestrator = QwenBatchProcessingOrchestrator(store=store, batch_port=Port())
    result = orchestrator.run(
        {"task_id": "task_001", "images": []}, service, schema={}
    )

    assert result["status"] == "failed"
    assert service.failed["details"]["reason"] == "upstream_failed"
