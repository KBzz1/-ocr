import json
import os
from datetime import datetime, timezone
from typing import Callable

from ..enums import FieldStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class ExportService:
    def __init__(
        self,
        store: JsonStore,
        export_dir: str,
        task_service,
        schema_provider: Callable[[], dict] | None = None,
    ):
        self._store = store
        self._export_dir = export_dir
        self._task_service = task_service
        self._schema_provider = schema_provider

    def check(self, task_id: str) -> dict:
        task = self._task_service.get_task(task_id)
        status = task["status"]

        if status not in ("confirmed", "exported"):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="任务尚未确认，不允许导出",
                details={"current": status},
            )

        review = self._store.read(f"results/{task_id}/review_result.json")
        if review is None or not review.get("fields"):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="审核结果缺失或字段为空，无法导出",
                details={"task_id": task_id},
            )

        fields = review["fields"]
        unreviewed = [f["field_key"] for f in fields if f["status"] == FieldStatus.UNREVIEWED.value]
        suspicious = [f["field_key"] for f in fields if f["status"] == FieldStatus.SUSPICIOUS.value]
        empty_unaccepted = [
            f["field_key"]
            for f in fields
            if f["status"] == FieldStatus.EMPTY.value and not f["empty_accepted"]
        ]

        summary = {
            "total_count": len(fields),
            "unreviewed_count": len(unreviewed),
            "suspicious_count": len(suspicious),
            "empty_count": sum(1 for f in fields if f["status"] == FieldStatus.EMPTY.value),
            "empty_unaccepted_count": len(empty_unaccepted),
            "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
        }

        blocking_fields = {
            "unreviewed": unreviewed,
            "suspicious": suspicious,
            "empty_unaccepted": empty_unaccepted,
        }

        can_export = not (unreviewed or suspicious or empty_unaccepted)

        return {
            "task_id": task_id,
            "status": status,
            "can_export": can_export,
            "summary": summary,
            "blocking_fields": blocking_fields,
        }

    def _build_export_model(self, task_id: str) -> dict:
        task = self._task_service.get_task(task_id)
        review = self._store.read(f"results/{task_id}/review_result.json")
        if review is None or not isinstance(review.get("fields"), list):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="审核结果缺失或字段为空，无法构建导出模型",
                details={"task_id": task_id},
            )

        schema = self._schema_provider() if self._schema_provider else {}
        field_groups = schema.get("field_groups", [])

        # Build field_key -> (group_key, group_label, field_name) mapping from schema
        schema_lookup: dict[str, dict[str, str]] = {}
        for group in field_groups:
            for field in group.get("fields", []):
                fk = field["field_key"]
                schema_lookup[fk] = {
                    "group_key": group["group_key"],
                    "group_label": group["group_label"],
                    "field_name": field.get("label") or field.get("field_name") or fk,
                }

        model_fields = []
        for f in review["fields"]:
            fk = f["field_key"]
            lookup = schema_lookup.get(fk, {})
            model_fields.append({
                "field_key": fk,
                "field_name": lookup.get("field_name") or f.get("field_name") or fk,
                "group_key": lookup.get("group_key", "unknown"),
                "group_label": lookup.get("group_label", "unknown"),
                "final_value": f["final_value"],
                "status": f["status"],
                "empty_accepted": f.get("empty_accepted", False),
                "evidence": f.get("evidence"),
                "page_no": f.get("page_no"),
                "reviewed_at": f.get("reviewed_at"),
            })

        summary = {
            "total_count": len(model_fields),
            "unreviewed_count": sum(1 for f in model_fields if f["status"] == FieldStatus.UNREVIEWED.value),
            "suspicious_count": sum(1 for f in model_fields if f["status"] == FieldStatus.SUSPICIOUS.value),
            "empty_count": sum(1 for f in model_fields if f["status"] == FieldStatus.EMPTY.value),
            "empty_unaccepted_count": sum(
                1 for f in model_fields
                if f["status"] == FieldStatus.EMPTY.value and not f["empty_accepted"]
            ),
            "missing_evidence_count": sum(1 for f in model_fields if not f["evidence"]),
        }

        return {
            "task_id": task_id,
            "exported_at": self._now(),
            "schema_version": review.get("schema_version") or task.get("schema_version", ""),
            "document_type": review.get("document_type") or task.get("document_type", ""),
            "fields": model_fields,
            "summary": summary,
        }

    def export_json(self, task_id: str) -> dict:
        model = self._build_export_model(task_id)
        filename = f"{task_id}.review.json"
        relative_path = f"{task_id}/{filename}"
        task_dir = os.path.join(self._export_dir, task_id)
        filepath = os.path.join(task_dir, filename)

        try:
            os.makedirs(task_dir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(model, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="导出文件写入失败",
                details={"format": "json", "reason": str(e)},
            )

        self._task_service.mark_exported(task_id, format="json", relative_path=relative_path)

        return {
            "format": "json",
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
