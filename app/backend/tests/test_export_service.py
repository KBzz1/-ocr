import json
import os

import pytest

from app.backend.enums import FieldStatus, TaskStatus
from app.backend.errors import AppError, ErrorCode
from app.backend.storage.json_store import JsonStore


def _make_export_service(tmp_path, task_service=None, schema_provider=None):
    from app.backend.services.export_service import ExportService
    from app.backend.services.task_service import TaskService

    store = JsonStore(str(tmp_path / "data"))
    export_dir = str(tmp_path / "exports")
    if task_service is None:
        task_service = TaskService(store=store)
    return ExportService(
        store=store,
        export_dir=export_dir,
        task_service=task_service,
        schema_provider=schema_provider,
    )


def _write_task(store, task_id="task-001", status="confirmed", **overrides):
    task = {
        "task_id": task_id,
        "session_id": "session-001",
        "status": status,
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2,
        "page_order": ["page-1", "page-2"],
        "source": "capture_session",
        "schema_version": "1.0.0",
        "document_type": "general_medical_record",
    }
    task.update(overrides)
    store.write(f"tasks/{task_id}.json", task)
    return task


def _write_review_result(store, task_id="task-001", fields=None):
    if fields is None:
        fields = [
            {
                "field_key": "chief_complaint",
                "field_name": "主诉",
                "auto_value": "auto_headache",
                "final_value": "头痛3天",
                "evidence": "第1页第2行",
                "page_no": 1,
                "confidence": 0.95,
                "status": FieldStatus.CONFIRMED.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": "2026-05-13T09:55:00+00:00",
                "updated_at": "2026-05-13T09:55:00+00:00",
                "history": [],
            },
            {
                "field_key": "diagnosis",
                "field_name": "诊断",
                "auto_value": "auto_diag",
                "final_value": "上呼吸道感染",
                "evidence": "第2页第1行",
                "page_no": 2,
                "confidence": 0.8,
                "status": FieldStatus.CONFIRMED.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": "2026-05-13T09:56:00+00:00",
                "updated_at": "2026-05-13T09:56:00+00:00",
                "history": [],
            },
        ]
    review = {
        "task_id": task_id,
        "schema_version": "1.0.0",
        "document_type": "general_medical_record",
        "initialized_at": "2026-05-13T09:50:00+00:00",
        "updated_at": "2026-05-13T09:56:00+00:00",
        "fields": fields,
        "summary": {
            "total_count": len(fields),
            "unreviewed_count": sum(1 for f in fields if f["status"] == FieldStatus.UNREVIEWED.value),
            "confirmed_count": sum(1 for f in fields if f["status"] == FieldStatus.CONFIRMED.value),
            "modified_count": sum(1 for f in fields if f["status"] == FieldStatus.MODIFIED.value),
            "suspicious_count": sum(1 for f in fields if f["status"] == FieldStatus.SUSPICIOUS.value),
            "empty_count": sum(1 for f in fields if f["status"] == FieldStatus.EMPTY.value),
            "empty_unaccepted_count": sum(1 for f in fields if f["status"] == FieldStatus.EMPTY.value and not f["empty_accepted"]),
            "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
        },
    }
    store.write(f"results/{task_id}/review_result.json", review)
    return review


_SAMPLE_SCHEMA = {
    "version": "1.0.0",
    "document_type": "general_medical_record",
    "field_groups": [
        {
            "group_key": "admission_info",
            "group_label": "入院/病程信息",
            "fields": [
                {"field_key": "chief_complaint", "label": "主诉", "type": "string"},
            ],
        },
        {
            "group_key": "diagnosis",
            "group_label": "诊断相关",
            "fields": [
                {"field_key": "diagnosis", "label": "诊断", "type": "string"},
            ],
        },
    ],
}


class TestExportCheck:
    def test_check_confirmed_task_can_export(self, tmp_path):
        svc = _make_export_service(tmp_path)
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        result = svc.check("task-001")

        assert result["task_id"] == "task-001"
        assert result["status"] == "confirmed"
        assert result["can_export"] is True
        assert result["summary"]["total_count"] == 2
        assert result["summary"]["unreviewed_count"] == 0
        assert result["blocking_fields"]["unreviewed"] == []
        assert result["blocking_fields"]["suspicious"] == []
        assert result["blocking_fields"]["empty_unaccepted"] == []

    def test_check_rejects_ready_for_review_task(self, tmp_path):
        svc = _make_export_service(tmp_path)
        _write_task(svc._store, status="ready_for_review")
        _write_review_result(svc._store)

        with pytest.raises(AppError) as exc_info:
            svc.check("task-001")

        assert exc_info.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code

    def test_check_rejects_missing_review_result(self, tmp_path):
        svc = _make_export_service(tmp_path)
        _write_task(svc._store, status="confirmed")
        # No review_result written

        with pytest.raises(AppError) as exc_info:
            svc.check("task-001")

        assert exc_info.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code

    def test_check_blocks_unreviewed_suspicious_and_empty_unaccepted_fields(self, tmp_path):
        svc = _make_export_service(tmp_path)
        _write_task(svc._store, status="confirmed")
        fields = [
            {
                "field_key": "f1",
                "field_name": "字段1",
                "auto_value": "auto1",
                "final_value": "ok",
                "evidence": "ev1",
                "page_no": 1,
                "confidence": 0.9,
                "status": FieldStatus.UNREVIEWED.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": None,
                "updated_at": None,
                "history": [],
            },
            {
                "field_key": "f2",
                "field_name": "字段2",
                "auto_value": "auto2",
                "final_value": "ok",
                "evidence": "ev2",
                "page_no": 1,
                "confidence": 0.8,
                "status": FieldStatus.SUSPICIOUS.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": None,
                "updated_at": None,
                "history": [],
            },
            {
                "field_key": "f3",
                "field_name": "字段3",
                "auto_value": "",
                "final_value": "",
                "evidence": None,
                "page_no": None,
                "confidence": None,
                "status": FieldStatus.EMPTY.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": None,
                "updated_at": None,
                "history": [],
            },
            {
                "field_key": "f4",
                "field_name": "字段4",
                "auto_value": "auto4",
                "final_value": "fixed",
                "evidence": "ev4",
                "page_no": 1,
                "confidence": 0.7,
                "status": FieldStatus.MODIFIED.value,
                "empty_accepted": False,
                "review_note": None,
                "reviewed_at": "2026-05-13T09:55:00+00:00",
                "updated_at": "2026-05-13T09:55:00+00:00",
                "history": [],
            },
        ]
        _write_review_result(svc._store, fields=fields)

        result = svc.check("task-001")

        assert result["can_export"] is False
        assert result["summary"]["unreviewed_count"] == 1
        assert result["summary"]["suspicious_count"] == 1
        assert result["summary"]["empty_count"] == 1
        assert result["summary"]["empty_unaccepted_count"] == 1
        assert result["summary"]["missing_evidence_count"] == 1
        assert result["blocking_fields"]["unreviewed"] == ["f1"]
        assert result["blocking_fields"]["suspicious"] == ["f2"]
        assert result["blocking_fields"]["empty_unaccepted"] == ["f3"]


class TestExportModel:
    def test_export_model_uses_final_value_not_auto_value_and_keeps_order(self, tmp_path):
        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        model = svc._build_export_model("task-001")

        assert model["task_id"] == "task-001"
        assert model["schema_version"] == "1.0.0"
        assert model["document_type"] == "general_medical_record"
        assert "exported_at" in model
        # Order preserved from review_result
        assert [f["field_key"] for f in model["fields"]] == ["chief_complaint", "diagnosis"]
        # final_value used, auto_value NOT present in model
        chief = model["fields"][0]
        assert chief["final_value"] == "头痛3天"
        assert "auto_value" not in chief
        # group info from schema
        assert chief["group_key"] == "admission_info"
        assert chief["group_label"] == "入院/病程信息"
        # second field
        diag = model["fields"][1]
        assert diag["final_value"] == "上呼吸道感染"
        assert diag["group_key"] == "diagnosis"
        assert diag["group_label"] == "诊断相关"
        # summary
        assert model["summary"]["total_count"] == 2


class TestExportJson:
    def test_export_json_writes_task_scoped_file(self, tmp_path):
        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        info = svc.export_json("task-001")

        assert os.path.exists(info["path"])
        # Verify file is in exports/{task_id}/
        assert f"exports{os.sep}task-001" in info["path"]
        assert info["relative_path"] == "task-001/task-001.review.json"
        assert info["filename"] == "task-001.review.json"

        # Verify content
        with open(info["path"], "r", encoding="utf-8") as f:
            content = json.loads(f.read())
        assert content["task_id"] == "task-001"
        assert "exported_at" in content
        assert [f["field_key"] for f in content["fields"]] == ["chief_complaint", "diagnosis"]
        # final_value only, no auto_value
        for field in content["fields"]:
            assert "auto_value" not in field
            assert "final_value" in field

    def test_export_json_returns_relative_path_and_download_name(self, tmp_path):
        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        info = svc.export_json("task-001")

        assert info["format"] == "json"
        assert info["relative_path"] == "task-001/task-001.review.json"
        assert info["filename"] == "task-001.review.json"
        assert os.path.isabs(info["path"])

    def test_export_json_write_failure_keeps_task_confirmed_and_review_unchanged(self, tmp_path, monkeypatch):
        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        review_before = _write_review_result(svc._store)

        # Simulate write failure by making export_dir a path that can't be created
        # (point it to a file instead of a directory, so makedirs fails)
        bad_export = tmp_path / "not_a_dir"
        bad_export.write_text("block")
        monkeypatch.setattr(svc, "_export_dir", str(bad_export))

        with pytest.raises(AppError) as exc_info:
            svc.export_json("task-001")

        assert exc_info.value.code == ErrorCode.EXPORT_FAILED.code
        assert exc_info.value.details["format"] == "json"

        # Task status must still be confirmed
        task = svc._store.read("tasks/task-001.json")
        assert task["status"] == "confirmed"

        # review_result must be unchanged
        review_after = svc._store.read("results/task-001/review_result.json")
        assert review_after == review_before


class TestExportExcel:
    def test_export_excel_writes_valid_xlsx_zip(self, tmp_path):
        import zipfile as zf

        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        info = svc.export_excel("task-001")

        assert os.path.exists(info["path"])
        assert info["relative_path"] == "task-001/task-001.review.xlsx"
        assert info["filename"] == "task-001.review.xlsx"

        # Verify it's a valid ZIP with required XLSX files
        with zf.ZipFile(info["path"], "r") as z:
            names = z.namelist()
            assert "[Content_Types].xml" in names
            assert "xl/workbook.xml" in names
            assert "xl/_rels/workbook.xml.rels" in names
            assert any(n.startswith("xl/worksheets/sheet") for n in names)

    def test_export_excel_groups_fields_by_schema_group(self, tmp_path):
        import zipfile as zf

        # Schema with two groups
        schema = {
            "version": "1.0.0",
            "document_type": "general_medical_record",
            "field_groups": [
                {
                    "group_key": "admission_info",
                    "group_label": "入院/病程信息",
                    "fields": [
                        {"field_key": "chief_complaint", "label": "主诉", "type": "string"},
                    ],
                },
                {
                    "group_key": "diagnosis",
                    "group_label": "诊断相关",
                    "fields": [
                        {"field_key": "diagnosis", "label": "诊断", "type": "string"},
                    ],
                },
            ],
        }
        svc = _make_export_service(tmp_path, schema_provider=lambda: schema)
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        info = svc.export_excel("task-001")

        with zf.ZipFile(info["path"], "r") as z:
            # Two sheets for two groups
            sheet_names = [
                n for n in z.namelist()
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
            ]
            assert len(sheet_names) == 2

            # workbook.xml should list both sheet names
            wb_xml = z.read("xl/workbook.xml").decode("utf-8")
            assert "入院_病程信息" in wb_xml
            assert "诊断相关" in wb_xml

    def test_export_excel_contains_final_value_not_auto_value(self, tmp_path):
        import zipfile as zf

        svc = _make_export_service(
            tmp_path,
            schema_provider=lambda: _SAMPLE_SCHEMA,
        )
        _write_task(svc._store, status="confirmed")
        _write_review_result(svc._store)

        info = svc.export_excel("task-001")

        with zf.ZipFile(info["path"], "r") as z:
            # Read all sheet XMLs concatenated
            sheet_xmls = []
            for name in z.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    sheet_xmls.append(z.read(name).decode("utf-8"))

            all_sheet_text = "".join(sheet_xmls)

            # final_value present
            assert "头痛3天" in all_sheet_text
            assert "上呼吸道感染" in all_sheet_text

            # auto_value NEVER present in export
            assert "auto_headache" not in all_sheet_text
            assert "auto_diag" not in all_sheet_text
