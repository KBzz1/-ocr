from datetime import datetime, timezone
from typing import Callable

from ..enums import TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class ReviewService:
    def __init__(self, store: JsonStore, task_service, schema_provider: Callable[[], dict] | None = None):
        self._store = store
        self._task_service = task_service
        self._schema_provider = schema_provider

    def get_or_init(self, task_id: str) -> dict:
        existing = self._store.read(f"results/{task_id}/review_result.json")
        if existing is not None:
            return existing

        task = self._task_service.get_task(task_id)
        self._ensure_readable(task)
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
                    "status": "unreviewed",
                    "empty_accepted": False,
                    "review_note": None,
                    "reviewed_at": None,
                    "updated_at": None,
                    "history": [],
                }
            )
        return result

    def _build_summary(self, fields: list[dict]) -> dict:
        return {
            "total_count": len(fields),
            "unreviewed_count": sum(1 for f in fields if f["status"] == "unreviewed"),
            "confirmed_count": sum(1 for f in fields if f["status"] == "confirmed"),
            "modified_count": sum(1 for f in fields if f["status"] == "modified"),
            "suspicious_count": sum(1 for f in fields if f["status"] == "suspicious"),
            "empty_count": sum(1 for f in fields if f["status"] == "empty"),
            "empty_unaccepted_count": sum(1 for f in fields if f["status"] == "empty" and not f["empty_accepted"]),
            "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
        }

    def _ensure_readable(self, task: dict) -> None:
        if task["status"] not in (TaskStatus.READY_FOR_REVIEW.value, TaskStatus.CONFIRMED.value):
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许读取审核结果",
                details={"current": task["status"]},
            )

    def _ensure_writable(self, task: dict) -> None:
        if task["status"] != TaskStatus.READY_FOR_REVIEW.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许编辑审核结果",
                details={"current": task["status"]},
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
