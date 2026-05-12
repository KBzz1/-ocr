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

    def update_field(self, task_id: str, field_key: str, payload: dict) -> dict:
        task = self._task_service.get_task(task_id)
        self._ensure_writable(task)
        review = self.get_or_init(task_id)

        action = payload.get("action")
        review_note = payload.get("review_note")
        if review_note is not None and not isinstance(review_note, str):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="review_note 必须是字符串或 null")

        field = self._find_field(review, field_key)
        old_value = field["final_value"]
        now = self._now()

        if action == "confirm":
            if "final_value" in payload:
                if not isinstance(payload["final_value"], str):
                    raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="final_value 必须是字符串")
                field["final_value"] = payload["final_value"]
            field["status"] = "confirmed"
            field["empty_accepted"] = False
        elif action == "modify":
            if not isinstance(payload.get("final_value"), str):
                raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="modify 必须提供字符串 final_value")
            field["final_value"] = payload["final_value"]
            field["status"] = "modified"
            field["empty_accepted"] = False
        elif action == "clear":
            field["final_value"] = ""
            field["status"] = "empty"
            field["empty_accepted"] = False
        elif action == "accept_empty":
            if field["status"] != "empty" or field["final_value"] != "":
                raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="只有已清空字段可以接受空值")
            field["status"] = "empty"
            field["empty_accepted"] = True
        elif action == "mark_suspicious":
            field["status"] = "suspicious"
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
        review = self.get_or_init(task_id)
        summary = self._build_summary(review["fields"])

        unreviewed = [f["field_key"] for f in review["fields"] if f["status"] == "unreviewed"]
        suspicious = [f["field_key"] for f in review["fields"] if f["status"] == "suspicious"]
        empty_unaccepted = [
            f["field_key"]
            for f in review["fields"]
            if f["status"] == "empty" and not f["empty_accepted"]
        ]
        if not review["fields"] or unreviewed or suspicious or empty_unaccepted:
            raise AppError(
                ErrorCode.REVIEW_VALIDATION_FAILED,
                message="审核确认校验失败",
                details={
                    "unreviewed": unreviewed,
                    "suspicious": suspicious,
                    "empty_unaccepted": empty_unaccepted,
                    "missing_evidence_count": summary["missing_evidence_count"],
                },
            )
        return self._task_service.mark_confirmed(task_id, review_summary=summary)

    def _find_field(self, review: dict, field_key: str) -> dict:
        for field in review["fields"]:
            if field["field_key"] == field_key:
                return field
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"字段 {field_key} 不在审核结果中")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
