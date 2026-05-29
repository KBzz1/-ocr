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
