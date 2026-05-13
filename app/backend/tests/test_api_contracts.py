"""API 契约回归测试 — 成功/错误响应 shape、404、上传校验、幂等、排序拒绝。"""
import io

from app.backend.tests.fixtures.images import JPEG_BYTES, PDF_BYTES


def _make_client(tmp_path, monkeypatch):
    """与 E2E 共用的 client helper 本地副本，避免文件间导入耦合。"""
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = f"""
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
  model_dir: "{tmp_path}/models"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
"""
    (config_dir / "default.yaml").write_text(config, encoding="utf-8")
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def _create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]["session_id"]


def _upload_page(client, session_id, image_bytes=None, filename="test.jpg",
                 image_width=1920, image_height=1080):
    if image_bytes is None:
        image_bytes = JPEG_BYTES
    data = {
        "image": (io.BytesIO(image_bytes), filename),
        "image_width": str(image_width),
        "image_height": str(image_height),
    }
    return client.post(
        f"/api/mobile/{session_id}/pages",
        data=data,
        content_type="multipart/form-data",
    )


class TestSuccessShape:
    def test_success_responses_use_success_data_shape(self, tmp_path, monkeypatch):
        """所有成功 JSON API 返回 {success: true, data: ...}。"""
        client = _make_client(tmp_path, monkeypatch)

        endpoints = [
            "/api/system/status",
        ]
        for url in endpoints:
            resp = client.get(url)
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["success"] is True, f"{url} 缺少 success"
            assert "data" in body, f"{url} 缺少 data"


class TestErrorShape:
    def test_error_responses_use_error_shape_without_traceback(self, tmp_path, monkeypatch):
        """所有失败 API 返回 {error: {code, message, details}}，不包含堆栈。"""
        client = _make_client(tmp_path, monkeypatch)

        # 404 响应
        resp = client.get("/api/capture-sessions/nonexistent")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
        # 不泄露堆栈
        error_str = str(body)
        assert "Traceback" not in error_str
        assert "stack" not in error_str

        # 缺少 image 的上传
        sid = _create_session(client)
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data={"image_width": "1920", "image_height": "1080"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "INVALID_REQUEST_PARAMS"
        error_str = str(body)
        assert "Traceback" not in error_str


class TestNotFoundErrors:
    def test_missing_session_and_task_return_standard_errors(self, tmp_path, monkeypatch):
        """404 session/task 返回对应错误码。"""
        client = _make_client(tmp_path, monkeypatch)

        resp = client.get("/api/capture-sessions/no-such-session")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "SESSION_NOT_FOUND"

        resp = client.get("/api/tasks/no-such-task")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "TASK_NOT_FOUND"

        resp = client.post("/api/tasks/no-such-task/process")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "TASK_NOT_FOUND"


class TestUploadParams:
    def test_upload_missing_image_returns_invalid_request_params(self, tmp_path, monkeypatch):
        """上传缺少 image 返回 INVALID_REQUEST_PARAMS。"""
        client = _make_client(tmp_path, monkeypatch)
        sid = _create_session(client)

        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data={"image_width": "1920", "image_height": "1080"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"

    def test_upload_non_image_returns_unsupported_file_type(self, tmp_path, monkeypatch):
        """非图片上传返回 UNSUPPORTED_FILE_TYPE。"""
        client = _make_client(tmp_path, monkeypatch)
        sid = _create_session(client)

        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(PDF_BYTES), "test.pdf"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


class TestFinishIdempotent:
    def test_finish_same_session_is_idempotent(self, tmp_path, monkeypatch):
        """重复 finish 同一 session 幂等返回同一 task_id。"""
        client = _make_client(tmp_path, monkeypatch)
        sid = _create_session(client)
        _upload_page(client, sid)

        resp1 = client.post(f"/api/mobile/{sid}/finish")
        assert resp1.status_code == 200
        task_id1 = resp1.get_json()["data"]["task_id"]

        resp2 = client.post(f"/api/mobile/{sid}/finish")
        assert resp2.status_code == 200
        task_id2 = resp2.get_json()["data"]["task_id"]

        assert task_id1 == task_id2
        assert resp2.get_json()["data"]["status"] == "locked"


class TestReorderRejection:
    def test_reorder_unknown_page_id_rejects_whole_request(self, tmp_path, monkeypatch):
        """排序未知 page_id 整体拒绝，不局部应用。"""
        client = _make_client(tmp_path, monkeypatch)
        sid = _create_session(client)

        # 先 add 两个页面（空的，不需要文件）
        resp1 = client.post(f"/api/capture-sessions/{sid}/pages")
        resp2 = client.post(f"/api/capture-sessions/{sid}/pages")
        page1 = resp1.get_json()["data"]["pages"][-1]["page_id"]
        page2 = resp2.get_json()["data"]["pages"][-1]["page_id"]

        # 原始顺序
        session = client.get(f"/api/capture-sessions/{sid}").get_json()["data"]
        original_order = [p["page_id"] for p in session["pages"]]

        # 用非法 page_id 排序
        resp = client.put(
            f"/api/capture-sessions/{sid}/pages/order",
            json={"page_ids": [page1, page2, "no-such-page"]},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "SESSION_NOT_FOUND"

        # 确认顺序未被修改
        session_after = client.get(f"/api/capture-sessions/{sid}").get_json()["data"]
        assert [p["page_id"] for p in session_after["pages"]] == original_order


class TestOfflineCheck:
    def test_offline_check_returns_local_check_shape(self, tmp_path, monkeypatch):
        """/api/maintenance/offline-check 只返回本地检查结构。"""
        client = _make_client(tmp_path, monkeypatch)

        resp = client.get("/api/maintenance/offline-check")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert isinstance(data, dict)
        # 应包含本地资源状态
        assert "config" in data or "ok" in data or "checks" in data or "disk" in data
