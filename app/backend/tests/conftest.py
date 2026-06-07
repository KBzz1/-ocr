"""共享 pytest fixtures,服务患者中心新增测试。

注意:旧测试仍按自己的辅助函数写测试,这些 fixture 只服务本轮新增测试。
"""
import io

import pytest

from app.backend.services.patient_service import PatientService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def store(tmp_path):
    return JsonStore(str(tmp_path))


@pytest.fixture
def patient_service(store):
    return PatientService(store, now=lambda: "2026-06-07T10:00:00+08:00")


@pytest.fixture
def task_service(store):
    return TaskService(
        store=store,
        schema_provider=lambda: {
            "version": "1.0.0",
            "document_type": "copd_admission_record",
            "field_groups": [],
        },
        background_runner=lambda task_id, run: run(),
    )


def _write_task(store, task_id="1", status="uploading", **overrides):
    base = {
        "task_id": task_id,
        "status": status,
        "created_at": "2026-06-07T10:00:00+08:00",
        "updated_at": "2026-06-07T10:00:00+08:00",
        "upload_token": "token_001",
        "images": [],
        "error_code": None,
        "error_message": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
    }
    base.update(overrides)
    store.write(f"tasks/{task_id}.json", base)
    return base


@pytest.fixture
def write_task(store):
    def _factory(task_id="1", status="uploading", **overrides):
        return _write_task(store, task_id=task_id, status=status, **overrides)
    return _factory


@pytest.fixture
def seeded_patient_task(client, patient_service, write_task):
    patient = patient_service.create("测试用例")
    task = write_task(status="review", patient_id=patient["patient_id"])
    return patient["patient_id"], task["task_id"]


@pytest.fixture
def seeded_processing_patient_task(client, patient_service, write_task):
    patient = patient_service.create("测试用例")
    task = write_task(status="processing", patient_id=patient["patient_id"])
    return patient["patient_id"], task["task_id"]
