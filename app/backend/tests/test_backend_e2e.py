"""后端 E2E 契约测试：MVP 任务上传、处理、审核、完成、导出。"""
import json
import os

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client, setup_task_with_images, upload_task_image
from app.backend.tests.fixtures.processing import install_simulated_processing


def test_backend_configures_copd_field_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_copd_extractor: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend._get_lan_addresses",
        lambda port: ["192.168.1.5:8081"],
    )
    monkeypatch.setattr(
        "app.backend.services.copd_extraction.port.build_default_copd_field_port",
        lambda config, field_keys_provider: object(),
    )

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._field_port is not None


def test_fixture_client_starts_with_system_status(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "running"


def test_mvp_success_flow_create_upload_process_review_done_export(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    created = client.post("/api/tasks").get_json()["data"]

    for index in range(3):
        upload = upload_task_image(client, created, filename=f"page-{index + 1}.jpg")
        assert upload.status_code == 201
        assert upload.get_json()["data"]["page_no"] == index + 1

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "review"

    task_after_finish = client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]
    assert task_after_finish["page_count"] == 3

    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    fields = review.get_json()["data"]["review_result"]["fields"]
    assert fields[0]["field_key"] == "chief_complaint"
    assert fields[0]["auto_value"] == "模拟外部算法返回的主诉"
    assert fields[0]["status"] == "unreviewed"

    saved = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": "chief_complaint", "value": "人工审核后的主诉", "status": "modified"}]},
    )
    assert saved.status_code == 200
    saved_field = saved.get_json()["data"]["review_result"]["fields"][0]
    assert saved_field["auto_value"] == "模拟外部算法返回的主诉"
    assert saved_field["final_value"] == "人工审核后的主诉"

    completed = client.post(f"/api/tasks/{created['task_id']}/complete")
    assert completed.status_code == 200
    assert completed.get_json()["data"]["status"] == "done"

    exported_json = client.get(f"/api/tasks/{created['task_id']}/export/json")
    assert exported_json.status_code == 200
    assert "人工审核后的主诉" in exported_json.get_data(as_text=True)

    exported_excel = client.get(f"/api/tasks/{created['task_id']}/export/excel")
    assert exported_excel.status_code == 200

    assert client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]["status"] == "done"


def test_mvp_algorithm_not_configured_goes_failed(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code


def test_mvp_empty_field_candidates_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="empty_fields")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 400
    assert review.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code


def test_mvp_simulated_algorithm_exception_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="module_failed")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_MODULE_FAILED.code
    assert data["failed_at"]


def test_mvp_invalid_field_contract_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="invalid_contract")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    assert data["failed_at"]


def test_e2e_logs_do_not_include_sensitive_payloads(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    created = setup_task_with_images(client, page_count=2)
    client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    log_path = os.path.join(app.config["BACKEND_CONFIG"]["log_dir"], "backend-events.jsonl")
    assert os.path.isfile(log_path)

    with open(log_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    events = [record["event"] for record in lines]
    assert "system_started" in events
    assert "task_processing_started" in events
    assert "task_review_ready" in events

    log_text = json.dumps(lines, ensure_ascii=False)
    assert "ffd8" not in log_text.lower()
    assert "\\xff\\xd8" not in log_text
    assert "110101" not in log_text
    assert "merged text" not in log_text
