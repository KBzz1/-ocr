from datetime import datetime, timezone
from typing import Callable

from ..enums import FieldStatus, TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore

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

    def get_or_init(self, task_id: str, task: dict | None = None) -> dict:
        if task is None:
            task = self._task_service.get_task(task_id)
        self._ensure_readable(task)

        existing = self._store.read(f"results/{task_id}/review_result.json")
        if existing is not None:
            return existing

        wrapper = self._store.read(f"results/{task_id}/field_candidates.json")
        candidates = wrapper.get("candidates") if isinstance(wrapper, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段候选缺失或为空，无法初始化审核")

        schema = self._schema_provider() if self._schema_provider else {}
        fields = self._build_fields(candidates, schema)
        now = self._now()
        review = {
            "task_id": task_id,
            "schema_version": schema.get("version") or task.get("schema_version"),
            "document_type": schema.get("document_type") or task.get("document_type"),
            "initialized_at": now,
            "updated_at": now,
            "source_groups": self._build_source_groups(candidates),
            "fields": fields,
            "summary": self._build_summary(fields),
        }
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def _build_fields(self, candidates: list[dict], schema: dict) -> list[dict]:
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
        result = []
        for item in sorted_candidates:
            field_key = item["field_key"]
            auto_value = item.get("original_value", "")
            result.append(
                {
                    "field_key": field_key,
                    "field_name": labels.get(field_key) or item.get("field_name") or field_key,
                    "auto_value": auto_value,
                    "final_value": auto_value,
                    "evidence": item.get("evidence"),
                    "page_no": item.get("page_no"),
                    "confidence": item.get("confidence"),
                    "source_hint": item.get("source_hint"),
                    "source_text": item.get("source_text"),
                    "source_group_id": item.get("source_group_id"),
                    "source_section": item.get("source_section"),
                    "extraction_status": item.get("extraction_status", "extracted"),
                    "verification_status": item.get("verification_status", "not_checked"),
                    "quality_flags": item.get("quality_flags", []),
                    "ocr_correction": item.get("ocr_correction"),
                    "status": FieldStatus.UNREVIEWED.value,
                    "empty_accepted": False,
                    "review_note": None,
                    "reviewed_at": None,
                    "updated_at": None,
                    "history": [],
                }
            )
        return result

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
        return {
            "total_count": len(fields),
            "unreviewed_count": sum(1 for f in fields if f["status"] == FieldStatus.UNREVIEWED.value),
            "confirmed_count": sum(1 for f in fields if f["status"] == FieldStatus.CONFIRMED.value),
            "modified_count": sum(1 for f in fields if f["status"] == FieldStatus.MODIFIED.value),
            "suspicious_count": sum(1 for f in fields if f.get("verification_status") == "suspicious"),
            "failed_verification_count": sum(1 for f in fields if f.get("verification_status") == "failed"),
            "not_found_count": sum(1 for f in fields if f.get("extraction_status") == "not_found"),
            "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
        }

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

        unreviewed = [f["field_key"] for f in review["fields"] if f["status"] == FieldStatus.UNREVIEWED.value]
        if not review["fields"] or unreviewed:
            raise AppError(
                ErrorCode.REVIEW_VALIDATION_FAILED,
                message="审核确认校验失败",
                details={
                    FieldStatus.UNREVIEWED.value: unreviewed,
                    "missing_evidence_count": summary["missing_evidence_count"],
                },
            )
        return self._task_service.complete_review(task_id, review_summary=summary)

    def _find_field(self, review: dict, field_key: str) -> dict:
        for field in review["fields"]:
            if field["field_key"] == field_key:
                return field
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"字段 {field_key} 不在审核结果中")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
