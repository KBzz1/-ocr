"""测试 client 和 session helpers — 减少跨文件重复。"""
import io

from app.backend import create_backend_app
from app.backend.tests.fixtures.images import JPEG_BYTES


def write_config(tmp_path):
    """写入测试用 YAML 配置，所有路径指向 tmp_path。"""
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
    return config_dir


def make_client(tmp_path, monkeypatch):
    """创建 Flask test client 和 app，所有路径隔离在 tmp_path 中。"""
    config_dir = write_config(tmp_path)
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client(), app


def upload_page(client, session_id, image_bytes=None, filename="test.jpg",
                image_width=1920, image_height=1080, quad_points=None):
    """上传一个图片页面，返回响应。"""
    if image_bytes is None:
        image_bytes = JPEG_BYTES
    data = {
        "image": (io.BytesIO(image_bytes), filename),
        "image_width": str(image_width),
        "image_height": str(image_height),
    }
    if quad_points is not None:
        data["quad_points"] = quad_points
    return client.post(
        f"/api/mobile/{session_id}/pages",
        data=data,
        content_type="multipart/form-data",
    )


def setup_session_with_pages(client, page_count=1):
    """创建会话、上传 page_count 页、finish，返回 (session_id, task_id)。"""
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    session_id = resp.get_json()["data"]["session_id"]

    for _ in range(page_count):
        resp = upload_page(client, session_id)
        assert resp.status_code == 201

    resp = client.post(f"/api/mobile/{session_id}/finish")
    assert resp.status_code == 200
    task_id = resp.get_json()["data"]["task_id"]
    return session_id, task_id
