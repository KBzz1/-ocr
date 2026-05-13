import json
import os
import zipfile
from datetime import datetime, timezone
from typing import Callable
from xml.sax.saxutils import escape

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

    def export_excel(self, task_id: str) -> dict:
        model = self._build_export_model(task_id)
        filename = f"{task_id}.review.xlsx"
        relative_path = f"{task_id}/{filename}"
        task_dir = os.path.join(self._export_dir, task_id)
        filepath = os.path.join(task_dir, filename)

        try:
            os.makedirs(task_dir, exist_ok=True)
            self._write_xlsx(filepath, model)
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="导出文件写入失败",
                details={"format": "excel", "reason": str(e)},
            )

        self._task_service.mark_exported(task_id, format="excel", relative_path=relative_path)

        return {
            "format": "excel",
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    # -- XLSX writer (minimal, standard-library only) --

    _XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    _HEADERS = ["字段 key", "字段名", "final_value", "状态", "来源页", "来源证据"]
    _COL_LETTERS = ["A", "B", "C", "D", "E", "F"]

    def _write_xlsx(self, path: str, model: dict) -> None:
        # Group fields by group_key, preserving order
        groups: dict[str, dict] = {}
        for f in model["fields"]:
            gk = f["group_key"]
            if gk not in groups:
                groups[gk] = {"group_label": f["group_label"], "fields": []}
            groups[gk]["fields"].append(f)

        # Build sheet names (dedup, sanitize)
        sheet_names = self._build_sheet_names(groups)

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types_xml(len(sheet_names)))
            z.writestr("_rels/.rels", self._rels_xml())
            z.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(sheet_names))

            sheet_idx = 1
            for group_key in groups:
                sheet_xml = self._sheet_xml(groups[group_key]["fields"])
                z.writestr(f"xl/worksheets/sheet{sheet_idx}.xml", sheet_xml)
                sheet_idx += 1

    def _build_sheet_names(self, groups: dict) -> list[str]:
        names = []
        seen = {}
        for gk, g in groups.items():
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
            lines.append(
                f'<sheet name="{escaped}" sheetId="{idx}" r:id="rId{idx}"/>'
            )
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
        # Header row
        lines.append('<row r="1">')
        for i, header in enumerate(cls._HEADERS):
            letter = cls._COL_LETTERS[i]
            escaped = escape(header)
            lines.append(
                f'<c r="{letter}1" t="inlineStr"><is><t>{escaped}</t></is></c>'
            )
        lines.append("</row>")

        # Data rows
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
                lines.append(
                    f'<c r="{letter}{row_idx}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                )
            lines.append("</row>")

        lines.append("</sheetData>")
        lines.append("</worksheet>")
        return "\n".join(lines)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
