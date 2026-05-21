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


def write_task(app, task_id="task_001", status="uploading", **overrides):
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


def test_post_tasks_creates_uploading_task(client):
    response = client.post("/api/tasks")

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["task_id"].startswith("task_")
    assert data["status"] == "uploading"
    assert data["upload_token"]
    assert f"/mobile/upload/{data['task_id']}?token={data['upload_token']}" in data["mobile_upload_url"]


def test_post_tasks_uses_lan_address_for_mobile_upload_url(client):
    response = client.post("/api/tasks", base_url="http://127.0.0.1:8081")

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["mobile_upload_url"].startswith("http://192.168.1.5:8081/mobile/upload/")
    assert "127.0.0.1" not in data["mobile_upload_url"]


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
    write_task(app, task_id="task_001", status="uploading")
    write_task(
        app,
        task_id="task_002",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(app, task_id="task_003", status="failed", error_code="ALGORITHM_MODULE_FAILED")

    response = client.get("/api/tasks")

    assert response.status_code == 200
    tasks = response.get_json()["data"]["tasks"]
    assert [task["task_id"] for task in tasks] == ["task_002", "task_003"]
    assert all("session_id" not in task for task in tasks)
    assert tasks[0]["page_count"] == 1
    assert tasks[0]["upload_token"] == "token_001"
    assert tasks[0]["mobile_upload_url"] == "http://192.168.1.5:8081/mobile/upload/task_002?token=token_001"
    assert "upload_token" not in tasks[1]
    assert "mobile_upload_url" not in tasks[1]


def test_list_tasks_filter_by_status(client, app):
    write_task(app, task_id="task_001", status="uploading")
    write_task(
        app,
        task_id="task_002",
        status="uploading",
        images=[{"page_id": "page_001", "page_no": 1}],
    )
    write_task(app, task_id="task_003", status="failed")

    response = client.get("/api/tasks?status=failed")

    assert response.status_code == 200
    assert [task["task_id"] for task in response.get_json()["data"]["tasks"]] == ["task_003"]

    uploading_response = client.get("/api/tasks?status=uploading")

    assert uploading_response.status_code == 200
    uploading_tasks = uploading_response.get_json()["data"]["tasks"]
    assert [task["task_id"] for task in uploading_tasks] == ["task_002"]
    assert uploading_tasks[0]["mobile_upload_url"] == "http://192.168.1.5:8081/mobile/upload/task_002?token=token_001"


def test_get_nonexistent_task_returns_404(client):
    response = client.get("/api/tasks/missing")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "TASK_NOT_FOUND"


def test_process_task_without_algorithm_returns_failed_payload(client, app):
    write_task(app, status="uploading")

    response = client.post("/api/tasks/task_001/process")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    assert data["error_message"] == "图像处理模块未配置"
    assert [entry["to_status"] for entry in data["status_history"]] == [
        "uploading",
        "processing",
        "failed",
    ]
