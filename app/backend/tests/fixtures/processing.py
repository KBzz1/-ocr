"""Simulated processing helpers for MVP E2E tests.

These helpers model external algorithm results for tests only. They do not
implement OCR, document parsing, field extraction, image processing, or rules.
"""

from typing import Literal

from app.backend.errors import ErrorCode
from app.backend.services.export_service import ExportService
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore

SimulatedMode = Literal["success", "module_failed", "empty_fields", "invalid_contract"]


class SimulatedProcessing:
    def __init__(self, store: JsonStore, mode: SimulatedMode = "success"):
        self._store = store
        self._mode = mode

    def run(self, task: dict, task_service: TaskService, schema: dict | None = None) -> dict:
        task_id = task["task_id"]
        if self._mode == "success":
            self._write_success_results(task_id, task, schema=schema)
            return task_service.mark_ready(task_id)
        if self._mode == "module_failed":
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "模拟算法异常",
                stage="field_extraction",
                details={"reason": "simulated_module_failure"},
            )
        if self._mode in ("empty_fields", "invalid_contract"):
            return self._fail_with_candidates(
                task_id, task_service, mode=self._mode
            )
        raise AssertionError(f"unknown simulated processing mode: {self._mode}")

    def _fail_with_candidates(self, task_id: str, task_service: TaskService, mode: str) -> dict:
        candidates = [] if mode == "empty_fields" else [{"field_key": ""}]
        message = "模拟结构化字段为空" if mode == "empty_fields" else "模拟结构化字段契约非法"
        reason = "empty_candidates" if mode == "empty_fields" else "invalid_candidate_contract"
        self._store.write(
            f"results/{task_id}/field_candidates.json",
            {"task_id": task_id, "stage": "field_extraction", "status": "success", "candidates": candidates},
        )
        return task_service.mark_failed(
            task_id,
            ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
            message,
            stage="field_extraction",
            details={"reason": reason},
        )

    def _write_success_results(self, task_id: str, task: dict, schema: dict | None) -> None:
        images = task.get("images") or []
        pages = [
            {
                "page_id": image["page_id"],
                "page_no": image["page_no"],
                "parsed_text": f"第{image['page_no']}页模拟 OCR 文本",
            }
            for image in images
        ]
        self._store.write(
            f"results/{task_id}/document_result.json",
            {
                "task_id": task_id,
                "stage": "document_parsing",
                "status": "success",
                "pages": pages,
                "merged_text": "模拟 OCR 合并文本",
            },
        )
        self._store.write(
            f"results/{task_id}/field_candidates.json",
            {
                "task_id": task_id,
                "stage": "field_extraction",
                "status": "success",
                "schema_version": (schema or {}).get("version"),
                "candidates": [
                    {
                        "field_key": "chief_complaint",
                        "field_name": "主诉",
                        "original_value": "模拟外部算法返回的主诉",
                        "evidence": "fixture evidence",
                        "page_no": 1,
                        "confidence": "medium",
                    }
                ],
            },
        )


def install_simulated_processing(app, mode: SimulatedMode = "success") -> TaskService:
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task_service = TaskService(
        store=store,
        orchestrator=SimulatedProcessing(store, mode=mode),
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    app.config["TASK_SERVICE"] = task_service
    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=task_service,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    app.config["EXPORT_SERVICE"] = ExportService(
        store=store,
        export_dir=app.config["BACKEND_CONFIG"]["export_dir"],
        task_service=task_service,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    return task_service
