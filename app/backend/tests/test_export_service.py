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


def test_compute_blocking_fields_ignores_empty_final_value_placeholders():
    """BE-MVP-05-06: 空 final_value 占位字段不阻断导出。"""
    fields = [
        {"field_key": "patient_name", "final_value": "张三", "status": "confirmed"},
        {"field_key": "occupation", "final_value": "", "status": "unreviewed"},
        {"field_key": "temperature", "final_value": "36.5", "status": "unreviewed"},
    ]
    blocking = ExportService._compute_blocking_fields(fields)
    # occupation 是占位字段(空 final_value),不阻断;temperature 是真未审核,阻断
    assert blocking == ["temperature"]


def test_export_excel_includes_all_schema_fields_when_review_missing_some(tmp_path):
    """BE-MVP-05-06: review 缺 schema 字段时,Excel 仍包含完整 schema 字段并按 schema 顺序排列。"""
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
                        {"field_key": "pulse", "label": "脉搏"},
                    ],
                },
            ],
        },
    )
    write_task(store, status="done")
    # review 只有 2 个字段,schema 实际有 4 个
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

    # 全部 4 个字段都在 sheet1
    for key in ("occupation", "smoking_history_status", "temperature", "pulse"):
        assert key in sheet1_xml, f"sheet1 缺 {key}"
    # 按 schema 顺序
    assert sheet1_xml.index("occupation") < sheet1_xml.index("smoking_history_status")
    assert sheet1_xml.index("temperature") < sheet1_xml.index("pulse")
    assert sheet1_xml.index("smoking_history_status") < sheet1_xml.index("temperature")
    # 分组 sheet 也存在
    assert 'sheet name="患者背景"' in workbook_xml
    assert 'sheet name="体格检查"' in workbook_xml


def test_export_json_includes_all_schema_fields_when_review_missing_some(tmp_path):
    """BE-MVP-05-06: JSON 导出 model 字段集合与 schema 一致。"""
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
                    "group_key": "exam",
                    "group_label": "体格检查",
                    "fields": [
                        {"field_key": "temperature", "label": "体温"},
                        {"field_key": "pulse", "label": "脉搏"},
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
                    "field_key": "temperature",
                    "field_name": "体温",
                    "final_value": "36.5℃",
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "T 36.5℃",
                    "page_no": 1,
                },
            ],
        },
    )

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        model = json.load(f)
    keys = [f["field_key"] for f in model["fields"]]
    assert keys == ["temperature", "pulse"]
    pulse = next(f for f in model["fields"] if f["field_key"] == "pulse")
    assert pulse["final_value"] == ""
    assert pulse["status"] == "unreviewed"


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


# --- Task 6: 导出元数据(患者 + 记录) ---


class _StubPatientService:
    def get(self, patient_id, *, include_deleted=False):
        record = self._patients.get(patient_id)
        if record is None:
            from app.backend.errors import AppError, ErrorCode
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        return record

    def __init__(self):
        self._patients = {}

    def add(self, patient_id, name, deleted_at=None):
        self._patients[patient_id] = {
            "patient_id": patient_id,
            "name": name,
            "deleted_at": deleted_at,
        }


def _make_export_with_patient(tmp_path, patient_id="P-A1B2C3D4", patient_name="测试用例",
                              patient_deleted=False, record_date="2026-06-07",
                              record_time="09:30", document_type="general_medical_record",
                              status="review"):
    store = JsonStore(str(tmp_path / "data"))
    stub = _StubPatientService()
    stub.add(patient_id, patient_name, deleted_at=("2026-06-07T10:00:00+00:00" if patient_deleted else None))

    class PatientAwareTaskService:
        def __init__(self, store, patient_service):
            self._store = store
            self._patient_service = patient_service
            self._impl = TaskService(store=store)

        def get_task(self, task_id):
            task = self._impl.get_task(task_id)
            return task

        def record_export(self, *args, **kwargs):
            return self._impl.record_export(*args, **kwargs)

        def patient_export_metadata(self, task):
            pid = task.get("patient_id")
            if pid is None:
                return {"patient_id": None, "name": None, "deleted": False}
            try:
                record = self._patient_service.get(pid, include_deleted=True)
            except Exception:
                snapshot = task.get("patient_snapshot") or {}
                return {
                    "patient_id": pid,
                    "name": snapshot.get("name"),
                    "deleted": True,
                }
            snapshot = task.get("patient_snapshot") or {}
            return {
                "patient_id": pid,
                "name": record.get("name") or snapshot.get("name"),
                "deleted": bool(record.get("deleted_at")),
            }

    task_service = PatientAwareTaskService(store, stub)
    export_service = ExportService(
        store=store,
        export_dir=str(tmp_path / "exports"),
        task_service=task_service,
        schema_provider=lambda: {
            "version": "1.0.0",
            "document_type": document_type,
            "field_groups": [
                {"group_key": "basic", "group_label": "基本信息", "fields": [{"field_key": "patient_name", "label": "姓名"}]}
            ],
        },
    )
    store.write(
        f"tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": status,
            "created_at": "2026-06-07T10:00:00+00:00",
            "updated_at": "2026-06-07T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "patient_id": patient_id,
            "patient_snapshot": {"patient_id": patient_id, "name": patient_name},
            "document_type": document_type,
            "document_type_label": "入院记录" if document_type == "copd_admission_record" else "通用病历",
            "schema_version": "1.0.0",
            "prompt_version": "1.0.0",
            "record_date": record_date,
            "record_time": record_time,
            "deleted_at": None,
        },
    )
    store.write(
        "results/task_001/review_result.json",
        {
            "task_id": "task_001",
            "schema_version": "1.0.0",
            "document_type": document_type,
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "final_value": patient_name,
                    "status": FieldStatus.CONFIRMED.value,
                    "evidence": "第1页",
                    "page_no": 1,
                }
            ],
        },
    )
    return export_service, store


def test_export_json_includes_patient_and_record_metadata(tmp_path):
    export_service, _ = _make_export_with_patient(tmp_path)

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        content = json.load(f)
    assert content["patient"] == {
        "patient_id": "P-A1B2C3D4",
        "name": "测试用例",
        "deleted": False,
    }
    assert content["record"] == {
        "document_type": "general_medical_record",
        "document_type_label": "通用病历",
        "record_date": "2026-06-07",
        "record_time": "09:30",
    }
    # 元数据不暴露
    assert "metadata_history" not in content
    assert "name_history" not in content


def test_export_json_uses_snapshot_name_when_patient_deleted(tmp_path):
    export_service, _ = _make_export_with_patient(tmp_path, patient_deleted=True,
                                                  patient_name="测试快照")

    info = export_service.export_json("task_001")

    with open(info["path"], encoding="utf-8") as f:
        content = json.load(f)
    assert content["patient"]["name"] == "测试快照"
    assert content["patient"]["deleted"] is True


def test_export_excel_has_task_info_sheet_with_patient_and_record(tmp_path):
    export_service, _ = _make_export_with_patient(tmp_path)

    info = export_service.export_excel("task_001")

    with zipfile.ZipFile(info["path"]) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        names = [name for name in workbook_xml.split("name=") if "sheet" in name]
    assert 'sheet name="任务信息"' in workbook_xml
    assert 'sheet name="全部字段"' in workbook_xml


def test_export_excel_keeps_field_sheets_intact_with_task_info(tmp_path):
    """新增"任务信息" sheet 后,既有"全部字段"和分组 sheet 仍存在,列结构不变。"""
    store = JsonStore(str(tmp_path / "data"))
    stub = _StubPatientService()
    stub.add("P-A1B2C3D4", "测试用例", deleted_at=None)

    class PatientAwareTaskService:
        def __init__(self, store, patient_service):
            self._store = store
            self._patient_service = patient_service
            self._impl = TaskService(store=store)

        def get_task(self, task_id):
            return self._impl.get_task(task_id)

        def record_export(self, *args, **kwargs):
            return self._impl.record_export(*args, **kwargs)

        def patient_export_metadata(self, task):
            pid = task.get("patient_id")
            record = self._patient_service.get(pid, include_deleted=True)
            return {
                "patient_id": pid,
                "name": record.get("name"),
                "deleted": bool(record.get("deleted_at")),
            }

    task_service = PatientAwareTaskService(store, stub)
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
                    ],
                },
            ],
        },
    )
    store.write(
        "tasks/task_001.json",
        {
            "task_id": "task_001",
            "status": "done",
            "created_at": "2026-06-07T10:00:00+00:00",
            "updated_at": "2026-06-07T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "patient_id": "P-A1B2C3D4",
            "patient_snapshot": {"patient_id": "P-A1B2C3D4", "name": "测试用例"},
            "document_type": "copd_admission_record",
            "document_type_label": "入院记录",
            "schema_version": "1.0.0",
            "prompt_version": "1.0.0",
            "record_date": "2026-06-07",
            "record_time": "09:30",
            "deleted_at": None,
        },
    )
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
            ],
        },
    )

    info = export_service.export_excel("task_001")

    with zipfile.ZipFile(info["path"]) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet1 = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        sheet2 = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        sheet3 = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")

    # 既有 sheet 与新增任务信息 sheet 都存在
    assert 'sheet name="全部字段"' in workbook_xml
    assert 'sheet name="患者背景"' in workbook_xml
    assert 'sheet name="任务信息"' in workbook_xml
    # 全部字段 sheet 仍包含 6 列(字段 key/字段名/final_value/状态/来源页/来源证据)
    for header in ("字段 key", "字段名", "final_value", "状态", "来源页", "来源证据"):
        assert header in sheet1
    # 分组 sheet 仍只包含对应字段
    assert "occupation" in sheet2
    # 任务信息 sheet(第三张)包含患者和记录元数据
    for keyword in ("P-A1B2C3D4", "测试用例", "入院记录", "2026-06-07", "09:30"):
        assert keyword in sheet3, f"任务信息 sheet 缺 {keyword}"


def test_batch_zip_model_includes_patient_and_record_metadata(tmp_path):
    export_service, _ = _make_export_with_patient(tmp_path)

    info = export_service.export_batch_zip(["task_001"])

    with zipfile.ZipFile(info["path"]) as archive:
        exported = json.loads(archive.read("task_001/task_001.review.json").decode("utf-8"))
    assert exported["patient"]["patient_id"] == "P-A1B2C3D4"
    assert exported["record"]["record_date"] == "2026-06-07"


def test_export_json_rejects_deleted_task(tmp_path):
    export_service, store = _make_export_with_patient(tmp_path)
    task = store.read("tasks/task_001.json")
    task["deleted_at"] = "2026-06-07T11:00:00+00:00"
    store.write("tasks/task_001.json", task)

    from app.backend.errors import AppError, ErrorCode
    with pytest.raises(AppError) as exc:
        export_service.export_json("task_001")
    assert exc.value.code == ErrorCode.TASK_NOT_FOUND.code
