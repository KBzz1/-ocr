import pytest

from app.backend.services.algorithm_ports.fixtures import (
    FixtureDocPort,
    FixtureFieldPort,
    FixtureImagePort,
)
from app.backend.storage.json_store import JsonStore


def _setup_task_and_session(store, task_id="task-001", session_id="session-001",
                              page_order=None, page_data=None):
    if page_order is None:
        page_order = ["page-1"]
    if page_data is None:
        page_data = {"page-1": {"original_image_path": "/tmp/p1.jpg", "quad_points": None,
                                 "image_width": 1920, "image_height": 1080}}

    for pid, meta in page_data.items():
        store.write(f"pages/{session_id}/{pid}.json", {
            "page_id": pid, "session_id": session_id, "page_no": 1,
            "original_image_path": meta["original_image_path"],
            "processed_image_path": None,
            "image_width": meta["image_width"], "image_height": meta["image_height"],
            "quad_points": meta.get("quad_points"), "uploaded_at": "2026-05-12T10:00:00+00:00",
        })

    pages = [{"page_id": pid, "page_no": i + 1,
              "upload_ref": f"pages/{session_id}/{pid}.json",
              "created_at": "2026-05-12T10:00:00+00:00"}
             for i, pid in enumerate(page_order)]
    store.write(f"sessions/{session_id}.json", {
        "session_id": session_id, "status": "locked",
        "created_at": "2026-05-12T10:00:00+00:00",
        "expires_at": "2026-05-12T10:30:00+00:00",
        "qr_code_url": None, "page_count": len(page_order),
        "pages": pages, "locked_at": "2026-05-12T10:05:00+00:00", "task_id": task_id,
    })

    store.write(f"tasks/{task_id}.json", {
        "task_id": task_id, "session_id": session_id,
        "status": "processing", "created_at": "2026-05-12T10:05:00+00:00",
        "page_count": len(page_order), "page_order": page_order,
        "source": "capture_session",
        "error_code": None, "error_message": None, "failed_at": None,
        "processing_at": "2026-05-12T10:05:00+00:00", "ready_at": None,
        "status_history": [{"from_status": None, "to_status": "uploaded",
                            "changed_at": "2026-05-12T10:00:00+00:00", "reason": "采集会话完成采集"}],
    })


def _make_orchestrator(tmp_path, image_port=None, doc_port=None, field_port=None, schema_validator=None):
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from app.backend.services.session_service import SessionService
    from app.backend.services.task_service import TaskService

    store = JsonStore(str(tmp_path))
    session_service = SessionService(store=store, lan_addresses=[], ttl_minutes=30)
    orchestrator = ProcessingOrchestrator(
        store=store, session_service=session_service,
        image_port=image_port, doc_port=doc_port,
        field_port=field_port, schema_validator=schema_validator,
    )
    service = TaskService(store=store, orchestrator=orchestrator)
    return store, service


class TestOrchestratorFailures:
    def test_no_ports_configured_marks_failed(self, tmp_path):
        store, service = _make_orchestrator(tmp_path)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
        assert result["details"]["stage"] == "image_processing"
        assert result["details"]["reason"] == "module_not_configured"

    def test_image_exception_skips_later_ports(self, tmp_path):
        img = FixtureImagePort(should_fail=True)
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["stage"] == "image_processing"
        assert result["details"]["reason"] == "module_exception"
        assert doc.calls == []
        assert field.calls == []

    def test_image_bad_processed_path_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort(return_bad_path=True)
        store, service = _make_orchestrator(tmp_path, image_port=img)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "image_processing"
        assert result["details"]["reason"] == "invalid_processed_path"

    def test_missing_page_metadata_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        store, service = _make_orchestrator(tmp_path, image_port=img)
        _setup_task_and_session(store, page_data={})
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "image_processing"
        assert result["details"]["reason"] == "page_metadata_missing"

    def test_absolute_upload_ref_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        store, service = _make_orchestrator(tmp_path, image_port=img)
        _setup_task_and_session(store)
        session = store.read("sessions/session-001.json")
        session["pages"][0]["upload_ref"] = str(tmp_path / "pages" / "session-001" / "page-1.json")
        store.write("sessions/session-001.json", session)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["reason"] == "page_metadata_missing"

    def test_document_empty_pages_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(return_empty=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "document_parsing"
        assert result["details"]["reason"] == "empty_pages"

    def test_document_non_dict_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(return_non_dict=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["reason"] == "invalid_document_result"

    def test_document_missing_pages_key_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(return_missing_pages=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["reason"] == "invalid_document_result"

    def test_document_exception_marks_module_failed(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(should_fail=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["stage"] == "document_parsing"

    def test_document_partial_page_failure_marks_failed_and_persists(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort(partial_fail_page_id="page-1")
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc)
        _setup_task_and_session(store, page_order=["page-1", "page-2"], page_data={
            "page-1": {"original_image_path": "/tmp/p1.jpg", "quad_points": None, "image_width": 1920, "image_height": 1080},
            "page-2": {"original_image_path": "/tmp/p2.jpg", "quad_points": None, "image_width": 1920, "image_height": 1080},
        })
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["reason"] == "partial_page_failed"
        assert store.exists("results/task-001/document_result.json")

    def test_field_empty_candidates_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort(return_empty=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1"})

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "field_extraction"
        assert result["details"]["reason"] == "empty_candidates"

    def test_field_non_list_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort(return_non_list=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1"})

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["reason"] == "invalid_candidate_contract"

    def test_missing_schema_marks_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service)  # no schema

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "field_extraction"
        assert result["details"]["reason"] == "schema_missing_or_invalid"
        assert field.calls == []

    def test_schema_validator_failure_maps_contract_invalid(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        # validator that rejects candidates
        def reject_validator(candidates, schema):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="schema violation")
        from app.backend.errors import AppError, ErrorCode

        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field, schema_validator=reject_validator)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1"})

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["details"]["stage"] == "field_extraction"
        assert result["details"]["reason"] == "schema_validation_failed"

    def test_field_exception_marks_module_failed(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort(should_fail=True)
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1"})

        assert result["status"] == "failed"
        assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
        assert result["details"]["stage"] == "field_extraction"
        assert result["details"]["reason"] == "module_exception"


class TestOrchestratorSuccess:
    def test_all_ports_configured_flow_to_ready(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1", "document_type": "medical_record"})

        assert result["status"] == "ready_for_review"
        assert result["ready_at"] is not None
        assert store.exists("results/task-001/image_result.json")
        assert store.exists("results/task-001/document_result.json")
        assert store.exists("results/task-001/field_candidates.json")

    def test_multi_page_calls_image_port_per_page(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store, page_order=["page-1", "page-2"], page_data={
            "page-1": {"original_image_path": "/tmp/p1.jpg", "quad_points": None, "image_width": 1920, "image_height": 1080},
            "page-2": {"original_image_path": "/tmp/p2.jpg", "quad_points": [[0,0],[1920,0],[1920,1080],[0,1080]], "image_width": 1920, "image_height": 1080},
        })
        task = store.read("tasks/task-001.json")

        service._orchestrator.run(task, service, schema={"version": "v1"})

        assert len(img.calls) == 2
        assert img.calls[0]["page_id"] == "page-1"
        assert img.calls[1]["page_id"] == "page-2"
        assert img.calls[1]["quad_points"] is not None

    def test_quad_points_null_is_accepted(self, tmp_path):
        img = FixtureImagePort()
        doc = FixtureDocPort()
        field = FixtureFieldPort()
        store, service = _make_orchestrator(tmp_path, image_port=img, doc_port=doc, field_port=field)
        _setup_task_and_session(store)
        task = store.read("tasks/task-001.json")

        result = service._orchestrator.run(task, service, schema={"version": "v1"})

        assert result["status"] == "ready_for_review"
        assert img.calls[0]["quad_points"] is None
