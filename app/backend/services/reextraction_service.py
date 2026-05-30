from datetime import datetime, timezone

from ..enums import TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore
from .algorithm_ports.field_extraction import all_fields_empty, validate_field_candidates


class ReextractionService:
    """Re-run field extraction from persisted OCR text only."""

    def __init__(
        self,
        store: JsonStore,
        task_service,
        field_port,
        schema_provider,
        schema_validator=None,
        prompt_version_provider=None,
        document_profiles=None,
    ):
        self._store = store
        self._task_service = task_service
        self._field_port = field_port
        self._schema_provider = schema_provider
        self._schema_validator = schema_validator
        self._prompt_version_provider = prompt_version_provider or (lambda: "")
        self._document_profiles = document_profiles

    def reextract(self, task_id: str) -> dict:
        task = self._task_service.get_task(task_id)
        if task["status"] not in (TaskStatus.REVIEW.value, TaskStatus.DONE.value):
            raise AppError(
                ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                message="只有待审核或已完成任务可以基于 OCR 文本重新抽取",
                details={"current": task["status"]},
            )

        document_result = self._load_ocr_document_result(task_id)

        profile = None
        if self._document_profiles is not None:
            profile = self._document_profiles.get_profile(task.get("document_type") or "copd_admission_record")
            schema = profile.schema
            field_port = profile.field_port
            prompt_version = profile.prompt_version
        else:
            schema = self._schema_provider() if self._schema_provider else {}
            field_port = self._field_port
            prompt_version = self._prompt_version_provider()

        if field_port is None:
            raise AppError(
                ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                message="字段抽取模块未配置，无法重新抽取",
                details={"reason": "field_port_not_configured"},
            )
        if not isinstance(schema, dict):
            raise AppError(
                ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                message="schema 缺失或非法，无法重新抽取",
                details={"reason": "schema_missing_or_invalid"},
            )

        candidates = field_port.extract(
            {
                "task_id": task_id,
                "document_result": document_result,
                "schema": schema,
                "source": "ocr_text_only",
                "document_type": task.get("document_type") or "copd_admission_record",
            }
        )
        if not isinstance(candidates, list) or not candidates or all_fields_empty(candidates):
            raise AppError(
                ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                message="重新抽取字段结果为空",
                details={"reason": "empty_field_results"},
            )
        try:
            validate_field_candidates(candidates)
        except AppError as exc:
            raise AppError(
                ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                message="重新抽取字段候选结构非法",
                details={"reason": "invalid_candidate_contract", "validation_error": str(exc)},
            )
        if self._schema_validator:
            try:
                if hasattr(self._schema_validator, "validate"):
                    self._schema_validator.validate(candidates, schema)
                else:
                    self._schema_validator(candidates, schema)
            except Exception as exc:
                raise AppError(
                    ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                    message="重新抽取字段结果未通过 schema 校验",
                    details={"reason": "schema_validation_failed", "validation_error": str(exc)},
                )

        now = self._now()
        run_id = f"reextract_{now.replace(':', '').replace('-', '').replace('.', '')}"
        metadata = {
            "run_id": run_id,
            "source": "ocr_text_only",
            "schema_version": schema.get("version"),
            "prompt_version": prompt_version,
            "created_at": now,
        }
        self._store.write(
            f"results/{task_id}/field_candidates.json",
            {
                "task_id": task_id,
                "stage": "field_extraction",
                "status": "success",
                "candidates": candidates,
                "metadata": metadata,
            },
        )
        self._store.write(
            f"results/{task_id}/reextract_runs/{run_id}.json",
            {
                "task_id": task_id,
                **metadata,
                "candidate_count": len(candidates),
            },
        )

        if task["status"] == TaskStatus.DONE.value:
            task = self._task_service.reopen_review(task_id)

        return {
            "task_id": task_id,
            "status": task["status"],
            "candidate_count": len(candidates),
            **metadata,
        }

    def _load_ocr_document_result(self, task_id: str) -> dict:
        doc = self._store.read(f"results/{task_id}/document_result.json")
        if isinstance(doc, dict):
            merged_text = doc.get("merged_text")
            pages = doc.get("pages")
            if isinstance(merged_text, str) and merged_text.strip() and isinstance(pages, list) and pages:
                return {"merged_text": merged_text, "pages": pages}

        review = self._store.read(f"results/{task_id}/review_result.json")
        if isinstance(review, dict):
            ocr_text = review.get("ocr_text")
            pages = review.get("pages")
            if isinstance(ocr_text, str) and ocr_text.strip():
                return {"merged_text": ocr_text, "pages": pages if isinstance(pages, list) else []}
            if isinstance(pages, list):
                page_texts = [p.get("parsed_text", "") for p in pages if isinstance(p, dict)]
                merged = "\n".join(text for text in page_texts if isinstance(text, str) and text.strip())
                if merged.strip():
                    return {"merged_text": merged, "pages": pages}

        raise AppError(
            ErrorCode.REEXTRACTION_VALIDATION_FAILED,
            message="任务缺少已识别 OCR 文本，无法重新抽取",
            details={"reason": "ocr_text_missing"},
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
