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


def write_task(app, task_id="task-001", status="uploaded", **overrides):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task = {
        "task_id": task_id, "session_id": "session-001",
        "status": status, "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2, "page_order": ["page-1", "page-2"],
        "source": "capture_session",
    }
    task.update(overrides)
    store.write(f"tasks/{task_id}.json", task)


class TestTaskRoutes:
    def test_list_tasks_returns_200(self, client, app):
        write_task(app, task_id="task-001", status="uploaded")
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["tasks"][0]["task_id"] == "task-001"

    def test_list_tasks_filter_by_status(self, client, app):
        write_task(app, task_id="task-001", status="uploaded")
        write_task(app, task_id="task-002", status="failed")
        resp = client.get("/api/tasks?status=failed")
        assert resp.status_code == 200
        assert [t["task_id"] for t in resp.get_json()["data"]["tasks"]] == ["task-002"]

    def test_get_task_returns_200(self, client, app):
        write_task(app)
        resp = client.get("/api/tasks/task-001")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["task_id"] == "task-001"
        assert data["page_summary"]["page_order"] == ["page-1", "page-2"]
        assert data["document_summary"] is None
        assert data["review_summary"]["status"] is None
        assert data["export_summary"]["formats"] == []

    def test_get_nonexistent_task_returns_404(self, client):
        resp = client.get("/api/tasks/missing")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "TASK_NOT_FOUND"

    def test_process_task_without_algorithm_returns_failed_payload(self, client, app):
        write_task(app, status="uploaded")
        resp = client.post("/api/tasks/task-001/process")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert data["error_message"] == "图像处理模块未配置"
        assert [e["to_status"] for e in data["status_history"]] == ["uploaded", "processing", "failed"]

    def test_process_task_invalid_state_returns_400(self, client, app):
        write_task(app, status="confirmed")
        resp = client.post("/api/tasks/task-001/process")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"

    def test_retry_task_without_algorithm_returns_failed_payload(self, client, app):
        write_task(app, status="failed", error_code="OLD", error_message="旧错误",
                   failed_at="2026-05-12T10:01:00+00:00")
        resp = client.post("/api/tasks/task-001/retry")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "failed"
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert data["error_message"] == "图像处理模块未配置"

    def test_retry_task_invalid_state_returns_400(self, client, app):
        write_task(app, status="uploaded")
        resp = client.post("/api/tasks/task-001/retry")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
