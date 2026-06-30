"""Qwen batch processing orchestrator.

Bridges the Qwen batch adapter port to the task service / persistence layer.
Orchestrates a single Qwen batch job: cancellation checks, stage tracking,
GPU queue gating, persistence of document and field results, and failure
marking.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ...errors import ErrorCode
from ...storage.json_store import JsonStore

logger = logging.getLogger(__name__)


class QwenBatchProcessingOrchestrator:
    """Orchestrate a Qwen batch processing run for one task.

    Parameters
    ----------
    store:
        ``JsonStore`` instance used to persist intermediate results.
    batch_port:
        An object with a ``run(task: dict) -> dict`` method (typically
        ``QwenBatchAlgorithmPort``).
    schema_validator:
        Optional callable ``(candidates, schema)`` for post-extraction
        schema validation.  Not yet wired; reserved for future use.
    gpu_stage_queue:
        Optional GPU stage queue for serialising GPU-heavy stages across
        tasks.  Not yet wired; reserved for future use.
    """

    def __init__(
        self,
        store: JsonStore,
        batch_port: Any,
        schema_validator: Optional[Any] = None,
        gpu_stage_queue: Optional[Any] = None,
    ):
        self._store = store
        self._batch_port = batch_port
        self._schema_validator = schema_validator
        self._gpu_stage_queue = gpu_stage_queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: dict, task_service: Any, schema: dict | None = None) -> dict:
        """Execute the Qwen batch pipeline for *task*.

        Returns the result of ``task_service.mark_ready()`` on success or
        ``task_service.mark_failed()`` on failure.
        """
        task_id = task["task_id"]
        schema = schema or {}

        # 1. Cancellation check
        if self._is_cancelled(task_service, task_id):
            return task_service.get_task(task_id)

        # 2. Mark stage running
        task_service.mark_processing_stage(
            task_id, "qwen_batch_engine", "running"
        )

        # 3. (Optional) GPU stage hold - reserved
        # if self._gpu_stage_queue:
        #     with self._gpu_stage_queue.stage(task_id=task_id, stage="qwen_batch_engine"):
        #         batch_result = self._batch_port.run(task)

        # 4. Call batch port
        try:
            batch_result = self._batch_port.run(task)
        except Exception as exc:
            logger.exception("task=%s QwenBatchProcessingOrchestrator port exception", task_id)
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "Qwen批处理模块异常",
                stage="qwen_batch_engine",
                details={
                    "stage": "qwen_batch_engine",
                    "reason": "module_exception",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc)[:500],
                },
            )

        # 5. On failed result
        if batch_result.get("status") == "failed":
            error_info = batch_result.get("error", {})
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "Qwen批处理失败",
                stage="qwen_batch_engine",
                details={
                    "stage": "qwen_batch_engine",
                    "reason": error_info.get("reason", "batch_failed"),
                    "message": error_info.get("message", ""),
                },
            )

        # 6. Check document result
        document_result = batch_result.get("document_result", {})
        merged_text = document_result.get("merged_text", "")
        if not merged_text or not isinstance(merged_text, str) or not merged_text.strip():
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "Qwen批处理OCR文本为空",
                stage="qwen_batch_engine",
                details={"stage": "qwen_batch_engine", "reason": "empty_ocr_text"},
            )

        # 7. Check review fields
        review_fields = batch_result.get("review_fields")
        if not isinstance(review_fields, list) or not review_fields:
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "Qwen批处理字段结果为空",
                stage="qwen_batch_engine",
                details={"stage": "qwen_batch_engine", "reason": "empty_field_results"},
            )

        # 8. Persist document result
        self._store.write(
            f"results/{task_id}/document_result.json",
            document_result,
        )

        # 9. Persist field candidates
        self._store.write(
            f"results/{task_id}/field_candidates.json",
            {
                "candidates": review_fields,
                "schema_version": schema.get("version", ""),
                "document_type": schema.get("document_type", ""),
                "field_groups": schema.get("field_groups") if isinstance(schema.get("field_groups"), list) else None,
            },
        )

        # 10. Mark ready
        return task_service.mark_ready(task_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_cancelled(task_service: Any, task_id: str) -> bool:
        if not hasattr(task_service, "is_processing_cancelled"):
            return False
        return task_service.is_processing_cancelled(task_id)
