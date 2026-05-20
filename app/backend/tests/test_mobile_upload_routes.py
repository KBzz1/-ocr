from io import BytesIO

import pytest

from app.backend import create_backend_app
from app.backend.tests.fixtures.images import PNG_BYTES


@pytest.fixture
def client(tmp_path, monkeypatch):
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
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def _create_task(client):
    return client.post("/api/tasks").get_json()["data"]


def _upload(client, task, image_name="page.png"):
    return client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token={task['upload_token']}",
        data={
            "image": (BytesIO(PNG_BYTES), image_name),
            "image_width": "120",
            "image_height": "80",
        },
        content_type="multipart/form-data",
    )


def test_upload_image_adds_page_to_task_in_upload_order(client):
    task = _create_task(client)

    first = _upload(client, task, "first.png")
    second = _upload(client, task, "second.png")

    assert first.status_code == 201
    assert second.status_code == 201
    first_data = first.get_json()["data"]
    second_data = second.get_json()["data"]
    assert first_data["page_no"] == 1
    assert second_data["page_no"] == 2
    assert "quad_points" not in first_data
    detail = client.get(f"/api/tasks/{task['task_id']}").get_json()["data"]
    assert [image["page_no"] for image in detail["images"]] == [1, 2]


def test_mobile_upload_status_returns_existing_images(client):
    task = _create_task(client)
    _upload(client, task, "first.png")

    response = client.get(f"/api/mobile-upload/{task['task_id']}?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["task_id"] == task["task_id"]
    assert data["status"] == "uploading"
    assert data["page_count"] == 1
    assert [image["page_no"] for image in data["images"]] == [1]


def test_upload_rejects_invalid_token(client):
    task = _create_task(client)

    response = client.post(
        f"/api/mobile-upload/{task['task_id']}/images?token=wrong",
        data={
            "image": (BytesIO(PNG_BYTES), "page.png"),
            "image_width": "120",
            "image_height": "80",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"


def test_finish_empty_task_returns_task_empty(client):
    task = _create_task(client)

    response = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "TASK_EMPTY"


def test_finish_with_images_moves_to_processing_or_failed(client):
    task = _create_task(client)
    _upload(client, task)

    response = client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] in {"processing", "failed"}
    if data["status"] == "failed":
        assert data["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"


def test_upload_rejects_closed_task(client):
    task = _create_task(client)
    _upload(client, task)
    client.post(f"/api/mobile-upload/{task['task_id']}/finish?token={task['upload_token']}")

    response = _upload(client, task, "late.png")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "TASK_UPLOAD_CLOSED"
