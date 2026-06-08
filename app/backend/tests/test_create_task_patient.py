"""Task 3: 创建任务时绑定患者和记录时间。"""
from datetime import datetime

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_service(store, *, patient_service=None, document_profiles=None):
    return TaskService(
        store=store,
        orchestrator=None,
        schema_provider=lambda: {"version": "1.0.0", "document_type": "copd_admission_record"},
        background_runner=lambda task_id, run: run(),
        patient_service=patient_service,
        document_profiles=document_profiles,
    )


def test_create_task_binds_patient_and_record_metadata(tmp_path):
    store = JsonStore(str(tmp_path))
    patient_service = type(
        "P",
        (),
        {
            "get_bindable": staticmethod(
                lambda patient_id: {
                    "patient_id": patient_id,
                    "name": "测试用例",
                    "deleted_at": None,
                }
            )
        },
    )()
    service = make_service(store, patient_service=patient_service)

    task = service.create_uploading_task(
        base_url="http://127.0.0.1:8081",
        patient_id="P-ABCDEF12",
        document_type="copd_admission_record",
        record_date="2026-06-07",
        record_time="09:30",
    )

    assert task["patient_id"] == "P-ABCDEF12"
    assert task["patient_snapshot"] == {"patient_id": "P-ABCDEF12", "name": "测试用例"}
    assert task["record_date"] == "2026-06-07"
    assert task["record_time"] == "09:30"
    assert task["deleted_at"] is None
    assert task["metadata_history"] == []


def test_create_task_rejects_missing_patient_id(tmp_path):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            document_type="copd_admission_record",
            record_date="2026-06-07",
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_create_task_rejects_blank_date(tmp_path):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-ABCDEF12",
            document_type="copd_admission_record",
            record_date="",
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code
    assert exc.value.message == "record_date 必填"


def test_create_task_rejects_missing_date_with_required_message(tmp_path):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-ABCDEF12",
            document_type="copd_admission_record",
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code
    assert exc.value.message == "record_date 必填"


def test_create_task_rejects_blank_document_type(tmp_path):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-ABCDEF12",
            document_type="",
            record_date="2026-06-07",
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


@pytest.mark.parametrize(
    "record_date",
    ["2026-13-45", "2026-02-30", "2026/06/07", "abc"],
)
def test_create_task_rejects_invalid_date(tmp_path, record_date):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-ABCDEF12",
            document_type="copd_admission_record",
            record_date=record_date,
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


@pytest.mark.parametrize(
    "record_time",
    ["24:00", "23:60", "abc"],
)
def test_create_task_rejects_invalid_time(tmp_path, record_time):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-ABCDEF12",
            document_type="copd_admission_record",
            record_date="2026-06-07",
            record_time=record_time,
        )

    assert exc.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_create_task_id_uses_max_plus_one_even_with_gaps(tmp_path):
    store = JsonStore(str(tmp_path))
    store.write(
        "tasks/1.json",
        {
            "task_id": "1",
            "status": "uploading",
            "created_at": "2026-06-07T10:00:00+08:00",
            "updated_at": "2026-06-07T10:00:00+08:00",
            "images": [],
        },
    )
    store.write(
        "tasks/5.json",
        {
            "task_id": "5",
            "status": "uploading",
            "created_at": "2026-06-07T10:00:00+08:00",
            "updated_at": "2026-06-07T10:00:00+08:00",
            "images": [],
        },
    )
    store.write(
        "tasks/task_legacy.json",
        {
            "task_id": "task_legacy",
            "status": "uploading",
            "created_at": "2026-06-07T10:00:00+08:00",
            "updated_at": "2026-06-07T10:00:00+08:00",
            "images": [],
        },
    )
    service = make_service(store, patient_service=_StubPatientService())

    task = service.create_uploading_task(
        base_url="http://127.0.0.1:8081",
        patient_id="P-ABCDEF12",
        document_type="copd_admission_record",
        record_date="2026-06-07",
    )

    assert task["task_id"] == "6"
    assert store.exists("tasks/task_legacy.json") is True


def test_create_task_rejects_deleted_patient(tmp_path):
    class _DeletedPatient:
        def get_bindable(self, patient_id):
            raise AppError(ErrorCode.PATIENT_DELETED)

    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_DeletedPatient())

    with pytest.raises(AppError) as exc:
        service.create_uploading_task(
            base_url="http://127.0.0.1:8081",
            patient_id="P-DELETED1",
            document_type="copd_admission_record",
            record_date="2026-06-07",
        )

    assert exc.value.code == ErrorCode.PATIENT_DELETED.code


def test_create_task_record_time_can_be_none(tmp_path):
    store = JsonStore(str(tmp_path))
    service = make_service(store, patient_service=_StubPatientService())

    task = service.create_uploading_task(
        base_url="http://127.0.0.1:8081",
        patient_id="P-ABCDEF12",
        document_type="copd_admission_record",
        record_date="2026-06-07",
    )

    assert task["record_time"] is None


class _StubPatientService:
    def get_bindable(self, patient_id):
        return {"patient_id": patient_id, "name": "测试用例", "deleted_at": None}
