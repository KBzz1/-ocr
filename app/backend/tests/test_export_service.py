import json
import os
import zipfile

import pytest

from app.backend.enums import FieldStatus
from app.backend.errors import AppError, ErrorCode
from app.backend.services.export_service import ExportService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_export_service(tmp_path):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    return ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "1.0.0",
            "document_type": "general_medical_record",
            "field_groups": [
                {"group_key": "basic", "group_label": "基本信息", "fields": [{"field_key": "patient_name", "label": "姓名"}]}
            ],
        },
    ), task_service


def write_task(store, task_id="task_001", status="review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-05-19T10:00:00+00:00",
            "updated_at": "2026-05-19T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
        },
    )


def write_review_result(store, task_id="task_001", status=FieldStatus.CONFIRMED.value):
    store.write(
        f"results/{task_id}/review_result.json",
        {
            "task_id": task_id,
            "schema_version": "1.0.0",
            "document_type": "general_medical_record",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "final_value": "张三",
                    "status": status,
                    "evidence": "第1页",
                    "page_no": 1,
                    "reviewed_at": "2026-05-19T10:10:00+00:00",
                }
            ],
        },
    )


def test_review_task_can_export_json_without_status_change(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, status="review")
    write_review_result(export_service._store)

    info = export_service.export_json("task_001")

    assert info["filename"].endswith(".json")
    assert task_service.get_task("task_001")["status"] == "review"
    assert "json" in task_service.get_task("task_001")["export_summary"]["formats"]


def test_done_task_can_export_excel_without_exported_state(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, status="done")
    write_review_result(export_service._store)

    info = export_service.export_excel("task_001")

    assert info["filename"].endswith(".xlsx")
    assert task_service.get_task("task_001")["status"] == "done"
    assert "excel" in task_service.get_task("task_001")["export_summary"]["formats"]


def test_uploading_task_cannot_export(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, status="uploading")
    write_review_result(export_service._store)

    with pytest.raises(AppError) as exc:
        export_service.export_json("task_001")

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code


def test_unreviewed_field_blocks_export(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, status="review")
    write_review_result(export_service._store, status=FieldStatus.UNREVIEWED.value)

    with pytest.raises(AppError) as exc:
        export_service.export_json("task_001")

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code
    assert exc.value.details["blocking_fields"]["unreviewed"] == ["patient_name"]


def test_export_json_file_uses_final_value(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, status="done")
    write_review_result(export_service._store)

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        content = json.load(f)
    assert content["fields"][0]["final_value"] == "张三"
    assert "auto_value" not in content["fields"][0]
    assert os.path.isabs(info["path"])


def test_export_excel_first_sheet_contains_all_fields_before_group_sheets(tmp_path):
    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "1.0.0",
            "document_type": "copd_admission_record",
            "field_groups": [
                {
                    "group_key": "profile",
                    "group_label": "患者背景",
                    "fields": [
                        {"field_key": "occupation", "label": "职业"},
                        {"field_key": "smoking_history_status", "label": "吸烟状态"},
                    ],
                },
                {
                    "group_key": "exam",
                    "group_label": "体格检查",
                    "fields": [
                        {"field_key": "temperature", "label": "体温"},
                    ],
                },
            ],
        },
    )
    write_task(store, status="done")
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "1.0.0",
            "document_type": "copd_admission_record",
            "fields": [
                {
                    "field_key": "occupation",
                    "field_name": "职业",
                    "final_value": "退休",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "退休",
                    "page_no": 1,
                },
                {
                    "field_key": "smoking_history_status",
                    "field_name": "吸烟状态",
                    "final_value": "已戒烟",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "已戒烟",
                    "page_no": 1,
                },
                {
                    "field_key": "temperature",
                    "field_name": "体温",
                    "final_value": "36.5℃",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "T 36.5℃",
                    "page_no": 2,
                },
            ],
        },
    )

    info = export_service.export_excel("task_001")

    with zipfile.ZipFile(info["path"]) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet1_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        sheet2_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        sheet3_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")

    assert 'sheet name="全部字段"' in workbook_xml
    assert 'sheet name="患者背景"' in workbook_xml
    assert 'sheet name="体格检查"' in workbook_xml
    assert "occupation" in sheet1_xml
    assert "smoking_history_status" in sheet1_xml
    assert "temperature" in sheet1_xml
    assert "occupation" in sheet2_xml
    assert "temperature" not in sheet2_xml
    assert "temperature" in sheet3_xml


def test_batch_zip_exports_json_files_for_multiple_tasks(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="done")
    write_review_result(export_service._store, task_id="task_002")

    info = export_service.export_batch_zip(["task_001", "task_002"])

    assert info["filename"].endswith(".zip")
    with zipfile.ZipFile(info["path"]) as archive:
        assert sorted(archive.namelist()) == [
            "manifest.json",
            "task_001/task_001.review.json",
            "task_002/task_002.review.json",
        ]
        exported = json.loads(archive.read("task_001/task_001.review.json").decode("utf-8"))
    assert exported["fields"][0]["final_value"] == "张三"
    assert "batch_zip" in task_service.get_task("task_001")["export_summary"]["formats"]
    assert "batch_zip" in task_service.get_task("task_002")["export_summary"]["formats"]


def test_batch_zip_rejects_non_exportable_task(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="uploading")
    write_review_result(export_service._store, task_id="task_002")

    with pytest.raises(AppError) as exc:
        export_service.export_batch_zip(["task_001", "task_002"])

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code


def test_batch_zip_writes_manifest_with_export_summary(tmp_path):
    export_service, _task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="done")
    write_review_result(export_service._store, task_id="task_002")

    info = export_service.export_batch_zip(["task_001", "task_002"])

    with zipfile.ZipFile(info["path"]) as archive:
        names = sorted(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

    assert names == ["manifest.json", "task_001/task_001.review.json", "task_002/task_002.review.json"]
    assert manifest["format"] == "batch_zip"
    assert manifest["task_count"] == 2
    assert manifest["success_count"] == 2
    assert manifest["failed_count"] == 0
    assert manifest["failed_tasks"] == []
    assert manifest["success_tasks"][0]["json_path"] == "task_001/task_001.review.json"
    assert manifest["success_tasks"][0]["field_count"] == 1
    assert manifest["success_tasks"][0]["schema_version"] == "1.0.0"
    assert manifest["success_tasks"][0]["document_type"] == "general_medical_record"
    assert manifest["generated_at"]


def test_batch_zip_reports_all_non_exportable_tasks_without_writing_new_zip(tmp_path):
    export_service, task_service = make_export_service(tmp_path)
    write_task(export_service._store, task_id="task_001", status="review")
    write_review_result(export_service._store, task_id="task_001")
    write_task(export_service._store, task_id="task_002", status="uploading")
    write_review_result(export_service._store, task_id="task_002")

    with pytest.raises(AppError) as exc:
        export_service.export_batch_zip(["task_001", "task_002"])

    assert exc.value.code == ErrorCode.EXPORT_VALIDATION_FAILED.code
    assert exc.value.details["format"] == "batch_zip"
    assert exc.value.details["failed_tasks"] == [
        {
            "task_id": "task_002",
            "error_code": "EXPORT_VALIDATION_FAILED",
            "reason": "只有待审核或已完成任务可以导出",
            "status": "uploading",
        }
    ]
    assert "batch_zip" not in task_service.get_task("task_001")["export_summary"]["formats"]
    assert not (tmp_path / "exports" / "batch" / "batch-review-export.zip").exists()


def test_export_uses_task_document_profile_schema_when_available(tmp_path):
    class Profile:
        def __init__(self):
            self.schema = {
                "version": "progress_note.v1",
                "document_type": "progress_note",
                "field_groups": [
                    {
                        "group_key": "progress",
                        "group_label": "病程记录",
                        "fields": [{"field_key": "patient_name", "label": "病程姓名"}],
                    }
                ],
            }

    class FakeDocumentProfiles:
        def get_profile(self, document_type):
            assert document_type == "progress_note"
            return Profile()

    store = JsonStore(str(tmp_path / "data"))
    task_service = TaskService(store=store)
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "1.0.0",
            "document_type": "general_medical_record",
            "field_groups": [
                {"group_key": "basic", "group_label": "基本信息", "fields": [{"field_key": "patient_name", "label": "姓名"}]}
            ],
        },
        document_profiles=FakeDocumentProfiles(),
    )
    write_task(store, status="done")
    task = store.read("tasks/task_001.json")
    task["document_type"] = "progress_note"
    store.write("tasks/task_001.json", task)
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "progress_note.v1",
            "document_type": "progress_note",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "final_value": "张三",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "第1页",
                    "page_no": 1,
                    "reviewed_at": "2026-05-19T10:10:00+00:00",
                }
            ],
        },
    )

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        content = json.load(f)

    assert content["fields"][0]["field_name"] == "病程姓名"
    assert content["schema_version"] == "progress_note.v1"
