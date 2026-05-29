import time

import pytest

from app.backend import create_backend_app
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
    response = client.post("/api/tasks")

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["task_id"] == "1"
    assert data["display_name"] == "1"
    assert data["status"] == "uploading"
    assert data["upload_token"]
    assert f"/mobile/upload/{data['task_id']}?token={data['upload_token']}" in data["mobile_upload_url"]


def test_post_tasks_uses_lan_address_for_mobile_upload_url(client):
    response = client.post("/api/tasks", base_url="http://127.0.0.1:8081")

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["mobile_upload_url"].startswith("http://192.168.1.5:8081/mobile/upload/")
    assert "127.0.0.1" not in data["mobile_upload_url"]


def test_post_tasks_prefers_public_base_url_over_container_lan_address(client, app):
    app.config["BACKEND_CONFIG"]["public_base_url"] = "http://172.20.10.5:8081"
    app.config["LAN_ADDRESSES"] = ["172.18.0.2:8081"]

    response = client.post("/api/tasks", base_url="http://127.0.0.1:8081")

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["mobile_upload_url"].startswith("http://172.20.10.5:8081/mobile/upload/")
    assert "172.18.0.2" not in data["mobile_upload_url"]


def test_get_task_returns_mvp_shape_without_session(client):
    created = client.post("/api/tasks").get_json()["data"]

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


def test_delete_task_with_cleanup(client, app):
    write_task(app, task_id="1", status="review", session_id="session_abc")
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    storage_dir = app.config["BACKEND_CONFIG"]["storage_dir"]
    import os
    os.makedirs(os.path.join(storage_dir, "results", "1"), exist_ok=True)
    os.makedirs(os.path.join(storage_dir, "pages", "session_abc"), exist_ok=True)

    response = client.delete("/api/tasks/1")

    assert response.status_code == 200
    assert not store.exists("tasks/1.json")


def test_delete_processing_task_returns_400(client, app):
    write_task(app, task_id="1", status="processing", images=[{"page_id": "page_001"}])

    response = client.delete("/api/tasks/1")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"


def test_reextract_task_route_returns_run_metadata(client, app):
    class FakeReextractionService:
        def reextract(self, task_id):
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
