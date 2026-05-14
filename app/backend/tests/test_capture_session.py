import os
import uuid
from datetime import datetime, timedelta, timezone

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
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
sessions:
  capture_session_ttl_minutes: 30
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]


def add_uploaded_page(client, session_id):
    service = client.application.config["SESSION_SERVICE"]
    session = service.add_page(session_id)
    page = session["pages"][-1]
    service.attach_page_upload(session_id, page["page_id"], f"pages/{session_id}/{page['page_id']}.json")


class TestCaptureSessionAPI:
    def test_create_session_returns_201_with_qr_url(self, client):
        data = create_session(client)

        assert data["status"] == "active"
        assert data["page_count"] == 0
        assert data["qr_code_url"].startswith("http://192.168.1.5:8081/mobile/sessions/")
        assert "created_at" in data
        assert "expires_at" in data

    def test_get_session_returns_current_status_and_pages(self, client):
        created = create_session(client)

        resp = client.get(f"/api/capture-sessions/{created['session_id']}")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["session_id"] == created["session_id"]
        assert data["status"] == "active"
        assert data["page_count"] == 0
        assert data["pages"] == []

    def test_get_nonexistent_session_returns_404(self, client):
        resp = client.get("/api/capture-sessions/missing")

        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "SESSION_NOT_FOUND"

    def test_add_page_before_finish_returns_201(self, client):
        created = create_session(client)

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["page_count"] == 1
        assert data["pages"][0]["page_no"] == 1

    def test_delete_page_before_finish_returns_200(self, client):
        created = create_session(client)
        added = client.post(f"/api/capture-sessions/{created['session_id']}/pages").get_json()["data"]
        page_id = added["pages"][0]["page_id"]

        resp = client.delete(f"/api/capture-sessions/{created['session_id']}/pages/{page_id}")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["page_count"] == 0

    def test_reorder_pages_before_finish_returns_200(self, client):
        created = create_session(client)
        client.post(f"/api/capture-sessions/{created['session_id']}/pages")
        current = client.post(f"/api/capture-sessions/{created['session_id']}/pages").get_json()["data"]
        order = [current["pages"][1]["page_id"], current["pages"][0]["page_id"]]

        resp = client.put(
            f"/api/capture-sessions/{created['session_id']}/pages/order",
            json={"page_ids": order},
        )

        assert resp.status_code == 200
        assert [p["page_id"] for p in resp.get_json()["data"]["pages"]] == order
        assert [p["page_no"] for p in resp.get_json()["data"]["pages"]] == [1, 2]

    def test_finish_locks_session_and_returns_task_id(self, client):
        created = create_session(client)
        add_uploaded_page(client, created["session_id"])

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "locked"
        assert data["task_id"] is not None
        assert data["locked_at"] is not None

    def test_finish_idempotent_returns_same_task_id(self, client):
        created = create_session(client)
        add_uploaded_page(client, created["session_id"])

        first = client.post(f"/api/mobile/{created['session_id']}/finish").get_json()["data"]
        second = client.post(f"/api/mobile/{created['session_id']}/finish").get_json()["data"]

        assert second["task_id"] == first["task_id"]

    def test_locked_session_rejects_page_writes(self, client):
        created = create_session(client)
        add_uploaded_page(client, created["session_id"])
        client.post(f"/api/mobile/{created['session_id']}/finish")

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_expired_session_rejects_page_writes(self, client):
        created = create_session(client)
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])
        session = store.read(f"sessions/{created['session_id']}.json")
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store.write(f"sessions/{created['session_id']}.json", session)

        resp = client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_EXPIRED"

    def test_finish_expired_session_returns_409(self, client):
        created = create_session(client)
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])
        session = store.read(f"sessions/{created['session_id']}.json")
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store.write(f"sessions/{created['session_id']}.json", session)

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_EXPIRED"

    def test_finish_empty_session_returns_400(self, client):
        created = create_session(client)

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "SESSION_EMPTY"

    def test_finish_placeholder_page_without_upload_ref_returns_400(self, client):
        created = create_session(client)
        client.post(f"/api/capture-sessions/{created['session_id']}/pages")

        resp = client.post(f"/api/mobile/{created['session_id']}/finish")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "SESSION_EMPTY"
