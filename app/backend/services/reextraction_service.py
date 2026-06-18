from datetime import datetime, timezone
from threading import Event
from typing import Optional

from ..enums import FieldStatus, TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore
from ._review_field_factory import (
    append_reextract_history,
    build_field_from_candidate,
    build_placeholder_field,
    build_review_summary,
)
from .algorithm_ports.field_extraction import all_fields_empty, validate_field_candidates
from .algorithm_ports.evidence_units import build_evidence_units
from .algorithm_ports.results import AlgorithmResultStore


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

    def reextract(
        self,
        task_id: str,
        cancellation_token: Optional[Event] = None,
    ) -> dict:
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
            try:
                profile = self._document_profiles.get_profile(task.get("document_type") or "copd_admission_record")
            except AppError as exc:
                raise AppError(
                    ErrorCode.REEXTRACTION_VALIDATION_FAILED,
                    message="文书模板未注册或未完成接入，无法重新抽取",
                    details={
                        "reason": "document_type_not_registered",
                        "document_type": task.get("document_type"),
                        "error_code": exc.code,
                    },
                )
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

        evidence_units = self._load_evidence_units_for_reextract(document_result)

        candidates = field_port.extract(
            {
                "task_id": task_id,
                "document_result": document_result,
                "evidence_units": evidence_units,
                "schema": schema,
                "source": "ocr_text_only",
                "document_type": task.get("document_type") or "copd_admission_record",
                "cancellation_token": cancellation_token,
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

        # BE-MVP-04-05 新契约:重抽取直接覆盖 review_result.json["fields"]
        self._overwrite_review_with_candidates(task_id, candidates, schema, run_id, now)

        return {
            "task_id": task_id,
            "status": task["status"],
            "candidate_count": len(candidates),
            **metadata,
        }

    def _load_evidence_units_for_reextract(self, document_result: dict) -> list[dict]:
        """Return evidence units to feed the field port.

        Re-extraction prefers the units persisted alongside the successful
        ``document_result.json`` (so OCR highlights stay byte-stable). When
        the saved result predates Task 2 (legacy), rebuild units from the
        raw OCR pages and merged text.
        """
        saved = document_result.get("evidence_units") if isinstance(document_result, dict) else None
        if isinstance(saved, list) and saved:
            return saved
        return build_evidence_units(document_result or {})

    def _load_ocr_document_result(self, task_id: str) -> dict:
        result_store = AlgorithmResultStore(self._store)
        doc = result_store.read_success_document_result(task_id)
        if doc is not None:
            return doc

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

    def _overwrite_review_with_candidates(
        self,
        task_id: str,
        candidates: list[dict],
        schema: dict,
        run_id: str,
        now: str,
    ) -> None:
        """按 schema 顺序用新候选覆盖 review_result.json["fields"]。

        规则:
        - 对每个 schema 字段,在新候选中找到同 field_key 则覆盖 review 字段(final_value/auto_value/evidence/...
          /状态重置为 unreviewed / history 追加 reextract 记录)。
        - 找不到候选的 schema 字段:review 中已有则保留,review 中没有则插入空占位。
        - 新候选中 schema 不存在的 field_key 丢弃,不写入 review。
        - 字段按 schema 顺序重排。
        - 写回 store。
        """
        existing_review = self._store.read(f"results/{task_id}/review_result.json")
        existing_fields: dict[str, dict] = {}
        if isinstance(existing_review, dict):
            for f in existing_review.get("fields") or []:
                if isinstance(f, dict) and f.get("field_key"):
                    existing_fields[f["field_key"]] = f
        else:
            # 兜底:review 不存在时,从 task 兜底 schema_version/document_type
            task = self._task_service.get_task(task_id)
            existing_review = {
                "task_id": task_id,
                "schema_version": schema.get("version") or task.get("schema_version"),
                "document_type": schema.get("document_type") or task.get("document_type"),
            }

        candidates_by_key = {c.get("field_key"): c for c in candidates if isinstance(c, dict) and c.get("field_key")}

        new_fields: list[dict] = []
        for group in schema.get("field_groups", []) or []:
            for schema_field in group.get("fields", []) or []:
                fk = schema_field.get("field_key")
                if not fk:
                    continue
                schema_label = schema_field.get("label") or schema_field.get("field_name") or fk
                candidate = candidates_by_key.get(fk)
                if candidate is not None:
                    old = existing_fields.get(fk, {})
                    to_value = candidate.get("original_value", "")
                    new_field = build_field_from_candidate(
                        fk,
                        schema_label,
                        candidate,
                        now=now,
                        previous_history=old.get("history"),
                        previous_review_note=old.get("review_note"),
                    )
                    append_reextract_history(
                        new_field,
                        from_value=old.get("final_value"),
                        to_value=to_value,
                        run_id=run_id,
                        now=now,
                    )
                    new_fields.append(new_field)
                elif fk in existing_fields:
                    # 候选中无该 schema 字段,review 中已有,保留原值
                    new_fields.append(existing_fields[fk])
                else:
                    # 候选中无,review 中也无,插入空占位
                    new_fields.append(build_placeholder_field(fk, schema_label, now=now))

        existing_review["fields"] = new_fields
        existing_review["updated_at"] = now
        existing_review["summary"] = build_review_summary(new_fields)
        self._store.write(f"results/{task_id}/review_result.json", existing_review)

    @staticmethod
    def _build_summary(fields: list[dict]) -> dict:
        return build_review_summary(fields)
