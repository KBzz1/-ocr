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
algorithms:
  enable_copd_extractor: true
  qwen_vllm_server_url: "http://qwen-vision-vllm-server:8000/v1"
  qwen_vllm_model_name: "Qwen3.5-4B-AWQ-4bit"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client()


def _create_task(client):
    patient = client.post("/api/patients", json={"name": "测试用例"}).get_json()["data"]
    return client.post(
        "/api/tasks",
        json={
            "patient_id": patient["patient_id"],
            "document_type": "copd_admission_record",
            "record_date": "2026-06-07",
        },
    ).get_json()["data"]


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


def test_delete_uploaded_image_removes_page_and_renumbers(client):
    task = _create_task(client)
    first = _upload(client, task, "first.png").get_json()["data"]
    _upload(client, task, "second.png")

    response = client.delete(
        f"/api/mobile-upload/{task['task_id']}/images/{first['page_id']}?token={task['upload_token']}"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["page_count"] == 1
    assert [image["page_no"] for image in data["images"]] == [1]
    assert [image["page_id"] for image in data["images"]] == ["page_002"]


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


def test_mobile_upload_status_omits_document_type_options(client):
    task = _create_task(client)

    response = client.get(f"/api/mobile-upload/{task['task_id']}?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["document_type"] == "copd_admission_record"
    assert data["document_type_label"] == "入院记录"
    assert "available_document_types" not in data


def test_mobile_upload_status_omits_internal_server_paths(client):
    """手机端 API 响应不得包含 original_image_path 等服务端本机路径。"""
    task = _create_task(client)
    upload_resp = _upload(client, task, "page.png")
    assert upload_resp.status_code == 201

    response = client.get(f"/api/mobile-upload/{task['task_id']}?token={task['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    for image in data["images"]:
        assert "original_image_path" not in image, (
            f"image 不应泄露服务端本机路径字段 original_image_path: {image}"
        )
        assert isinstance(image.get("page_id"), str)
        assert isinstance(image.get("page_no"), int)
        # preview_url 必须存在且是相对路径
        preview = image.get("preview_url")
        assert isinstance(preview, str) and preview.startswith("/"), (
            f"preview_url 应为相对路径,实际: {preview!r}"
        )


def test_delete_uploaded_image_response_omits_internal_server_paths(client):
    """DELETE 图片后返回的 images 也不应泄露 original_image_path。"""
    task = _create_task(client)
    first = _upload(client, task, "first.png").get_json()["data"]

    response = client.delete(
        f"/api/mobile-upload/{task['task_id']}/images/{first['page_id']}?token={task['upload_token']}"
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    for image in data["images"]:
        assert "original_image_path" not in image, (
            f"DELETE 响应 image 不应泄露 original_image_path: {image}"
        )


def test_mobile_upload_document_type_route_is_removed(client):
    task = _create_task(client)

    response = client.patch(
        f"/api/mobile-upload/{task['task_id']}/document-type?token={task['upload_token']}",
        json={"document_type": "copd_admission_record"},
    )

    assert response.status_code == 404
