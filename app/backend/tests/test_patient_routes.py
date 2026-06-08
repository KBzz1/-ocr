"""患者 API 路由测试。"""
import pytest

from app.backend.errors import ErrorCode
from app.backend.storage.json_store import JsonStore
from app.backend.tests.fixtures.client import make_client


def test_patient_crud_contract(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    created = client.post("/api/patients", json={"name": "测试患者"})
    assert created.status_code == 201
    patient_id = created.get_json()["data"]["patient_id"]
    assert patient_id.startswith("P-")

    search = client.get("/api/patients?query=测试患者")
    assert search.status_code == 200
    payload = search.get_json()["data"]["patients"]
    assert any(item["patient_id"] == patient_id for item in payload)

    detail = client.get(f"/api/patients/{patient_id}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["name"] == "测试患者"
    assert "name_history" not in detail.get_json()["data"]

    patched = client.patch(f"/api/patients/{patient_id}", json={"name": "测试用例"})
    assert patched.status_code == 200
    assert patched.get_json()["data"]["name"] == "测试用例"


def test_create_patient_rejects_blank_name(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.post("/api/patients", json={"name": "   "})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_get_missing_patient_returns_404(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/patients/P-MISSING01")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.PATIENT_NOT_FOUND.code


def test_rename_patient_appends_history_but_does_not_leak(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = client.post("/api/patients", json={"name": "甲"}).get_json()["data"]
    patient_id = created["patient_id"]

    renamed = client.patch(f"/api/patients/{patient_id}", json={"name": "乙"})
    assert renamed.status_code == 200
    assert "name_history" not in renamed.get_json()["data"]


def test_rename_patient_rejects_blank(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = client.post("/api/patients", json={"name": "甲"}).get_json()["data"]

    response = client.patch(f"/api/patients/{created['patient_id']}", json={"name": ""})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_get_patient_records_returns_grouped_timeline(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    for record_date, record_time, doc_type in (
        ("2026-06-07", "09:30", "copd_admission_record"),
        ("2026-06-07", None, "copd_admission_record"),
    ):
        body = {
            "patient_id": patient["patient_id"],
            "document_type": doc_type,
            "record_date": record_date,
        }
        if record_time is not None:
            body["record_time"] = record_time
        resp = client.post("/api/tasks", json=body)
        assert resp.status_code == 201

    response = client.get(f"/api/patients/{patient['patient_id']}/records")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["patient"]["patient_id"] == patient["patient_id"]
    [group] = data["record_groups"]
    assert group["document_type"] == "copd_admission_record"
    record_times = [t["record_time"] for t in group["tasks"]]
    assert record_times == ["09:30", None]


def test_get_patient_records_returns_404_for_unknown_patient(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/patients/P-MISSING01/records")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == ErrorCode.PATIENT_NOT_FOUND.code


def test_list_patients_includes_task_count_and_latest_record_at(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    client.post(
        "/api/tasks",
        json={
            "patient_id": patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
            "record_time": "09:30",
        },
    )

    response = client.get("/api/patients")
    items = response.get_json()["data"]["patients"]
    target = next(item for item in items if item["patient_id"] == patient["patient_id"])
    assert target["task_count"] == 1
    assert target["latest_record_at"] == "2026-06-07T09:30"


# --- Task 6: 逻辑删除患者/任务 ---


def _create_patient(client, name="测试用例"):
    return client.post("/api/patients", json={"name": name}).get_json()["data"]


def _write_task_with_patient(app, task_id, patient_id, status="review"):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "status": status,
            "created_at": "2026-06-07T10:00:00+00:00",
            "updated_at": "2026-06-07T10:00:00+00:00",
            "upload_token": "token_001",
            "images": [],
            "error_code": None,
            "error_message": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "patient_id": patient_id,
            "patient_snapshot": {"patient_id": patient_id, "name": "测试用例"},
            "record_date": "2026-06-07",
            "record_time": None,
            "deleted_at": None,
            "metadata_history": [],
            "document_type": "copd_admission_record",
            "document_type_label": "入院记录",
            "schema_version": "copd_admission_record.v1",
            "prompt_version": "copd_admission_record.prompt.v1",
            "extraction_profile": "copd_admission_record",
        },
    )


def test_delete_patient_only_keeps_tasks_visible_with_deleted_marker(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(app, "1", patient["patient_id"], status="review")

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")

    assert response.status_code == 200
    assert response.get_json()["data"]["deleted"] is True
    # 任务仍然能查到,且 patient.deleted 标记
    task_resp = client.get("/api/tasks/1").get_json()["data"]
    assert task_resp["status"] == "review"
    assert task_resp["patient"]["deleted"] is True
    # 任务 JSON 仍在
    assert JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"]).exists("tasks/1.json")


def test_delete_patient_and_tasks_hides_tasks_without_deleting_files(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(app, "1", patient["patient_id"], status="review")
    storage = app.config["BACKEND_CONFIG"]["storage_dir"]
    store = JsonStore(storage)
    store.write("results/1/review_result.json", {"task_id": "1", "fields": []})
    import os
    os.makedirs(os.path.join(storage, "pages", "1"), exist_ok=True)
    pages_marker = os.path.join(storage, "pages", "1", "marker.txt")
    with open(pages_marker, "w", encoding="utf-8") as f:
        f.write("page")
    results_marker = os.path.join(storage, "results", "1", "marker.txt")
    with open(results_marker, "w", encoding="utf-8") as f:
        f.write("result")

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=true")

    assert response.status_code == 200
    assert client.get("/api/tasks/1").status_code == 404
    # 任务 JSON 与 results/pages 都保留
    assert store.exists("tasks/1.json")
    assert store.exists("results/1/review_result.json")
    assert os.path.exists(pages_marker)
    assert os.path.exists(results_marker)


def test_delete_patient_with_processing_tasks_is_rejected(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(app, "1", patient["patient_id"], status="processing")

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=true")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
    # 患者仍未删除
    detail = client.get(f"/api/patients/{patient['patient_id']}")
    assert detail.status_code == 200


def test_delete_patient_and_tasks_keeps_patient_active_if_task_delete_races_to_processing(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(app, "1", patient["patient_id"], status="review")
    task_service = app.config["TASK_SERVICE"]
    original_delete_task = task_service.delete_task

    def race_to_processing(task_id):
        store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
        raw = store.read(f"tasks/{task_id}.json")
        raw["status"] = "processing"
        store.write(f"tasks/{task_id}.json", raw)
        return original_delete_task(task_id)

    monkeypatch.setattr(task_service, "delete_task", race_to_processing)

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=true")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
    detail = client.get(f"/api/patients/{patient['patient_id']}")
    assert detail.status_code == 200


def test_delete_patient_with_processing_tasks_allowed_when_only_patient(tmp_path, monkeypatch):
    """仅删除患者时不应被 processing 任务阻断。"""
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(app, "1", patient["patient_id"], status="processing")

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")

    assert response.status_code == 200
    task_resp = client.get("/api/tasks/1").get_json()["data"]
    assert task_resp["status"] == "processing"
    assert task_resp["patient"]["deleted"] is True


def test_delete_patient_invalid_delete_tasks_value_returns_400(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")

    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=other")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"


def test_delete_patient_missing_returns_404(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.delete("/api/patients/P-MISSING01?delete_tasks=false")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_delete_patient_twice_returns_404(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")

    first = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")
    second = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")

    assert first.status_code == 200
    assert second.status_code == 404
    assert second.get_json()["error"]["code"] == "PATIENT_NOT_FOUND"


def test_deleted_patient_blocks_task_rebind(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    _write_task_with_patient(client.application, "1", patient["patient_id"], status="review")

    client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")
    response = client.patch(
        "/api/tasks/1/metadata",
        json={"patient_id": patient["patient_id"]},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PATIENT_DELETED"


def test_delete_patient_refreshes_snapshots_for_attached_tasks_only(tmp_path, monkeypatch):
    """仅刷新 patient_id 仍指向该患者且未删除任务的 patient_snapshot;
    已改绑或已删除任务不受影响。"""
    client, app = make_client(tmp_path, monkeypatch)
    patient = _create_patient(client, "测试用例")
    other = _create_patient(client, "其他患者")
    # 任务 1:仍指向 patient,未删除
    _write_task_with_patient(app, "1", patient["patient_id"], status="review")
    # 任务 2:已改绑到其他患者
    _write_task_with_patient(app, "2", other["patient_id"], status="review")
    # 任务 3:仍指向 patient 但已逻辑删除
    _write_task_with_patient(app, "3", patient["patient_id"], status="review")
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    raw = store.read("tasks/3.json")
    raw["deleted_at"] = "2026-06-07T11:00:00+00:00"
    raw["patient_snapshot"] = {"patient_id": patient["patient_id"], "name": "旧名"}
    store.write("tasks/3.json", raw)
    # 任务 2 原始快照记录在改绑前,确认未刷新
    raw2 = store.read("tasks/2.json")
    raw2["patient_snapshot"] = {"patient_id": other["patient_id"], "name": "其他原始名"}
    store.write("tasks/2.json", raw2)

    client.patch(
        f"/api/patients/{patient['patient_id']}",
        json={"name": "测试患者新名"},
    )
    response = client.delete(f"/api/patients/{patient['patient_id']}?delete_tasks=false")
    assert response.status_code == 200

    # 任务 1 快照被刷新
    task1 = store.read("tasks/1.json")
    assert task1["patient_snapshot"]["name"] == "测试患者新名"
    assert task1["patient_snapshot"]["patient_id"] == patient["patient_id"]
    # 任务 2 未被改动(patient_id 已不是被删除的患者)
    task2 = store.read("tasks/2.json")
    assert task2["patient_snapshot"]["name"] == "其他原始名"
    # 任务 3 保持原状(已删除任务不刷新)
    task3 = store.read("tasks/3.json")
    assert task3["patient_snapshot"]["name"] == "旧名"
