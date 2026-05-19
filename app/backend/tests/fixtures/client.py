"""测试 client 和 task upload helpers。"""
import io

from app.backend import create_backend_app
from app.backend.tests.fixtures.images import JPEG_BYTES


def write_config(tmp_path):
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
    config_dir = write_config(tmp_path)
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client(), app


def upload_task_image(client, task, image_bytes=None, filename="test.jpg", image_width=1920, image_height=1080):
    if image_bytes is None:
        image_bytes = JPEG_BYTES
    return client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token={task['upload_token']}",
        data={
            "image": (io.BytesIO(image_bytes), filename),
            "image_width": str(image_width),
            "image_height": str(image_height),
        },
        content_type="multipart/form-data",
    )


def setup_task_with_images(client, page_count=1):
    created = client.post("/api/tasks").get_json()["data"]
    for index in range(page_count):
        response = upload_task_image(client, created, filename=f"page-{index + 1}.jpg")
        assert response.status_code == 201
    return created
