"""API 契约回归测试 — 成功/错误响应 shape、404、上传校验、幂等、排序拒绝。"""
import io
import socket

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client, upload_page
from app.backend.tests.fixtures.images import PDF_BYTES


def _create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]["session_id"]


class TestSuccessShape:
    def test_success_responses_use_success_data_shape(self, tmp_path, monkeypatch):
        """所有成功 JSON API 返回 {success: true, data: ...}。"""
        client, _app = make_client(tmp_path, monkeypatch)
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert "data" in body


class TestErrorShape:
    def test_error_responses_use_error_shape_without_traceback(self, tmp_path, monkeypatch):
        """所有失败 API 返回 {error: {code, message, details}}，不包含堆栈。"""
        client, _app = make_client(tmp_path, monkeypatch)

        resp = client.get("/api/capture-sessions/nonexistent")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
        error_str = str(body)
        assert "Traceback" not in error_str
        assert "stack" not in error_str

        sid = _create_session(client)
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data={"image_width": "1920", "image_height": "1080"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code
        assert "Traceback" not in str(resp.get_json())


class TestNotFoundErrors:
    def test_missing_session_and_task_return_standard_errors(self, tmp_path, monkeypatch):
        """404 session/task 返回对应错误码。"""
        client, _app = make_client(tmp_path, monkeypatch)

        resp = client.get("/api/capture-sessions/no-such-session")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == ErrorCode.SESSION_NOT_FOUND.code

        resp = client.get("/api/tasks/no-such-task")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == ErrorCode.TASK_NOT_FOUND.code

        resp = client.post("/api/tasks/no-such-task/process")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == ErrorCode.TASK_NOT_FOUND.code


class TestUploadParams:
    def test_upload_missing_image_returns_invalid_request_params(self, tmp_path, monkeypatch):
        """上传缺少 image 返回 INVALID_REQUEST_PARAMS。"""
        client, _app = make_client(tmp_path, monkeypatch)
        sid = _create_session(client)
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data={"image_width": "1920", "image_height": "1080"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == ErrorCode.INVALID_REQUEST_PARAMS.code

    def test_upload_non_image_returns_unsupported_file_type(self, tmp_path, monkeypatch):
        """非图片上传返回 UNSUPPORTED_FILE_TYPE。"""
        client, _app = make_client(tmp_path, monkeypatch)
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
        assert resp.get_json()["error"]["code"] == ErrorCode.UNSUPPORTED_FILE_TYPE.code


class TestFinishIdempotent:
    def test_finish_same_session_is_idempotent(self, tmp_path, monkeypatch):
        """重复 finish 同一 session 幂等返回同一 task_id。"""
        client, _app = make_client(tmp_path, monkeypatch)
        sid = _create_session(client)
        upload_page(client, sid)

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
        client, _app = make_client(tmp_path, monkeypatch)
        sid = _create_session(client)

        resp1 = client.post(f"/api/capture-sessions/{sid}/pages")
        resp2 = client.post(f"/api/capture-sessions/{sid}/pages")
        page1 = resp1.get_json()["data"]["pages"][-1]["page_id"]
        page2 = resp2.get_json()["data"]["pages"][-1]["page_id"]

        session = client.get(f"/api/capture-sessions/{sid}").get_json()["data"]
        original_order = [p["page_id"] for p in session["pages"]]

        resp = client.put(
            f"/api/capture-sessions/{sid}/pages/order",
            json={"page_ids": [page1, page2, "no-such-page"]},
        )
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == ErrorCode.SESSION_NOT_FOUND.code

        session_after = client.get(f"/api/capture-sessions/{sid}").get_json()["data"]
        assert [p["page_id"] for p in session_after["pages"]] == original_order


class TestOfflineCheck:
    def test_offline_check_returns_local_check_shape(self, tmp_path, monkeypatch):
        """/api/maintenance/offline-check 只返回本地检查结构。"""
        client, _app = make_client(tmp_path, monkeypatch)
        resp = client.get("/api/maintenance/offline-check")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert isinstance(data, dict)

    def test_offline_check_does_not_make_network_calls(self, tmp_path, monkeypatch):
        """离线检查不应发起网络访问。"""
        client, _app = make_client(tmp_path, monkeypatch)

        connect_calls = []
        real_connect = socket.socket.connect

        def _counting_connect(self_conn, target):
            connect_calls.append(target)
            return real_connect(self_conn, target)

        monkeypatch.setattr(socket.socket, "connect", _counting_connect)

        resp = client.get("/api/maintenance/offline-check")
        assert resp.status_code == 200
        assert len(connect_calls) == 0, f"offline-check 意外发起了网络连接: {connect_calls}"
