import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Callable
from xml.sax.saxutils import escape

from ..enums import FieldStatus, TaskStatus
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

        review = self._store.read(f"results/{task_id}/review_result.json")
        fields = self._get_review_fields_for_export(task_id, status, review)

        unreviewed = self._compute_blocking_fields(fields)
        summary = self._compute_summary(fields)

        return {
            "task_id": task_id,
            "status": status,
            "can_export": not unreviewed,
            "summary": summary,
            "blocking_fields": {
                "unreviewed": unreviewed,
            },
        }

    def _build_export_model(self, task_id: str, task: dict | None = None) -> dict:
        if task is None:
            task = self._task_service.get_task(task_id)
        review = self._store.read(f"results/{task_id}/review_result.json")
        fields = self._get_review_fields_for_export(task_id, task["status"], review)
        self._ensure_no_blocking_fields(fields)

        schema = self._schema_provider() if self._schema_provider else {}
        schema_lookup: dict[str, dict[str, str]] = {}
        for group in schema.get("field_groups", []):
            for field in group.get("fields", []):
                fk = field["field_key"]
                schema_lookup[fk] = {
                    "group_key": group["group_key"],
                    "group_label": group["group_label"],
                    "field_name": field.get("label") or field.get("field_name") or fk,
                }

        model_fields = []
        for f in fields:
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

        return {
            "task_id": task_id,
            "exported_at": self._now(),
            "schema_version": review.get("schema_version") or task.get("schema_version", ""),
            "document_type": review.get("document_type") or task.get("document_type", ""),
            "fields": model_fields,
            "summary": self._compute_summary(model_fields),
        }

    def export_json(self, task_id: str) -> dict:
        return self._do_export(task_id, "json", "json", self._write_json_file)

    def export_excel(self, task_id: str) -> dict:
        return self._do_export(task_id, "excel", "xlsx", self._write_xlsx)

    def export_batch_zip(self, task_ids: list[str]) -> dict:
        models = []
        for task_id in task_ids:
            task = self._task_service.get_task(task_id)
            models.append((task_id, self._build_export_model(task_id, task=task)))

        filename = "batch-review-export.zip"
        relative_path = f"batch/{filename}"
        batch_dir = os.path.join(self._export_dir, "batch")
        filepath = os.path.join(batch_dir, filename)

        try:
            os.makedirs(batch_dir, exist_ok=True)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as archive:
                for task_id, model in models:
                    archive.writestr(
                        f"{task_id}/{task_id}.review.json",
                        json.dumps(model, ensure_ascii=False, indent=2),
                    )
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="批量导出文件写入失败",
                details={"format": "batch_zip", "reason": str(e)},
            )

        for task_id, _model in models:
            self._task_service.record_export(task_id, format="batch_zip", relative_path=relative_path)

        return {
            "format": "batch_zip",
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    def _do_export(self, task_id: str, format: str, ext: str, writer: Callable) -> dict:
        task = self._task_service.get_task(task_id)
        model = self._build_export_model(task_id, task=task)
        filename = f"{task_id}.review.{ext}"
        relative_path = f"{task_id}/{filename}"
        task_dir = os.path.join(self._export_dir, task_id)
        filepath = os.path.join(task_dir, filename)

        try:
            os.makedirs(task_dir, exist_ok=True)
            writer(filepath, model)
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="导出文件写入失败",
                details={"format": format, "reason": str(e)},
            )

        self._task_service.record_export(task_id, format=format, relative_path=relative_path)

        return {
            "format": format,
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    # -- shared helpers --

    @staticmethod
    def _get_review_fields_for_export(task_id: str, status: str, review: dict | None) -> list[dict]:
        if status not in (TaskStatus.REVIEW.value, TaskStatus.DONE.value):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="只有待审核或已完成任务可以导出",
                details={"current": status},
            )
        if review is None or not isinstance(review.get("fields"), list) or not review["fields"]:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="审核结果缺失或字段为空，无法导出",
                details={"task_id": task_id},
            )
        return review["fields"]

    @classmethod
    def _ensure_no_blocking_fields(cls, fields: list[dict]) -> None:
        unreviewed = cls._compute_blocking_fields(fields)
        if unreviewed:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="审核结果存在未确认字段，无法导出",
                details={
                    "blocking_fields": {
                        "unreviewed": unreviewed,
                    }
                },
            )

    @staticmethod
    def _compute_summary(fields: list[dict]) -> dict:
        total = len(fields)
        unreviewed = 0
        missing_evidence = 0
        for f in fields:
            status = f["status"]
            if status == FieldStatus.UNREVIEWED.value:
                unreviewed += 1
            if not f.get("evidence"):
                missing_evidence += 1
        return {
            "total_count": total,
            "unreviewed_count": unreviewed,
            "missing_evidence_count": missing_evidence,
        }

    @staticmethod
    def _compute_blocking_fields(fields: list[dict]) -> list[str]:
        unreviewed = []
        for f in fields:
            status = f["status"]
            if status == FieldStatus.UNREVIEWED.value:
                unreviewed.append(f["field_key"])
        return unreviewed

    # -- file writers --

    @staticmethod
    def _write_json_file(path: str, model: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(model, f, ensure_ascii=False, indent=2)

    # -- XLSX writer (standard-library only) --

    _XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    _HEADERS = ["字段 key", "字段名", "final_value", "状态", "来源页", "来源证据"]
    _COL_LETTERS = ["A", "B", "C", "D", "E", "F"]

    def _write_xlsx(self, path: str, model: dict) -> None:
        groups: dict[str, dict] = {}
        for f in model["fields"]:
            gk = f["group_key"]
            if gk not in groups:
                groups[gk] = {"group_label": f["group_label"], "fields": []}
            groups[gk]["fields"].append(f)

        sheet_names = self._build_sheet_names(groups)

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types_xml(len(sheet_names)))
            z.writestr("_rels/.rels", self._rels_xml())
            z.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(sheet_names))

            for idx, group_key in enumerate(groups, start=1):
                sheet_xml = self._sheet_xml(groups[group_key]["fields"])
                z.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)

    def _build_sheet_names(self, groups: dict) -> list[str]:
        names = []
        seen = {}
        for g in groups.values():
            label = g["group_label"]
            sanitized = self._sanitize_sheet_name(label)
            if sanitized in seen:
                seen[sanitized] += 1
                names.append(f"{sanitized}{seen[sanitized]}")
            else:
                seen[sanitized] = 0
                names.append(sanitized)
        return names

    @staticmethod
    def _sanitize_sheet_name(name: str) -> str:
        result = name[:31]
        for ch in r"[]:*?/\\":
            result = result.replace(ch, "_")
        return result

    @staticmethod
    def _content_types_xml(sheet_count: int) -> str:
        types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        for i in range(1, sheet_count + 1):
            types.append(
                f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        types.append("</Types>")
        return "\n".join(types)

    @staticmethod
    def _rels_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
            "</Relationships>"
        )

    @staticmethod
    def _workbook_xml(sheet_names: list[str]) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
            "<sheets>",
        ]
        for idx, name in enumerate(sheet_names, start=1):
            escaped = escape(name)
            lines.append(f'<sheet name="{escaped}" sheetId="{idx}" r:id="rId{idx}"/>')
        lines.append("</sheets>")
        lines.append("</workbook>")
        return "\n".join(lines)

    @staticmethod
    def _workbook_rels_xml(sheet_names: list[str]) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        ]
        for idx in range(1, len(sheet_names) + 1):
            lines.append(
                f'<Relationship Id="rId{idx}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
            )
        lines.append("</Relationships>")
        return "\n".join(lines)

    @classmethod
    def _sheet_xml(cls, fields: list[dict]) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            "<sheetData>",
        ]
        lines.append('<row r="1">')
        for i, header in enumerate(cls._HEADERS):
            letter = cls._COL_LETTERS[i]
            escaped = escape(header)
            lines.append(f'<c r="{letter}1" t="inlineStr"><is><t>{escaped}</t></is></c>')
        lines.append("</row>")

        for row_idx, field in enumerate(fields, start=2):
            lines.append(f'<row r="{row_idx}">')
            values = [
                field.get("field_key", ""),
                field.get("field_name", ""),
                field.get("final_value", ""),
                field.get("status", ""),
                str(field.get("page_no") or ""),
                field.get("evidence") or "",
            ]
            for i, val in enumerate(values):
                letter = cls._COL_LETTERS[i]
                escaped = escape(val)
                lines.append(f'<c r="{letter}{row_idx}" t="inlineStr"><is><t>{escaped}</t></is></c>')
            lines.append("</row>")

        lines.append("</sheetData>")
        lines.append("</worksheet>")
        return "\n".join(lines)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
