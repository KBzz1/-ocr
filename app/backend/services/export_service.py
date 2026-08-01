import json
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Callable
from xml.sax.saxutils import escape

from ..enums import FieldStatus, TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore
from ._review_field_factory import build_placeholder_field, is_field_blocking


class ExportService:
    def __init__(
        self,
        store: JsonStore,
        export_dir: str,
        task_service,
        schema_provider: Callable[[], dict] | None = None,
        document_profiles=None,
    ):
        self._store = store
        self._export_dir = export_dir
        self._task_service = task_service
        self._schema_provider = schema_provider
        self._document_profiles = document_profiles

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
        self._get_review_fields_for_export(task_id, task["status"], review)

        schema = self._schema_for_task(task)
        # BE-MVP-05-06: 不直接遍历 review["fields"],先按当前 schema 生成 schema 字段视图
        # 缺失字段用空占位补齐,顺序与 schema 一致
        schema_view = self._build_schema_view(review or {}, schema)
        self._ensure_no_blocking_fields(schema_view)

        model_fields = []
        for f in schema_view:
            fk = f["field_key"]
            model_fields.append({
                "field_key": fk,
                "field_name": f.get("field_name") or fk,
                "group_key": f.get("group_key", "unknown"),
                "group_label": f.get("group_label", "unknown"),
                "final_value": f.get("final_value", ""),
                "auto_value": f.get("auto_value", ""),
                "status": f.get("status", FieldStatus.UNREVIEWED.value),
                "empty_accepted": f.get("empty_accepted", False),
                "evidence": f.get("evidence"),
                "page_no": f.get("page_no"),
                "extraction_status": f.get("extraction_status", "not_found"),
                "verification_status": f.get("verification_status", "not_checked"),
                "attention_required": bool(f.get("attention_required", False)),
                "attention_message": f.get("attention_message", "") or "",
                "quality_flags": list(f.get("quality_flags") or []),
                "reviewed_at": f.get("reviewed_at"),
            })

        return {
            "task_id": task_id,
            "exported_at": self._now(),
            "schema_version": (review or {}).get("schema_version") or task.get("schema_version", ""),
            "document_type": (review or {}).get("document_type") or task.get("document_type", ""),
            "patient": self._patient_metadata(task),
            "record": self._record_metadata(task),
            "fields": model_fields,
            "summary": self._compute_summary(model_fields),
        }

    def _patient_metadata(self, task: dict) -> dict:
        """导出场景下的患者元数据。优先使用 task_service 提供的实现,
        未提供或结果缺姓名时,回落到 task.patient_snapshot
        (list_tasks summary 形态时回落到 task.patient 汇总)。"""
        provider = getattr(self._task_service, "patient_export_metadata", None)
        if callable(provider):
            try:
                metadata = provider(task)
                if metadata is not None and metadata.get("name"):
                    return metadata
            except Exception:
                pass
        snapshot = task.get("patient_snapshot") or task.get("patient") or {}
        return {
            "patient_id": task.get("patient_id"),
            "name": snapshot.get("name"),
            "deleted": False,
        }

    def _record_metadata(self, task: dict) -> dict:
        return {
            "document_type": task.get("document_type"),
            "document_type_label": task.get("document_type_label"),
            "record_date": task.get("record_date"),
            "record_time": task.get("record_time"),
        }

    @staticmethod
    def _build_schema_view(review: dict, schema: dict) -> list[dict]:
        """按 schema 顺序构造字段视图,review 中已有字段保留原值,缺失字段用空占位补齐。

        schema.label 优先于 review.field_name(沿用原 _build_export_model 语义),确保导出字段名与 schema 同步。
        """
        existing = {f["field_key"]: f for f in (review.get("fields") or []) if isinstance(f, dict) and f.get("field_key")}
        view: list[dict] = []
        for group in schema.get("field_groups", []) or []:
            group_key = group.get("group_key", "unknown")
            group_label = group.get("group_label", "unknown")
            for schema_field in group.get("fields", []) or []:
                fk = schema_field.get("field_key")
                if not fk:
                    continue
                schema_label = schema_field.get("label") or schema_field.get("field_name") or fk
                field = existing.get(fk)
                if field is None:
                    field = build_placeholder_field(fk, schema_label, now=None)
                    field["updated_at"] = None
                elif field.get("field_name") != schema_label:
                    field = {**field, "field_name": schema_label}
                view.append({
                    **field,
                    "group_key": group_key,
                    "group_label": group_label,
                })
        return view

    def _schema_for_task(self, task: dict) -> dict:
        if self._document_profiles is not None:
            try:
                profile = self._document_profiles.get_profile(task.get("document_type"))
            except AppError as exc:
                raise AppError(
                    ErrorCode.EXPORT_VALIDATION_FAILED,
                    message="文书模板未注册或未完成接入，无法导出",
                    details={
                        "reason": "document_type_not_registered",
                        "document_type": task.get("document_type"),
                        "error_code": exc.code,
                    },
                )
            return profile.schema
        return self._schema_provider() if self._schema_provider else {}

    def export_json(self, task_id: str) -> dict:
        return self._do_export(task_id, "json", "json", self._write_json_file)

    def export_excel(self, task_id: str) -> dict:
        return self._do_export(task_id, "excel", "xlsx", self._write_xlsx)

    def export_batch_zip(self, task_ids: list[str]) -> dict:
        models, failed_tasks = self._build_batch_export_models(task_ids)
        if failed_tasks:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="批量导出存在不可导出任务",
                details={"format": "batch_zip", "task_count": len(task_ids), "failed_tasks": failed_tasks},
            )

        filename = "batch-review-export.zip"
        relative_path = f"batch/{filename}"
        batch_dir = os.path.join(self._export_dir, "batch")
        filepath = os.path.join(batch_dir, filename)

        try:
            os.makedirs(batch_dir, exist_ok=True)
            with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "manifest.json",
                    json.dumps(self._build_batch_manifest(models), ensure_ascii=False, indent=2),
                )
                for item in models:
                    archive.writestr(
                        item["json_path"],
                        json.dumps(item["model"], ensure_ascii=False, indent=2),
                    )
        except OSError as e:
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="批量导出文件写入失败",
                details={"format": "batch_zip", "reason": str(e)},
            )

        for item in models:
            self._task_service.record_export(item["task_id"], format="batch_zip", relative_path=relative_path)

        return {
            "format": "batch_zip",
            "path": filepath,
            "relative_path": relative_path,
            "filename": filename,
        }

    def _build_batch_export_models(self, task_ids: list[str]) -> tuple[list[dict], list[dict]]:
        models = []
        failed_tasks = []
        for task_id in task_ids:
            try:
                task = self._task_service.get_task(task_id)
                model = self._build_export_model(task_id, task=task)
            except AppError as exc:
                failed_tasks.append({
                    "task_id": task_id,
                    "error_code": exc.code,
                    "reason": exc.message,
                    "status": self._get_task_status_for_error(task_id),
                })
                continue
            models.append({
                "task_id": task_id,
                "status": task["status"],
                "json_path": f"{task_id}/{task_id}.review.json",
                "model": model,
            })
        return models, failed_tasks

    def batch_excel_templates(self) -> list[dict]:
        if self._document_profiles is None:
            return []
        return self._document_profiles.get_batch_excel_available_document_types()

    @staticmethod
    def _task_sort_key(task: dict) -> tuple:
        raw = task.get("task_id")
        try:
            return (0, int(raw))
        except (TypeError, ValueError):
            return (1, str(raw))

    def _candidate_tasks(self, document_type: str) -> list[dict]:
        tasks = self._task_service.list_tasks()
        candidates = [
            task
            for task in tasks
            if task.get("status") in (TaskStatus.REVIEW.value, TaskStatus.DONE.value)
            and task.get("document_type") == document_type
        ]
        candidates.sort(key=self._task_sort_key)
        return candidates

    def _build_batch_excel_rows(self, candidate_tasks: list[dict], schema: dict) -> tuple[list[dict], list[dict]]:
        module_group_keys = [group_key for group_key, _ in self._BATCH_MODULE_COLUMNS]
        schema_group_fields = {
            group.get("group_key"): list(group.get("fields") or [])
            for group in (schema.get("field_groups") or [])
        }
        rows: list[dict] = []
        skipped: list[dict] = []
        serial = 0
        for task in candidate_tasks:
            task_id = task["task_id"]
            try:
                review = self._store.read(f"results/{task_id}/review_result.json")
                if review is None or not isinstance(review.get("fields"), list) or not review["fields"]:
                    raise AppError(
                        ErrorCode.EXPORT_VALIDATION_FAILED,
                        message="审核结果缺失或字段为空",
                    )
                schema_view = self._build_schema_view(review, schema)
            except AppError as exc:
                skipped.append({"task_id": task_id, "reason": exc.message})
                continue
            except (ValueError, OSError):
                skipped.append({"task_id": task_id, "reason": "审核结果缺失或损坏"})
                continue

            confirmed_by_group = {group_key: [] for group_key in module_group_keys}
            for field in schema_view:
                group_key = field.get("group_key")
                if group_key not in confirmed_by_group:
                    continue
                if field.get("status") not in (FieldStatus.CONFIRMED.value, FieldStatus.MODIFIED.value):
                    continue
                final_value = str(field.get("final_value") or "")
                if not final_value.strip():
                    continue
                confirmed_by_group[group_key].append(field)

            cells: dict[str, str] = {}
            for group_key, _ in self._BATCH_MODULE_COLUMNS:
                confirmed_fields = confirmed_by_group[group_key]
                if not confirmed_fields:
                    cells[group_key] = ""
                    continue
                group_fields = schema_group_fields.get(group_key, [])
                # 单字段且字段与组同名(主诉/家族史等代表字段)才只写值,
                # 其余形态(多字段或单字段不同名)写"字段名：值"
                if len(group_fields) == 1 and group_fields[0].get("field_key") == group_key:
                    cells[group_key] = str(confirmed_fields[0]["final_value"])
                else:
                    cells[group_key] = "\n".join(
                        f"{field.get('field_name') or field['field_key']}：{field['final_value']}"
                        for field in confirmed_fields
                    )

            if not any(cells.values()):
                skipped.append({"task_id": task_id, "reason": "目标模块中没有任何已确认字段，未生成导出行"})
                continue

            serial += 1
            patient = self._patient_metadata(task)
            rows.append({
                "serial": serial,
                "patient_name": (patient or {}).get("name") or "",
                "cells": cells,
                "task_id": task_id,
            })
        return rows, skipped

    def _get_task_status_for_error(self, task_id: str) -> str | None:
        try:
            return self._task_service.get_task(task_id).get("status")
        except AppError:
            return None

    def _build_batch_manifest(self, models: list[dict]) -> dict:
        success_tasks = [
            {
                "task_id": item["task_id"],
                "status": item["status"],
                "json_path": item["json_path"],
                "field_count": len(item["model"].get("fields", [])),
                "schema_version": item["model"].get("schema_version", ""),
                "document_type": item["model"].get("document_type", ""),
            }
            for item in models
        ]
        return {
            "format": "batch_zip",
            "generated_at": self._now(),
            "task_count": len(models),
            "success_count": len(success_tasks),
            "success_tasks": success_tasks,
        }

    def batch_excel_download_path(self, export_id: str) -> str | None:
        if not isinstance(export_id, str) or len(export_id) != 32 or not export_id.isalnum():
            return None
        filepath = os.path.join(self._export_dir, "batch", f"batch-{export_id}.xlsx")
        return filepath if os.path.isfile(filepath) else None

    def export_batch_excel(self, document_type: str) -> dict:
        if not isinstance(document_type, str) or not document_type.strip():
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="document_type 必须为非空字符串")
        if self._document_profiles is None:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未注册或未完成接入，无法导出",
                details={"document_type": document_type},
            )
        try:
            profile = self._document_profiles.get_profile(document_type)
        except AppError as exc:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未注册或未完成接入，无法导出",
                details={"document_type": document_type, "error_code": exc.code},
            )
        if not getattr(profile, "batch_excel_enabled", False):
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="文书模板未启用批量 Excel 导出",
                details={"document_type": document_type},
            )

        candidates = self._candidate_tasks(document_type)
        if not candidates:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="没有可导出的记录",
                details={"document_type": document_type},
            )

        rows, skipped = self._build_batch_excel_rows(candidates, profile.schema)
        if not rows:
            raise AppError(
                ErrorCode.EXPORT_VALIDATION_FAILED,
                message="没有可导出的记录",
                details={"document_type": document_type, "skipped": skipped},
            )

        export_id = uuid.uuid4().hex
        filename = f"batch-{export_id}.xlsx"
        relative_path = f"batch/{filename}"
        filepath = os.path.join(self._export_dir, relative_path)
        tmp_path = f"{filepath}.tmp"
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            self._write_batch_xlsx(tmp_path, rows)
            os.replace(tmp_path, filepath)
        except OSError as exc:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise AppError(
                ErrorCode.EXPORT_FAILED,
                message="导出文件写入失败",
                details={"format": "batch_excel", "reason": str(exc)},
            )

        for row in rows:
            self._task_service.record_export(row["task_id"], format="batch_excel", relative_path=relative_path)

        return {
            "format": "batch_excel",
            "export_id": export_id,
            "filename": filename,
            "download_url": f"/api/tasks/export/batch-excel/{export_id}",
            "candidate_count": len(candidates),
            "exported_count": len(rows),
            "skipped_count": len(skipped),
            "skipped": skipped,
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
        """BE-MVP-05-06: 只有非空 final_value 且 status == unreviewed 才视为未确认,占位字段不阻断。"""
        return [f["field_key"] for f in fields if is_field_blocking(f)]

    # -- file writers --

    @staticmethod
    def _write_json_file(path: str, model: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(model, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _serialize_evidence_for_excel(evidence) -> str:
        """Excel 单元格只能写字符串;evidence 数组序列化为 JSON 字符串以便审计可读。

        - ``None`` / 空列表 / 空字符串 → ``""``
        - ``list[dict]`` → ``json.dumps(..., ensure_ascii=False)``
        - ``str``(旧扁平化形态)→ 原样返回
        - 其它 → ``str(evidence)``
        """
        if evidence is None or evidence == "" or evidence == []:
            return ""
        if isinstance(evidence, list):
            return json.dumps(evidence, ensure_ascii=False)
        if isinstance(evidence, str):
            return evidence
        return str(evidence)

    # -- XLSX writer (standard-library only) --

    _XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    _HEADERS = ["字段 key", "字段名", "final_value", "状态", "来源页", "来源证据"]
    _COL_LETTERS = ["A", "B", "C", "D", "E", "F"]

    _BATCH_SHEET_NAME = "批量导出"
    _BATCH_HEADERS = ["序号", "姓名", "主诉", "新病史", "既往史", "个人史", "家族史", "体格检查", "任务编号"]
    _BATCH_COL_LETTERS = ["A", "B", "C", "D", "E", "F", "G", "H", "I"]

    # 批量 Excel 固定列:入院记录六大模块(group_key, 列名)
    _BATCH_MODULE_COLUMNS = [
        ("chief_complaint", "主诉"),
        ("history_of_present_illness", "新病史"),
        ("past_history", "既往史"),
        ("personal_history", "个人史"),
        ("family_history", "家族史"),
        ("physical_exam", "体格检查"),
    ]

    def _write_xlsx(self, path: str, model: dict) -> None:
        groups: dict[str, dict] = {}
        for f in model["fields"]:
            gk = f["group_key"]
            if gk not in groups:
                groups[gk] = {"group_label": f["group_label"], "fields": []}
            groups[gk]["fields"].append(f)

        worksheets = [{"name": "全部字段", "fields": model["fields"]}]
        for group in groups.values():
            worksheets.append({"name": group["group_label"], "fields": group["fields"]})
        # 任务信息 sheet 固定追加在分组 sheet 之后
        worksheets.append({"name": "任务信息", "fields": [], "metadata": True, "model": model})
        sheet_names = self._build_sheet_names([worksheet["name"] for worksheet in worksheets])

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types_xml(len(sheet_names)))
            z.writestr("_rels/.rels", self._rels_xml())
            z.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(sheet_names))

            for idx, worksheet in enumerate(worksheets, start=1):
                if worksheet.get("metadata"):
                    sheet_xml = self._metadata_sheet_xml(worksheet["model"])
                else:
                    sheet_xml = self._sheet_xml(worksheet["fields"])
                z.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)

    _METADATA_ROWS = [
        ("patient.patient_id", "患者编号"),
        ("patient.name", "患者姓名"),
        ("patient.deleted", "患者已删除"),
        ("record.document_type", "记录类型"),
        ("record.document_type_label", "记录类型名称"),
        ("record.record_date", "记录日期"),
        ("record.record_time", "记录时间"),
        ("task_id", "任务编号"),
        ("document_type", "导出记录类型"),
        ("exported_at", "导出时间"),
    ]

    @classmethod
    def _metadata_sheet_xml(cls, model: dict) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            "<sheetData>",
        ]
        lines.append('<row r="1">')
        for letter, header in zip(["A", "B"], ["字段", "值"]):
            escaped = escape(header)
            lines.append(f'<c r="{letter}1" t="inlineStr"><is><t>{escaped}</t></is></c>')
        lines.append("</row>")

        patient = model.get("patient") or {}
        record = model.get("record") or {}

        def _lookup(path: str):
            if path.startswith("patient."):
                return patient.get(path.split(".", 1)[1])
            if path.startswith("record."):
                return record.get(path.split(".", 1)[1])
            return model.get(path)

        for row_idx, (key, header) in enumerate(cls._METADATA_ROWS, start=2):
            lines.append(f'<row r="{row_idx}">')
            value = _lookup(key)
            if isinstance(value, bool):
                display = "是" if value else "否"
            elif value is None:
                display = ""
            else:
                display = str(value)
            for letter, val in zip(["A", "B"], [header, display]):
                escaped = escape(val)
                lines.append(
                    f'<c r="{letter}{row_idx}" t="inlineStr"><is><t>{escaped}</t></is></c>'
                )
            lines.append("</row>")

        lines.append("</sheetData>")
        lines.append("</worksheet>")
        return "\n".join(lines)

    @staticmethod
    def _styles_xml() -> str:
        """最小样式表:index 0 默认,index 1 wrapText + 顶端对齐(批量导出值列用)。"""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>\n'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>\n'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>\n'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>\n'
            '<cellXfs count="2">\n'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>\n'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
            '<alignment wrapText="1" vertical="top"/></xf>\n'
            '</cellXfs>\n'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>\n'
            '</styleSheet>'
        )

    @classmethod
    def _batch_sheet_xml(cls, rows: list[dict]) -> str:
        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
            # 第 9 列"任务编号"隐藏,便于结果回查且不干扰医生
            '<cols><col min="9" max="9" width="0" hidden="1"/></cols>',
            "<sheetData>",
        ]
        lines.append('<row r="1">')
        for i, header in enumerate(cls._BATCH_HEADERS):
            escaped = escape(header)
            lines.append(f'<c r="{cls._BATCH_COL_LETTERS[i]}1" t="inlineStr"><is><t>{escaped}</t></is></c>')
        lines.append("</row>")

        for row_idx, row in enumerate(rows, start=2):
            lines.append(f'<row r="{row_idx}">')
            values = [
                str(row["serial"]),
                row.get("patient_name", ""),
            ]
            for group_key, _ in cls._BATCH_MODULE_COLUMNS:
                values.append(row.get("cells", {}).get(group_key, ""))
            values.append(row["task_id"])
            for i, val in enumerate(values):
                letter = cls._BATCH_COL_LETTERS[i]
                style = "" if i == 0 else ' s="1"'
                escaped = escape(val)
                lines.append(f'<c r="{letter}{row_idx}"{style} t="inlineStr"><is><t>{escaped}</t></is></c>')
            lines.append("</row>")

        lines.append("</sheetData>")
        lines.append("</worksheet>")
        return "\n".join(lines)

    def _write_batch_xlsx(self, path: str, rows: list[dict]) -> None:
        sheet_name = self._build_sheet_names([self._BATCH_SHEET_NAME])[0]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", self._content_types_xml(1, include_styles=True))
            z.writestr("_rels/.rels", self._rels_xml())
            z.writestr("xl/workbook.xml", self._workbook_xml([sheet_name]))
            z.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml([sheet_name]))
            z.writestr("xl/styles.xml", self._styles_xml())
            z.writestr("xl/worksheets/sheet1.xml", self._batch_sheet_xml(rows))

    def _build_sheet_names(self, raw_names: list[str]) -> list[str]:
        names = []
        seen = {}
        for raw_name in raw_names:
            sanitized = self._sanitize_sheet_name(raw_name)
            count = seen.get(sanitized, 0)
            if count:
                suffix = str(count + 1)
                names.append(f"{sanitized[:31 - len(suffix)]}{suffix}")
            else:
                names.append(sanitized)
            seen[sanitized] = count + 1
        return names

    @staticmethod
    def _sanitize_sheet_name(name: str) -> str:
        result = name[:31]
        for ch in r"[]:*?/\\":
            result = result.replace(ch, "_")
        return result

    @staticmethod
    def _content_types_xml(sheet_count: int, include_styles: bool = False) -> str:
        types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        ]
        if include_styles:
            types.append(
                '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            )
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
            evidence_value = cls._serialize_evidence_for_excel(field.get("evidence"))
            values = [
                field.get("field_key", ""),
                field.get("field_name", ""),
                field.get("final_value", ""),
                field.get("status", ""),
                str(field.get("page_no") or ""),
                evidence_value,
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
