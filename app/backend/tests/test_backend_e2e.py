"""后端 E2E 契约测试：MVP 任务上传、处理、审核、完成、导出。"""
import json
import os

from app.backend.errors import ErrorCode
from app.backend.services.algorithm_ports.fixtures import FixtureDocPort, FixtureFieldPort, FixtureImagePort
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore
from app.backend.tests.fixtures.client import make_client, setup_task_with_images, upload_task_image


def install_fixture_task_service(app, field_port=None):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=FixtureImagePort(),
        doc_port=FixtureDocPort(),
        field_port=field_port or FixtureFieldPort(),
        schema_validator=app.config["SCHEMA_SERVICE"].build_validator(),
    )
    task_service = TaskService(
        store=store,
        orchestrator=orchestrator,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    app.config["TASK_SERVICE"] = task_service
    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=task_service,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )


def test_fixture_client_starts_with_system_status(tmp_path, monkeypatch):
    client, _app = make_client(tmp_path, monkeypatch)

    response = client.get("/api/system/status")

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "running"


def test_mvp_success_flow_create_upload_process_review_done_export(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_fixture_task_service(app)
    created = client.post("/api/tasks").get_json()["data"]

    upload = upload_task_image(client, created)
    assert upload.status_code == 201

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "review"

    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    fields = review.get_json()["data"]["review_result"]["fields"]
    assert fields[0]["status"] == "unreviewed"

    saved = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": fields[0]["field_key"], "value": "头痛3天加重1天", "status": "modified"}]},
    )
    assert saved.status_code == 200

    completed = client.post(f"/api/tasks/{created['task_id']}/complete")
    assert completed.status_code == 200
    assert completed.get_json()["data"]["status"] == "done"

    exported = client.get(f"/api/tasks/{created['task_id']}/export/json")
    assert exported.status_code == 200
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
    install_fixture_task_service(app, field_port=FixtureFieldPort(return_empty=True))
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_e2e_logs_do_not_include_sensitive_payloads(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_fixture_task_service(app)
    created = setup_task_with_images(client, page_count=2)
    client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    log_path = os.path.join(app.config["BACKEND_CONFIG"]["log_dir"], "backend-events.jsonl")
    assert os.path.isfile(log_path)

    with open(log_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    events = [record["event"] for record in lines]
    assert "system_started" in events
    assert "task_processing_started" in events
    assert "task_ready_for_review" in events

    log_text = json.dumps(lines, ensure_ascii=False)
    assert "ffd8" not in log_text.lower()
    assert "\\xff\\xd8" not in log_text
    assert "110101" not in log_text
    assert "merged text" not in log_text
