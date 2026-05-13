"""后端 E2E 契约测试 — 覆盖采集、处理、审核主流程。"""
import json
import os

from app.backend.errors import ErrorCode
from app.backend.services.algorithm_ports.fixtures import (
    FixtureDocPort,
    FixtureFieldPort,
    FixtureImagePort,
)
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore
from app.backend.tests.fixtures.client import make_client, setup_session_with_pages, upload_page


def _install_fixture_task_service(app, field_port=None, image_port=None, doc_port=None):
    """替换 TASK_SERVICE 和 REVIEW_SERVICE 使用 fixture 算法端口。"""
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])

    orchestrator = ProcessingOrchestrator(
        store=store,
        session_service=app.config["SESSION_SERVICE"],
        image_port=image_port or FixtureImagePort(),
        doc_port=doc_port or FixtureDocPort(),
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


class TestFixtureClient:
    def test_fixture_client_starts_with_system_status(self, tmp_path, monkeypatch):
        client, _app = make_client(tmp_path, monkeypatch)
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"


class TestSuccessFlow:
    def test_capture_process_review_confirm_success_flow(self, tmp_path, monkeypatch):
        """成功主流程：多页上传 → finish → process → review → modify → confirm。"""
        client, app = make_client(tmp_path, monkeypatch)

        resp = client.post("/api/capture-sessions")
        assert resp.status_code == 201
        session_data = resp.get_json()["data"]
        session_id = session_data["session_id"]
        assert session_data["status"] == "active"

        upload_page(client, session_id)
        upload_page(client, session_id)

        resp = client.post(f"/api/mobile/{session_id}/finish")
        assert resp.status_code == 200
        finish_data = resp.get_json()["data"]
        assert finish_data["status"] == "locked"
        task_id = finish_data["task_id"]

        resp = client.get(f"/api/capture-sessions/{session_id}")
        assert resp.get_json()["data"]["status"] == "locked"

        _install_fixture_task_service(app)

        resp = client.post(f"/api/tasks/{task_id}/process")
        assert resp.status_code == 200
        task = resp.get_json()["data"]
        assert task["status"] == "ready_for_review"

        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "ready_for_review"

        resp = client.get(f"/api/tasks/{task_id}/review")
        assert resp.status_code == 200
        review_data = resp.get_json()["data"]
        assert review_data["task_id"] == task_id
        fields = review_data["review_result"]["fields"]
        assert len(fields) >= 1
        chief = next(f for f in fields if f["field_key"] == "chief_complaint")
        assert chief["auto_value"] == "头痛3天"
        assert chief["status"] == "unreviewed"

        resp = client.patch(
            f"/api/tasks/{task_id}/review/fields/chief_complaint",
            json={"action": "modify", "final_value": "头痛3天加重1天"},
        )
        assert resp.status_code == 200
        chief_updated = next(
            f for f in resp.get_json()["data"]["review_result"]["fields"]
            if f["field_key"] == "chief_complaint"
        )
        assert chief_updated["final_value"] == "头痛3天加重1天"
        assert chief_updated["status"] == "modified"
        assert chief_updated["auto_value"] == "头痛3天"

        for f in fields:
            client.patch(
                f"/api/tasks/{task_id}/review/fields/{f['field_key']}",
                json={"action": "confirm"},
            )
        resp = client.post(f"/api/tasks/{task_id}/review/confirm")
        assert resp.status_code == 200
        confirmed_task = resp.get_json()["data"]
        assert confirmed_task["status"] == "confirmed"
        assert confirmed_task["confirmed_at"] is not None


class TestFailureFlow:
    def test_process_without_algorithm_marks_failed_and_review_is_rejected(
        self, tmp_path, monkeypatch
    ):
        """默认 app（无算法端口）处理任务应进入 failed，review 入口应被拒绝。"""
        client, app = make_client(tmp_path, monkeypatch)
        _session_id, task_id = setup_session_with_pages(client)

        resp = client.post(f"/api/tasks/{task_id}/process")
        assert resp.status_code == 200
        task = resp.get_json()["data"]
        assert task["status"] == "failed"
        assert task["error_code"] == ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code
        assert task["error_message"] is not None
        assert task["failed_at"] is not None

        resp = client.get(f"/api/tasks/{task_id}")
        assert resp.get_json()["data"]["status"] == "failed"

        resp = client.get(f"/api/tasks/{task_id}/review")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code

    def test_process_empty_field_candidates_marks_failed(self, tmp_path, monkeypatch):
        """空字段候选应导致 ALGORITHM_CONTRACT_INVALID 且不能进入审核。"""
        client, app = make_client(tmp_path, monkeypatch)
        _session_id, task_id = setup_session_with_pages(client)

        _install_fixture_task_service(
            app,
            field_port=FixtureFieldPort(return_empty=True),
        )

        resp = client.post(f"/api/tasks/{task_id}/process")
        assert resp.status_code == 200
        task = resp.get_json()["data"]
        assert task["status"] == "failed"
        assert task["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
        assert task["error_message"] is not None
        assert task["failed_at"] is not None

        resp = client.get(f"/api/tasks/{task_id}/review")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code

    def test_process_bad_field_candidate_contract_marks_failed(
        self, tmp_path, monkeypatch
    ):
        """非法字段结构应导致 ALGORITHM_CONTRACT_INVALID 且不能进入审核。"""
        client, app = make_client(tmp_path, monkeypatch)
        _session_id, task_id = setup_session_with_pages(client)

        _install_fixture_task_service(
            app,
            field_port=FixtureFieldPort(return_bad_structure=True),
        )

        resp = client.post(f"/api/tasks/{task_id}/process")
        assert resp.status_code == 200
        task = resp.get_json()["data"]
        assert task["status"] == "failed"
        assert task["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
        assert task["error_message"] is not None
        assert task["failed_at"] is not None

        resp = client.get(f"/api/tasks/{task_id}/review")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code


class TestLoggingPrivacy:
    def test_e2e_produces_expected_events_no_sensitive_leak(
        self, tmp_path, monkeypatch
    ):
        """成功主流程应产生已实现事件，日志不泄露图片/OCR/base64/身份证号。"""
        client, app = make_client(tmp_path, monkeypatch)
        _session_id, task_id = setup_session_with_pages(client, page_count=2)
        _install_fixture_task_service(app)
        client.post(f"/api/tasks/{task_id}/process")

        log_path = os.path.join(
            app.config["BACKEND_CONFIG"]["log_dir"], "backend-events.jsonl"
        )
        assert os.path.isfile(log_path), f"日志文件不存在: {log_path}"

        lines = []
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(json.loads(line))

        events = [r["event"] for r in lines]
        for expected in ("system_started", "session_created", "page_uploaded",
                         "session_finished", "task_processing_started"):
            assert expected in events, f"缺少事件: {expected}"
        assert "task_ready_for_review" in events

        log_text = json.dumps(lines, ensure_ascii=False)
        assert "ffd8" not in log_text.lower()
        assert "\\xff\\xd8" not in log_text
        assert "110101" not in log_text
        assert "merged text" not in log_text
