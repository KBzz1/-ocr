import io
import json
import os
import pytest
from app.backend.__init__ import create_backend_app
from app.backend.storage.json_store import JsonStore


def _make_jpg():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


@pytest.fixture
def client(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "0.1.0"
server:
  bind_host: "0.0.0.0"
  port: 8081
paths:
  data_dir: "{tmp_path}/data"
  log_dir: "{tmp_path}/logs"
  export_dir: "{tmp_path}/exports"
  model_dir: "{tmp_path}/models"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def _create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]["session_id"]


class TestMobilePages:
    def test_upload_page_returns_201(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["page_id"]
        assert body["data"]["page_no"] == 1

    def test_upload_without_quad_points_returns_201(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["quad_points"] is None

    def test_upload_rejects_non_image_file(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(b'%PDF-1.4 fake pdf'), "doc.pdf"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_upload_rejects_oversized_file(self, client):
        sid = _create_session(client)
        big = b'\xff\xd8\xff\xe0' + b'\x00' * (11 * 1024 * 1024)
        data = {
            "image": (io.BytesIO(big), "big.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_upload_rejects_invalid_quad_points(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
            "quad_points": "not json",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_QUAD_POINTS"

    def test_upload_missing_image_returns_400(self, client):
        sid = _create_session(client)
        data = {"image_width": "1920", "image_height": "1080"}
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"

    def test_upload_missing_dimensions_returns_400(self, client):
        sid = _create_session(client)
        data = {"image": (io.BytesIO(_make_jpg()), "test.jpg")}
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"

    def test_upload_nonexistent_session_returns_404(self, client):
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            "/api/mobile/nonexistent/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 404

    def test_upload_session_page_has_upload_ref(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201

        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 1
        assert pages[0]["upload_ref"] is not None

    def test_upload_locked_session_returns_409(self, client):
        sid = _create_session(client)
        # First upload a page so finish doesn't fail with SESSION_EMPTY
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        upload_resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert upload_resp.status_code == 201
        client.post(f"/api/mobile/{sid}/finish")

        # Now try to upload another page to the locked session
        new_data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=new_data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_upload_expired_session_returns_409(self, client):
        sid = _create_session(client)
        config = client.application.config["BACKEND_CONFIG"]
        store = JsonStore(config["storage_dir"])
        session = store.read(f"sessions/{sid}.json")
        from datetime import datetime, timedelta, timezone
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        store.write(f"sessions/{sid}.json", session)

        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 409
