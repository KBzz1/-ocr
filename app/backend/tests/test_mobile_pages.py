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

    def test_update_quad_route_returns_stable_page_data(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/quad",
            json={
                "quad_points": [
                    {"x": 100, "y": 100},
                    {"x": 1800, "y": 100},
                    {"x": 1800, "y": 900},
                    {"x": 100, "y": 900},
                ]
            },
        )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["page_id"] == page_id
        assert data["page_no"] == 1
        assert data["quad_points"][0] == {"x": 100, "y": 100}
        assert data["quad_updated_at"] is not None

    def test_update_quad_route_rejects_locked_session(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]
        client.post(f"/api/mobile/{sid}/finish")

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/quad",
            json={"quad_points": [{"x": 0, "y": 0}]},
        )

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_replace_image_route_preserves_page_identity(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/image",
            data={
                "image": (io.BytesIO(_make_jpg()), "replacement.jpg"),
                "image_width": "1000",
                "image_height": "1400",
                "quad_points": json.dumps([
                    {"x": 50, "y": 60},
                    {"x": 950, "y": 60},
                    {"x": 950, "y": 1260},
                    {"x": 50, "y": 1260},
                ]),
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["page_id"] == page_id
        assert data["page_no"] == 1
        assert data["image_width"] == 1000
        assert data["image_height"] == 1400


class TestUploadFailureCompensation:
    """上传失败补偿：失败上传不应留下空 page。"""

    def test_failed_upload_non_image_does_not_leave_empty_page(self, client):
        """非图片上传失败后，session pages 中不存在空 page。"""
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

        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 0

    def test_failed_upload_oversized_file_does_not_leave_empty_page(self, client):
        """超大文件上传失败后，session pages 中不存在空 page。"""
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

        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 0

    def test_failed_upload_invalid_quad_does_not_leave_empty_page(self, client):
        """非法 quad 上传失败后，session pages 中不存在空 page。"""
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

        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 0

    def test_failed_upload_after_success_keeps_successful_page(self, client):
        """一个成功上传后再失败，成功页面仍保留且 finish 可固化。"""
        sid = _create_session(client)

        # 第一个页面成功上传
        data1 = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp1 = client.post(
            f"/api/mobile/{sid}/pages",
            data=data1,
            content_type="multipart/form-data",
        )
        assert resp1.status_code == 201

        # 第二个页面上传失败（非图片）
        data2 = {
            "image": (io.BytesIO(b'%PDF-1.4 fake pdf'), "doc.pdf"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp2 = client.post(
            f"/api/mobile/{sid}/pages",
            data=data2,
            content_type="multipart/form-data",
        )
        assert resp2.status_code == 400

        # session 中仍只有一个页面（成功的那一个）
        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 1
        assert pages[0]["upload_ref"] is not None

        # finish 能返回 200
        finish_resp = client.post(f"/api/mobile/{sid}/finish")
        assert finish_resp.status_code == 200

    def test_failed_upload_save_exception_does_not_leave_empty_page(self, client):
        """PageService.save 抛异常时 session pages 不新增空 page。"""
        sid = _create_session(client)

        # 先用正常上传确认 session 有 1 页
        data1 = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp1 = client.post(
            f"/api/mobile/{sid}/pages",
            data=data1,
            content_type="multipart/form-data",
        )
        assert resp1.status_code == 201

        # 模拟 PageService.save 抛异常
        from unittest.mock import patch
        from app.backend.errors import AppError, ErrorCode

        with patch.object(
            client.application.config["PAGE_SERVICE"],
            "save",
            side_effect=AppError(ErrorCode.INTERNAL_SERVER_ERROR),
        ):
            data2 = {
                "image": (io.BytesIO(_make_jpg()), "test2.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            }
            resp2 = client.post(
                f"/api/mobile/{sid}/pages",
                data=data2,
                content_type="multipart/form-data",
            )
            assert resp2.status_code == 500

        # session 中仍有 1 个页面（第一个成功的）
        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 1
        assert pages[0]["upload_ref"] is not None
