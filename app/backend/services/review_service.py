import logging
import re
from datetime import datetime, timezone
from typing import Callable

from ..enums import FieldStatus, TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore
from ._review_field_factory import (
    build_placeholder_field,
    build_review_summary,
    is_field_blocking,
)
from .copd_extraction.quality_checks import apply_quality_checks

logger = logging.getLogger(__name__)

MVP_FIELD_STATUSES = {
    FieldStatus.UNREVIEWED.value,
    FieldStatus.CONFIRMED.value,
    FieldStatus.MODIFIED.value,
}


class ReviewService:
    def __init__(self, store: JsonStore, task_service, schema_provider: Callable[[], dict] | None = None):
        self._store = store
        self._task_service = task_service
        self._schema_provider = schema_provider

    @staticmethod
    def _iter_schema_fields(schema: dict):
        """按 schema 顺序产出 (field_key, label, schema_field) 元组。"""
        for group in schema.get("field_groups", []) or []:
            for schema_field in group.get("fields", []) or []:
                fk = schema_field.get("field_key")
                if not fk:
                    continue
                label = schema_field.get("label") or schema_field.get("field_name") or fk
                yield fk, label, schema_field

    @staticmethod
    def _field_text(field: dict | None) -> str:
        if not isinstance(field, dict):
            return ""
        for key in ("final_value", "auto_value", "value"):
            value = field.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _extract_composite_value(text: str, pattern: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip().rstrip("。；;，,、")

    _LEGACY_COMPOSITE_FIELD_PATTERNS: dict[str, tuple[str, str]] = {
        "pe_temperature": ("pe_vital_signs", r"体温[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*℃?"),
        "pe_pulse": ("pe_vital_signs", r"脉搏[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*次/分?"),
        "pe_heart_rate": ("pe_heart_rhythm", r"心率[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*次/分?"),
        "pe_respiration_rate": ("pe_vital_signs", r"呼吸[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*次/分?"),
        "pe_blood_pressure": ("pe_vital_signs", r"血压[:：]?\s*([0-9]{2,3}\s*/\s*[0-9]{2,3})\s*mmHg"),
        "pe_height": ("pe_height_weight_bmi", r"身高[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*cm"),
        "pe_weight": ("pe_height_weight_bmi", r"体重[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*kg"),
        "pe_bmi": ("pe_height_weight_bmi", r"BMI[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*kg/m[²2]?"),
        "aux_blood_gas_ph": ("aux_blood_gas", r"pH\s*([0-9]+(?:\.[0-9]+)?)"),
        "aux_blood_gas_pco2": ("aux_blood_gas", r"(?:pCO2|PCO2|PaCO2|PC02)\s*([0-9]+(?:\.[0-9]+)?)\s*mmHg"),
        "aux_blood_gas_po2": ("aux_blood_gas", r"(?:pO2|PO2|PaO2|P02)\s*([0-9]+(?:\.[0-9]+)?)\s*mmHg"),
        "aux_blood_gas_na": ("aux_blood_gas", r"Na\+?\s*([0-9]+(?:\.[0-9]+)?)\s*mmol/L"),
        "aux_blood_gas_fio2": ("aux_blood_gas", r"(?:FiO2|FIO2|Fi02|F102)\s*([0-9]+(?:\.[0-9]+)?)"),
        "aux_blood_gas_oxygenation_index": ("aux_blood_gas", r"氧合指数[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?"),
        "aux_blood_routine_wbc": (
            "aux_blood_routine",
            r"白细胞(?:\(WBC\))?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[*×]\s*)?10\^9/L",
        ),
        "aux_blood_routine_mxd_percent": (
            "aux_blood_routine",
            r"单核细胞百分率(?:\(MXD%\))?\s*([0-9]+(?:\.[0-9]+)?%)",
        ),
        "aux_blood_routine_mod_absolute": (
            "aux_blood_routine",
            r"单核细胞绝对值(?:\(MOD#\))?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:[*×]\s*)?10\^9/L",
        ),
    }

    _PARAMETER_VALUE_PATTERNS: dict[str, str] = {
        "pe_temperature": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_pulse": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_heart_rate": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_respiration_rate": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_blood_pressure": r"([0-9]{2,3}\s*/\s*[0-9]{2,3})",
        "pe_height": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_weight": r"([0-9]+(?:\.[0-9]+)?)",
        "pe_bmi": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_ph": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_pco2": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_po2": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_na": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_fio2": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_gas_oxygenation_index": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_crp": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_routine_wbc": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_routine_mxd_percent": r"([0-9]+(?:\.[0-9]+)?)",
        "aux_blood_routine_mod_absolute": r"([0-9]+(?:\.[0-9]+)?)",
    }

    @classmethod
    def _normalize_parameter_value(cls, field_key: str, value: str) -> str:
        pattern = cls._PARAMETER_VALUE_PATTERNS.get(field_key)
        if not pattern or not value.strip():
            return value
        match = re.search(pattern, value)
        if not match:
            return value.strip()
        return match.group(1).strip()

    @staticmethod
    def _infer_judgement_value(text: str) -> str | None:
        from .copd_extraction.judgement_rules import matches_normal_judgement

        if matches_normal_judgement(text):
            return "正常"
        return None

    def _build_field_from_legacy_composite(self, field_key: str, label: str, existing: dict[str, dict]) -> dict | None:
        rule = self._LEGACY_COMPOSITE_FIELD_PATTERNS.get(field_key)
        if rule is None:
            return None
        legacy_key, pattern = rule
        legacy_field = existing.get(legacy_key)
        legacy_text = self._field_text(legacy_field)
        value = self._extract_composite_value(legacy_text, pattern)
        if not value:
            return None

        field = build_placeholder_field(field_key, label)
        field["auto_value"] = value
        field["final_value"] = value
        field["evidence"] = legacy_field.get("evidence") if isinstance(legacy_field, dict) else None
        field["source_text"] = legacy_text
        field["source_hint"] = legacy_field.get("source_hint") if isinstance(legacy_field, dict) else None
        field["source_group_id"] = legacy_field.get("source_group_id") if isinstance(legacy_field, dict) else None
        field["source_section"] = legacy_field.get("source_section") if isinstance(legacy_field, dict) else None
        field["extraction_status"] = "extracted"
        field["verification_status"] = "not_checked"
        field["attention_required"] = False
        field["attention_message"] = ""
        field["status"] = FieldStatus.UNREVIEWED.value
        return field

    def _normalize_existing_field_for_schema(self, field: dict, schema_field: dict) -> bool:
        mutated = False
        field_key = field.get("field_key")
        if not isinstance(field_key, str):
            return False

        if field_key in self._PARAMETER_VALUE_PATTERNS:
            for value_key in ("auto_value", "final_value", "value"):
                raw_value = field.get(value_key)
                if not isinstance(raw_value, str):
                    continue
                normalized = self._normalize_parameter_value(field_key, raw_value)
                if normalized != raw_value:
                    field[value_key] = normalized
                    mutated = True

        if schema_field.get("review_control") == "judgement" or schema_field.get("qwen_type") == "J":
            current_value = self._field_text(field)
            inferred = self._infer_judgement_value(current_value)
            if inferred and field.get("final_value") != inferred:
                field["auto_value"] = inferred
                field["final_value"] = inferred
                field["extraction_status"] = "extracted"
                field["verification_status"] = "not_checked"
                mutated = True
        return mutated

    def _hydrate_missing_fields(self, review: dict, schema: dict) -> dict:
        """按 schema 顺序补齐 review 中缺失的字段,并对已存在字段按 schema 顺序重排。

        若 review 已对齐 schema(无缺失且顺序一致),跳过写盘。
        """
        if not isinstance(schema, dict) or not schema.get("field_groups"):
            return review

        existing = {f["field_key"]: f for f in review.get("fields", []) if isinstance(f, dict) and f.get("field_key")}
        ordered_keys: list[str] = []
        new_fields: list[dict] = []
        mutated = False
        for fk, label, schema_field in self._iter_schema_fields(schema):
            ordered_keys.append(fk)
            field = existing.get(fk)
            if field is None:
                field = self._build_field_from_legacy_composite(fk, label, existing)
                if field is None:
                    field = build_placeholder_field(fk, label)
                mutated = True
            elif field.get("field_name") != label:
                # schema.label 优先于 review.field_name(与 ExportService 语义一致)
                field["field_name"] = label
                mutated = True
            if self._normalize_existing_field_for_schema(field, schema_field):
                mutated = True
            new_fields.append(field)

        existing_order = [f["field_key"] for f in review.get("fields", []) if isinstance(f, dict) and f.get("field_key")]
        if not mutated and existing_order == ordered_keys:
            return review

        review["fields"] = new_fields
        review["summary"] = build_review_summary(new_fields)
        review["updated_at"] = datetime.now(timezone.utc).isoformat()
        task_id = review.get("task_id")
        if task_id:
            self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def _load_document_result(self, task_id: str) -> dict | None:
        wrapper = self._store.read(f"results/{task_id}/document_result.json")
        if not isinstance(wrapper, dict):
            return None
        return wrapper

    def _enrich_with_ocr(self, review: dict, task_id: str) -> dict:
        doc = self._load_document_result(task_id)
        if not doc:
            return review
        merged_text = doc.get("merged_text", "")
        doc_pages = doc.get("pages") or []
        review["ocr_text"] = merged_text
        review["pages"] = [
            {
                "page_id": p.get("page_id", f"page_{i+1:03d}"),
                "page_no": p.get("page_no", i + 1),
                "parsed_text": p.get("text", ""),
            }
            for i, p in enumerate(doc_pages)
        ]
        return review

    def _enrich_with_schema(self, review: dict) -> dict:
        if self._schema_provider is None:
            return review
        schema = self._schema_provider()
        review_schema_version = review.get("schema_version")
        schema_version = schema.get("version") if isinstance(schema, dict) else None
        if (
            schema
            and "field_groups" in schema
            and (not review_schema_version or review_schema_version == schema_version)
        ):
            review["field_groups"] = schema["field_groups"]
        return review

    def _schema_for_existing_review(self, review: dict) -> dict:
        if self._schema_provider is None:
            return {}
        schema = self._schema_provider()
        if not isinstance(schema, dict):
            return {}
        review_schema_version = review.get("schema_version")
        if review_schema_version and review_schema_version != schema.get("version"):
            return {}
        return schema

    def _schema_for_candidate_wrapper(self, wrapper: dict, task: dict) -> dict:
        current_schema = self._schema_provider() if self._schema_provider else {}
        if not isinstance(current_schema, dict):
            current_schema = {}
        wrapper_schema_version = wrapper.get("schema_version")
        current_schema_version = current_schema.get("version")
        wrapper_field_groups = wrapper.get("field_groups")
        if (
            wrapper_schema_version
            and wrapper_schema_version != current_schema_version
        ):
            if isinstance(wrapper_field_groups, list):
                return {
                    "version": wrapper_schema_version,
                    "document_type": wrapper.get("document_type") or task.get("document_type"),
                    "field_groups": wrapper_field_groups,
                }
            return {
                "version": wrapper_schema_version,
                "document_type": wrapper.get("document_type") or task.get("document_type"),
                "field_groups": [],
            }
        return current_schema

    def _sync_task_review_summary(self, task_id: str, review: dict) -> None:
        summary = review.get("summary")
        sync = getattr(self._task_service, "update_review_summary", None)
        if isinstance(summary, dict) and callable(sync):
            sync(task_id, summary)

    def _apply_quality_warnings(self, task_id: str, review: dict) -> dict:
        fields = review.get("fields")
        if not isinstance(fields, list) or not fields:
            return review
        doc = self._load_document_result(task_id)
        full_text = doc.get("merged_text", "") if isinstance(doc, dict) else ""
        if not full_text:
            return review

        check_input = []
        for field in fields:
            if not isinstance(field, dict):
                check_input.append(field)
                continue
            item = dict(field)
            item["original_value"] = (
                field.get("final_value")
                or field.get("auto_value")
                or field.get("value")
                or ""
            )
            # quality_flags 由 apply_quality_checks 全新计算，
            # 不传递旧 flags 以避免重复累积
            item["quality_flags"] = []
            check_input.append(item)

        checked = apply_quality_checks(
            check_input,
            full_text,
            include_document_flags=False,
        )

        mutated = False
        for field, checked_field in zip(fields, checked):
            if not isinstance(field, dict) or not isinstance(checked_field, dict):
                continue
            next_flags = checked_field.get("quality_flags") or []
            if not next_flags:
                continue
            if field.get("quality_flags") != next_flags:
                field["quality_flags"] = next_flags
                mutated = True
            if (
                field.get("verification_status") != "failed"
                and field.get("verification_status") != "suspicious"
            ):
                field["verification_status"] = "suspicious"
                mutated = True

        if not mutated:
            return review
        review["summary"] = build_review_summary(fields)
        review["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def get_or_init(self, task_id: str, task: dict | None = None) -> dict:
        if task is None:
            task = self._task_service.get_task(task_id)
        self._ensure_readable(task)

        existing = self._store.read(f"results/{task_id}/review_result.json")
        if existing is not None:
            # BE-MVP-05-06: 按当前 schema 补齐缺失字段并重排
            # 仅限同 schema_version。历史任务不得被当前默认 schema 静默改写。
            schema_for_hydrate = self._schema_for_existing_review(existing)
            self._hydrate_missing_fields(existing, schema_for_hydrate)
            self._apply_quality_warnings(task_id, existing)
            self._sync_task_review_summary(task_id, existing)
            return self._enrich_with_schema(self._enrich_with_ocr(existing, task_id))

        wrapper = self._store.read(f"results/{task_id}/field_candidates.json")
        candidates = wrapper.get("candidates") if isinstance(wrapper, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段候选缺失或为空，无法初始化审核")

        schema = self._schema_for_candidate_wrapper(wrapper, task)
        fields = self._build_fields(candidates, schema)
        field_groups = schema.get("field_groups") if isinstance(schema.get("field_groups"), list) else wrapper.get("field_groups")
        now = self._now()
        review = {
            "task_id": task_id,
            "schema_version": schema.get("version") or wrapper.get("schema_version") or task.get("schema_version"),
            "document_type": schema.get("document_type") or wrapper.get("document_type") or task.get("document_type"),
            "initialized_at": now,
            "updated_at": now,
            "source_groups": self._build_source_groups(candidates),
            "fields": fields,
            "summary": self._build_summary(fields),
        }
        if isinstance(field_groups, list):
            review["field_groups"] = field_groups
        self._store.write(f"results/{task_id}/review_result.json", review)
        # BE-MVP-05-06: candidates 路径也要按 schema 补齐缺失字段并重排
        self._hydrate_missing_fields(review, schema)
        self._sync_task_review_summary(task_id, review)
        return self._enrich_with_schema(self._enrich_with_ocr(review, task_id))

    def _build_fields(self, candidates: list[dict], schema: dict) -> list[dict]:
        from ._review_field_factory import build_field_from_candidate

        labels = {}
        order = {}
        index = 0
        for group in schema.get("field_groups", []):
            for field in group.get("fields", []):
                key = field["field_key"]
                labels[key] = field.get("label") or field.get("field_name") or key
                order[key] = index
                index += 1

        sorted_candidates = sorted(
            candidates,
            key=lambda c: order.get(c.get("field_key"), len(order)),
        )
        return [
            build_field_from_candidate(
                item["field_key"],
                labels.get(item["field_key"]) or item.get("field_name") or item["field_key"],
                item,
            )
            for item in sorted_candidates
        ]

    def _build_source_groups(self, candidates: list[dict]) -> list[dict]:
        groups: dict[str, dict] = {}
        for item in candidates:
            source_group_id = item.get("source_group_id")
            source_hint = item.get("source_hint") or item.get("source_section")
            source_text = item.get("source_text") or item.get("evidence")
            if not source_group_id or not source_hint or not source_text:
                continue
            group = groups.setdefault(
                source_group_id,
                {
                    "source_group_id": source_group_id,
                    "source_hint": source_hint,
                    "source_text": source_text,
                    "field_keys": [],
                },
            )
            group["field_keys"].append(item["field_key"])
        return list(groups.values())

    def _build_summary(self, fields: list[dict]) -> dict:
        return build_review_summary(fields)

    def _ensure_readable(self, task: dict) -> None:
        if task["status"] not in (TaskStatus.REVIEW.value, TaskStatus.DONE.value):
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许读取审核结果",
                details={"current": task["status"]},
            )

    def _ensure_writable(self, task: dict) -> None:
        if task["status"] != TaskStatus.REVIEW.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许编辑审核结果",
                details={"current": task["status"]},
            )

    def _validate_field_status(self, status: str) -> None:
        if status not in MVP_FIELD_STATUSES:
            raise AppError(
                ErrorCode.REVIEW_VALIDATION_FAILED,
                message="字段状态必须是 unreviewed、confirmed 或 modified",
                details={"status": status},
            )

    def save(self, task_id: str, payload: dict) -> dict:
        fields = payload.get("fields")
        if not isinstance(fields, list):
            raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="fields 必须是列表")

        review = self.get_or_init(task_id)
        for item in fields:
            if not isinstance(item, dict):
                raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段项必须是对象")
            field_key = item.get("field_key")
            status = item.get("status", FieldStatus.MODIFIED.value)
            self._validate_field_status(status)
            field = self._find_field(review, field_key)
            value = item.get("value", item.get("final_value", field["final_value"]))
            if not isinstance(value, str):
                raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段值必须是字符串")
            field["final_value"] = value
            field["status"] = status
            field["reviewed_at"] = self._now()
            field["updated_at"] = field["reviewed_at"]

        review["updated_at"] = self._now()
        review["summary"] = self._build_summary(review["fields"])
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def update_field(self, task_id: str, field_key: str, payload: dict) -> dict:
        task = self._task_service.get_task(task_id)
        self._ensure_writable(task)
        review = self.get_or_init(task_id, task=task)

        if "status" in payload:
            status = payload["status"]
            self._validate_field_status(status)
            field = self._find_field(review, field_key)
            value = payload.get("value", payload.get("final_value", field["final_value"]))
            if not isinstance(value, str):
                raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段值必须是字符串")
            field["final_value"] = value
            field["status"] = status
            field["reviewed_at"] = self._now()
            field["updated_at"] = field["reviewed_at"]
            review["updated_at"] = field["updated_at"]
            review["summary"] = self._build_summary(review["fields"])
            self._store.write(f"results/{task_id}/review_result.json", review)
            return review

        action = payload.get("action")
        review_note = payload.get("review_note")
        if review_note is not None and not isinstance(review_note, str):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="review_note 必须是字符串或 null")

        field = self._find_field(review, field_key)
        old_value = field["final_value"]

        # Guard: skip write when the action is a no-op
        new_value = payload.get("final_value")
        if action == "confirm" and field["status"] == FieldStatus.CONFIRMED.value and new_value is None:
            return review
        if action == "confirm" and field["status"] == FieldStatus.CONFIRMED.value and new_value == old_value:
            return review
        if action == "modify" and field["status"] == FieldStatus.MODIFIED.value and new_value == old_value:
            return review

        now = self._now()

        if action == "confirm":
            if "final_value" in payload:
                if not isinstance(payload["final_value"], str):
                    raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="final_value 必须是字符串")
                field["final_value"] = payload["final_value"]
            field["status"] = FieldStatus.CONFIRMED.value
            field["empty_accepted"] = False
        elif action == "modify":
            if not isinstance(payload.get("final_value"), str):
                raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="modify 必须提供字符串 final_value")
            field["final_value"] = payload["final_value"]
            field["status"] = FieldStatus.MODIFIED.value
            field["empty_accepted"] = False
        else:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"未知审核动作: {action}")

        field["review_note"] = review_note
        field["reviewed_at"] = now
        field["updated_at"] = now
        field.setdefault("history", []).append(
            {
                "action": action,
                "from_value": old_value,
                "to_value": field["final_value"],
                "review_note": review_note,
                "changed_at": now,
            }
        )
        review["updated_at"] = now
        review["summary"] = self._build_summary(review["fields"])
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def confirm(self, task_id: str) -> dict:
        task = self._task_service.get_task(task_id)
        self._ensure_writable(task)
        review = self.get_or_init(task_id, task=task)
        summary = self._build_summary(review["fields"])

        # BE-MVP-05-06: 空 final_value 占位字段不算未确认,与导出阻断逻辑保持一致
        unreviewed = [f["field_key"] for f in review["fields"] if is_field_blocking(f)]
        if not review["fields"] or unreviewed:
            raise AppError(
                ErrorCode.REVIEW_VALIDATION_FAILED,
                message="审核确认校验失败",
                details={
                    FieldStatus.UNREVIEWED.value: unreviewed,
                    "missing_evidence_count": summary["missing_evidence_count"],
                },
            )
        result = self._task_service.complete_review(task_id, review_summary=summary)
        self._collect_review_feedback(task_id, review)
        return result

    def _collect_review_feedback(self, task_id: str, review: dict) -> None:
        """聚合医生修正字段（auto_value≠final_value）写入回流文件；失败降级不阻断。"""
        fields = review.get("fields")
        if not isinstance(fields, list):
            return
        items = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            original = str(field.get("auto_value") or "")
            corrected = str(field.get("final_value") or "")
            if original == corrected:
                continue
            items.append({
                "field_key": field.get("field_key", ""),
                "status": "found" if corrected.strip() else "not_found",
                "original_value": original,
                "corrected_value": corrected,
            })
        if not items:
            return
        feedback = {
            "task_id": task_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": review.get("schema_version"),
            "fields": items,
        }
        try:
            self._store.write(f"evaluation/review_feedback/{task_id}.json", feedback)
        except Exception:  # noqa: BLE001 — 回流失败不阻断审核确认
            logger.warning("审核回流写入失败 task_id=%s", task_id, exc_info=True)

    def _find_field(self, review: dict, field_key: str) -> dict:
        for field in review["fields"]:
            if field["field_key"] == field_key:
                return field
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"字段 {field_key} 不在审核结果中")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
