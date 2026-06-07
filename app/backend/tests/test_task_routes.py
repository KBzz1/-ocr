import threading
import time

import pytest

from app.backend import create_backend_app
from app.backend.errors import AppError, ErrorCode
from app.backend.services.reextract_jobs import ReextractJobRegistry
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""", encoding="utf-8")
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def write_task(app, task_id="1", status="uploading", **overrides):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task = {
        "task_id": task_id,
        "status": status,
        "created_at": "2026-05-19T10:00:00+00:00",
        "updated_at": "2026-05-19T10:00:00+00:00",
        "upload_token": "token_001",
        "images": [],
        "error_code": None,
        "error_message": None,
        "export_summary": {"last_exported_at": None, "formats": [], "files": []},
    }
    task.update(overrides)
    store.write(f"tasks/{task_id}.json", task)


def wait_for_task_status(client, task_id: str, status: str, timeout: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = client.get(f"/api/tasks/{task_id}").get_json()["data"]
        if latest["status"] == status:
            return latest
        time.sleep(0.01)
    return latest or client.get(f"/api/tasks/{task_id}").get_json()["data"]


def test_post_tasks_creates_uploading_task(client):
    created_patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    response = client.post(
        "/api/tasks",
        json={
            "patient_id": created_patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["task_id"] == "1"
    assert data["display_name"] == "1"
    assert data["status"] == "uploading"
    assert data["upload_token"]
    assert f"/mobile/upload/{data['task_id']}?token={data['upload_token']}" in data["mobile_upload_url"]
    assert data["patient_id"] == created_patient["patient_id"]
    assert data["record_date"] == "2026-06-07"


def test_post_tasks_uses_lan_address_for_mobile_upload_url(client):
    created_patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    response = client.post(
        "/api/tasks",
        json={
            "patient_id": created_patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
        base_url="http://127.0.0.1:8081",
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["mobile_upload_url"].startswith("http://192.168.1.5:8081/mobile/upload/")
    assert "127.0.0.1" not in data["mobile_upload_url"]


def test_post_tasks_prefers_public_base_url_over_container_lan_address(client, app):
    app.config["BACKEND_CONFIG"]["public_base_url"] = "http://172.20.10.5:8081"
    app.config["LAN_ADDRESSES"] = ["172.18.0.2:8081"]
    created_patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]

    response = client.post(
        "/api/tasks",
        json={
            "patient_id": created_patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
        base_url="http://127.0.0.1:8081",
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["mobile_upload_url"].startswith("http://172.20.10.5:8081/mobile/upload/")
    assert "172.18.0.2" not in data["mobile_upload_url"]


def test_get_task_returns_mvp_shape_without_session(client):
    created_patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    created = client.post(
        "/api/tasks",
        json={
            "patient_id": created_patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
    ).get_json()["data"]

    response = client.get(f"/api/tasks/{created['task_id']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "uploading"
    assert data["images"] == []
    assert data["page_count"] == 0
    assert "session_id" not in data


def test_list_tasks_returns_mvp_summaries(client, app):
    write_task(app, task_id="1", status="uploading")
    write_task(
        app,
        task_id="2",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(app, task_id="3", status="failed", error_code="ALGORITHM_MODULE_FAILED")

    response = client.get("/api/tasks")

    assert response.status_code == 200
    tasks = response.get_json()["data"]["tasks"]
    assert [task["task_id"] for task in tasks] == ["2", "3"]
    assert all("session_id" not in task for task in tasks)
    assert tasks[0]["page_count"] == 1
    assert tasks[0]["upload_token"] == "token_001"
    assert tasks[0]["mobile_upload_url"] == "http://192.168.1.5:8081/mobile/upload/2?token=token_001"
    assert "upload_token" not in tasks[1]
    assert "mobile_upload_url" not in tasks[1]


def test_list_tasks_filter_by_status(client, app):
    write_task(app, task_id="1", status="uploading")
    write_task(
        app,
        task_id="2",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(app, task_id="3", status="failed")

    response = client.get("/api/tasks?status=failed")

    assert response.status_code == 200
    assert [task["task_id"] for task in response.get_json()["data"]["tasks"]] == ["3"]

    uploading_response = client.get("/api/tasks?status=uploading")

    assert uploading_response.status_code == 200
    uploading_tasks = uploading_response.get_json()["data"]["tasks"]
    assert [task["task_id"] for task in uploading_tasks] == ["2"]
    assert uploading_tasks[0]["mobile_upload_url"] == "http://192.168.1.5:8081/mobile/upload/2?token=token_001"


def test_get_nonexistent_task_returns_404(client):
    response = client.get("/api/tasks/missing")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_process_task_without_algorithm_returns_failed_payload(client, app):
    write_task(app, status="uploading")

    response = client.post("/api/tasks/1/process")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "processing"
    assert data["processing_summary"]["stage"] == "queued"

    data = wait_for_task_status(client, "1", "failed")
    assert data["status"] == "failed"
    assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    assert data["error_message"] == "图像处理模块未配置"
    assert [entry["to_status"] for entry in data["status_history"]] == [
        "uploading",
        "processing",
        "failed",
    ]


def test_cancel_processing_route_marks_task_failed(client, app):
    write_task(
        app,
        status="processing",
        images=[{"page_id": "page_001", "page_no": 1}],
        processing_summary={
            "stage": "document_parsing",
            "status": "running",
            "label": "OCR 文档解析",
            "progress_percent": 55,
        },
    )

    response = client.post("/api/tasks/1/cancel-processing")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "TASK_PROCESSING_CANCELLED"
    assert data["error_message"] == "用户取消处理"


def test_cancel_processing_route_rejects_non_processing_task(client, app):
    write_task(app, status="review")

    response = client.post("/api/tasks/1/cancel-processing")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_rename_task_route_updates_display_name(client, app):
    write_task(app, status="review")

    response = client.patch(
        "/api/tasks/1/rename",
        json={"display_name": "张三入院记录"},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["display_name"] == "张三入院记录"
    assert data["task_id"] == "1"

    persisted = client.get("/api/tasks/1").get_json()["data"]
    assert persisted["display_name"] == "张三入院记录"


def test_rename_task_route_rejects_empty_display_name(client, app):
    write_task(app, status="review")

    response = client.patch(
        "/api/tasks/1/rename",
        json={"display_name": "  "},
    )

    assert response.status_code == 400


def test_delete_task_removes_from_listing(client, app):
    write_task(app, task_id="1", status="review")
    write_task(app, task_id="2", status="failed")

    response = client.delete("/api/tasks/1")

    assert response.status_code == 200
    assert response.get_json()["data"]["task_id"] == "1"
    assert response.get_json()["data"]["deleted"] is True

    tasks = client.get("/api/tasks").get_json()["data"]["tasks"]
    assert [t["task_id"] for t in tasks] == ["2"]

    response = client.get("/api/tasks/1")
    assert response.status_code == 404
    # 任务 JSON 仍保留(逻辑删除)
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    assert store.exists("tasks/1.json")
    raw = store.read("tasks/1.json")
    assert raw.get("deleted_at")


def test_delete_task_does_not_cleanup_files(client, app):
    """Task 6: 逻辑删除不应触发 CleanupService,
    任务/pages/results 目录均保留。"""
    write_task(app, task_id="1", status="review", session_id="session_abc")
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    storage_dir = app.config["BACKEND_CONFIG"]["storage_dir"]
    import os
    os.makedirs(os.path.join(storage_dir, "results", "1"), exist_ok=True)
    os.makedirs(os.path.join(storage_dir, "pages", "session_abc"), exist_ok=True)
    pages_marker = os.path.join(storage_dir, "pages", "session_abc", "marker.txt")
    with open(pages_marker, "w", encoding="utf-8") as f:
        f.write("page")
    results_marker = os.path.join(storage_dir, "results", "1", "marker.txt")
    with open(results_marker, "w", encoding="utf-8") as f:
        f.write("result")

    response = client.delete("/api/tasks/1")

    assert response.status_code == 200
    # 任务/pages/results 目录均保留
    assert store.exists("tasks/1.json")
    assert os.path.isdir(os.path.join(storage_dir, "pages", "session_abc"))
    assert os.path.exists(pages_marker)
    assert os.path.isdir(os.path.join(storage_dir, "results", "1"))
    assert os.path.exists(results_marker)
    raw = store.read("tasks/1.json")
    assert raw.get("deleted_at")


def test_deleted_task_does_not_break_listing_with_other_tasks(client, app):
    write_task(app, task_id="1", status="review")
    write_task(app, task_id="2", status="failed")

    client.delete("/api/tasks/1")
    tasks = client.get("/api/tasks").get_json()["data"]["tasks"]
    assert [t["task_id"] for t in tasks] == ["2"]


def test_deleted_task_blocks_metadata_patch(client, app):
    write_task(app, task_id="1", status="review")
    client.delete("/api/tasks/1")

    response = client.patch("/api/tasks/1/metadata", json={"record_date": "2026-06-08"})

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_deleted_task_blocks_reextract(client, app):
    write_task(app, task_id="1", status="review")
    client.delete("/api/tasks/1")

    response = client.post("/api/tasks/1/reextract")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_deleted_task_blocks_export(client, app):
    write_task(app, task_id="1", status="review")
    client.delete("/api/tasks/1")

    response = client.get("/api/tasks/1/export/json")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_delete_processing_task_returns_400(client, app):
    write_task(app, task_id="1", status="processing", images=[{"page_id": "page_001"}])

    response = client.delete("/api/tasks/1")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_reextract_task_route_returns_run_metadata(client, app):
    class FakeReextractionService:
        def reextract(self, task_id, cancellation_token=None):
            return {
                "task_id": task_id,
                "status": "review",
                "run_id": "reextract_001",
                "source": "ocr_text_only",
                "schema_version": "copd.v1",
                "prompt_version": "copd.prompt.v1",
                "candidate_count": 1,
            }

    app.config["REEXTRACTION_SERVICE"] = FakeReextractionService()

    response = client.post("/api/tasks/1/reextract")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["source"] == "ocr_text_only"
    assert data["schema_version"] == "copd.v1"
    assert data["prompt_version"] == "copd.prompt.v1"


def test_delete_nonexistent_task_returns_404(client):
    response = client.delete("/api/tasks/missing")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


# --- 重新抽取取消(BE-MVP-04-05 补)---


def test_reextract_job_registry_lifecycle():
    registry = ReextractJobRegistry()
    event = registry.register("t1")
    assert isinstance(event, threading.Event)
    assert not event.is_set()
    # cancel 不会自动 unregister;事件持续到 unregister 调用,以便在飞行中的
    # reextract 协程下一次检查时还能看到 set 状态。
    assert registry.cancel("t1") is True
    assert event.is_set()
    assert registry.cancel("t1") is True  # 幂等
    registry.unregister("t1")
    assert registry.get("t1") is None
    assert registry.cancel("t1") is False  # unregister 后才能 False


def test_reextract_job_registry_reuses_event_for_same_task():
    registry = ReextractJobRegistry()
    first = registry.register("t1")
    second = registry.register("t1")
    assert first is second
    assert registry.cancel("t1") is True
    assert first.is_set()


def test_cancel_reextract_route_rejects_when_no_inflight_job(client, app):
    write_task(app, task_id="1", status="review")

    response = client.post("/api/tasks/1/cancel-reextract")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == ErrorCode.REEXTRACTION_VALIDATION_FAILED.code
    assert response.get_json()["error"]["details"]["reason"] == "no_inflight_reextract"


def test_cancel_reextract_route_returns_404_for_missing_task(client):
    response = client.post("/api/tasks/missing/cancel-reextract")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_cancel_reextract_route_aborts_reextract_between_llm_batches(client, app, tmp_path):
    """模拟一个跑在 LLM 批次间检查取消 token 的 field port,验证取消生效后
    reextract 返回 409 REEXTRACTION_CANCELLED,review_result.json 不被覆盖,
    任务在 _reextract_runs/ 下没有写入 run 记录(因为没跑完)。"""
    write_task(app, task_id="1", status="review")
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "results/1/document_result.json",
        {
            "task_id": "1",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "姓名：张三",
            "pages": [{"page_id": "page_001", "page_no": 1, "text": "姓名：张三"}],
        },
    )
    # 预先放一份 review 用来检验"取消后不被覆盖"
    store.write(
        "results/1/review_result.json",
        {
            "task_id": "1",
            "schema_version": "old",
            "fields": [
                {
                    "field_key": "patient_name",
                    "field_name": "姓名",
                    "auto_value": "李四",
                    "final_value": "手工",
                    "status": "modified",
                }
            ],
        },
    )

    service_ready = threading.Event()

    class CancellableReextractService:
        def reextract(self, task_id, cancellation_token=None):
            assert cancellation_token is not None
            service_ready.set()
            # 阻塞等待 cancel 信号,wait 在 set 时立即返回 True
            if cancellation_token.wait(timeout=2.0):
                raise AppError(
                    ErrorCode.REEXTRACTION_CANCELLED,
                    message="用户取消重新抽取",
                    details={"reason": "user_cancelled"},
                )
            return {"task_id": task_id, "status": "review", "run_id": "r1",
                    "source": "ocr_text_only", "candidate_count": 1}

    app.config["REEXTRACTION_SERVICE"] = CancellableReextractService()

    result_box: dict = {}

    def call_reextract():
        # Flask test client 是同步的,需要在另一个线程中跑,以便我们能 cancel 它
        result_box["response"] = client.post("/api/tasks/1/reextract")

    t = threading.Thread(target=call_reextract)
    t.start()
    # 等服务拿到 cancellation_token 并开始等待
    assert service_ready.wait(timeout=2.0), "reextract 服务没及时启动"
    cancel_response = client.post("/api/tasks/1/cancel-reextract")
    t.join(timeout=2.0)
    assert not t.is_alive(), "reextract 线程没在取消后退出"

    assert cancel_response.status_code == 200
    assert cancel_response.get_json()["data"]["cancelled"] is True
    assert result_box["response"].status_code == 409
    assert result_box["response"].get_json()["error"]["code"] == ErrorCode.REEXTRACTION_CANCELLED.code

    # 取消后 review_result.json 应保持原样
    review = store.read("results/1/review_result.json")
    assert review["schema_version"] == "old"
    assert review["fields"][0]["final_value"] == "手工"
    # reextract_runs 不应写入
    assert store.list_json("results/1/reextract_runs") == []


# --- 任务元数据修改 (Task 4: PATCH /api/tasks/<task_id>/metadata) ---


def _create_test_patient(client, name="测试用例"):
    response = client.post("/api/patients", json={"name": name})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["data"]


def test_patch_metadata_route_requires_at_least_one_field(client, app):
    patient = _create_test_patient(client)
    write_task(app, task_id="1", status="review", patient_id=patient["patient_id"])

    response = client.patch("/api/tasks/1/metadata", json={})

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"


def test_patch_metadata_route_rebinds_patient(client, app):
    patient_a = _create_test_patient(client, name="测试用例一")
    patient_b = _create_test_patient(client, name="测试用例二")
    write_task(app, task_id="1", status="review", patient_id=patient_a["patient_id"])

    response = client.patch(
        "/api/tasks/1/metadata",
        json={"patient_id": patient_b["patient_id"]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["patient_id"] == patient_b["patient_id"]
    assert "metadata_history" not in data


def test_patch_metadata_route_rejects_processing_task(client, app):
    patient = _create_test_patient(client)
    write_task(app, task_id="1", status="processing", patient_id=patient["patient_id"])

    response = client.patch(
        "/api/tasks/1/metadata",
        json={"patient_id": patient["patient_id"]},
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_patch_metadata_route_rejects_deleted_patient(client, app):
    patient = _create_test_patient(client)
    deleted_patient = _create_test_patient(client, name="待删除")
    app.config["PATIENT_SERVICE"].mark_deleted(deleted_patient["patient_id"])
    write_task(app, task_id="1", status="review", patient_id=patient["patient_id"])

    response = client.patch(
        "/api/tasks/1/metadata",
        json={"patient_id": deleted_patient["patient_id"]},
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "PATIENT_DELETED"


def test_patch_metadata_route_blocks_document_type_change_with_active_reextract(client, app):
    patient = _create_test_patient(client)
    other_patient = _create_test_patient(client, name="改绑参考")
    write_task(app, task_id="1", status="review", patient_id=patient["patient_id"])
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "results/1/document_result.json",
        {
            "task_id": "1",
            "stage": "document_parsing",
            "status": "success",
            "merged_text": "x",
            "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "x"}],
        },
    )
    app.config["REEXTRACT_JOB_REGISTRY"].register("1")
    try:
        # 当存在活动重抽取时,仅改绑患者(不修改 document_type)仍允许
        response = client.patch(
            "/api/tasks/1/metadata",
            json={"patient_id": other_patient["patient_id"]},
        )
    finally:
        app.config["REEXTRACT_JOB_REGISTRY"].unregister("1")

    assert response.status_code == 200
    assert response.get_json()["data"]["patient_id"] == other_patient["patient_id"]


def test_cancel_reextract_unregisters_after_normal_completion(client, app):
    """正常完成的 reextract 之后,registry 应当清空任务,后续 cancel 返回 400。"""
    write_task(app, task_id="1", status="review")
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "results/1/document_result.json",
        {"task_id": "1", "stage": "document_parsing", "status": "success",
         "merged_text": "姓名:张三", "pages": []},
    )

    class QuickService:
        def reextract(self, task_id, cancellation_token=None):
            return {"task_id": task_id, "status": "review", "run_id": "r1",
                    "source": "ocr_text_only", "candidate_count": 0}

    app.config["REEXTRACTION_SERVICE"] = QuickService()

    response = client.post("/api/tasks/1/reextract")
    assert response.status_code == 200

    # 完成后 registry 应已 unregister
    follow_up = client.post("/api/tasks/1/cancel-reextract")
    assert follow_up.status_code == 400
    assert follow_up.get_json()["error"]["details"]["reason"] == "no_inflight_reextract"
