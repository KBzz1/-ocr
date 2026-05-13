import pytest

from app.backend import create_backend_app
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def seed_reviewable_task(app, status="ready_for_review"):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task-001.json",
        {
            "task_id": "task-001",
            "session_id": "session-001",
            "status": status,
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 1,
            "page_order": ["page-1"],
            "source": "capture_session",
            "schema_version": "medical_record.v1",
            "document_type": "medical_record",
        },
    )
    store.write(
        "results/task-001/field_candidates.json",
        {
            "task_id": "task-001",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "chief_complaint", "original_value": "头痛3天", "evidence": "第1页", "confidence": 0.95},
                {"field_key": "diagnosis", "original_value": "上感", "evidence": "第1页", "confidence": 0.8},
            ],
        },
    )


def field_from_response(resp, field_key):
    fields = resp.get_json()["data"]["review_result"]["fields"]
    return next(field for field in fields if field["field_key"] == field_key)


class TestReviewRoutes:
    def test_get_review_initializes_result(self, client, app):
        seed_reviewable_task(app)

        resp = client.get("/api/tasks/task-001/review")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["task_id"] == "task-001"
        assert data["status"] == "ready_for_review"
        assert data["review_result"]["summary"]["unreviewed_count"] == 2

    def test_patch_modify_field(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.patch(
            "/api/tasks/task-001/review/fields/chief_complaint",
            json={"action": "modify", "final_value": "修正值"},
        )

        assert resp.status_code == 200
        field = field_from_response(resp, "chief_complaint")
        assert field["status"] == "modified"
        assert field["final_value"] == "修正值"

    def test_patch_confirm_field_without_final_value(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.patch("/api/tasks/task-001/review/fields/chief_complaint", json={"action": "confirm"})

        assert resp.status_code == 200
        assert field_from_response(resp, "chief_complaint")["status"] == "confirmed"

    def test_confirm_incomplete_review_returns_review_validation_failed(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.post("/api/tasks/task-001/review/confirm")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "REVIEW_VALIDATION_FAILED"
        assert resp.get_json()["error"]["details"]["unreviewed"] == ["chief_complaint", "diagnosis"]

    def test_confirm_complete_review_updates_task(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")
        client.patch("/api/tasks/task-001/review/fields/chief_complaint", json={"action": "confirm"})
        client.patch("/api/tasks/task-001/review/fields/diagnosis", json={"action": "confirm"})

        resp = client.post("/api/tasks/task-001/review/confirm")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "confirmed"
        assert resp.get_json()["data"]["review_summary"]["unreviewed_count"] == 0

    def test_failed_task_cannot_enter_review_flow(self, client, app):
        seed_reviewable_task(app, status="failed")

        resp = client.get("/api/tasks/task-001/review")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"

    def test_exported_task_can_reopen_review_result(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")
        store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
        task = store.read("tasks/task-001.json")
        task["status"] = "exported"
        store.write("tasks/task-001.json", task)

        resp = client.get("/api/tasks/task-001/review")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "exported"
        assert resp.get_json()["data"]["review_result"]["task_id"] == "task-001"
