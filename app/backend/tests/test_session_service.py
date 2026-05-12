import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.storage.json_store import JsonStore


def make_service(tmp_path, lan_addresses=None, ttl_minutes=30):
    from app.backend.services.session_service import SessionService

    return SessionService(
        store=JsonStore(str(tmp_path)),
        lan_addresses=lan_addresses if lan_addresses is not None else ["192.168.1.5:8081"],
        ttl_minutes=ttl_minutes,
    )


class TestSessionCreateGet:
    def test_create_returns_unique_session_id(self, tmp_path):
        service = make_service(tmp_path)
        first = service.create()
        second = service.create()

        assert first["session_id"]
        assert second["session_id"]
        assert first["session_id"] != second["session_id"]

    def test_create_sets_active_status_timestamps_and_empty_pages(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        assert session["status"] == "active"
        assert session["page_count"] == 0
        assert session["pages"] == []
        assert session["locked_at"] is None
        assert session["task_id"] is None

        created = datetime.fromisoformat(session["created_at"])
        expires = datetime.fromisoformat(session["expires_at"])
        assert timedelta(minutes=29) < expires - created < timedelta(minutes=31)

    def test_create_persists_session_json(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        path = tmp_path / "sessions" / f"{session['session_id']}.json"
        assert path.is_file()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["session_id"] == session["session_id"]
        assert data["status"] == "active"

    def test_create_qr_code_url_uses_first_lan_address(self, tmp_path):
        service = make_service(tmp_path, lan_addresses=["10.0.0.2:8081", "192.168.1.5:8081"])
        session = service.create()

        assert session["qr_code_url"] == f"http://10.0.0.2:8081/mobile/{session['session_id']}"

    def test_create_qr_code_url_is_none_without_lan_address(self, tmp_path):
        service = make_service(tmp_path, lan_addresses=[])
        session = service.create()

        assert session["qr_code_url"] is None

    def test_get_returns_session(self, tmp_path):
        service = make_service(tmp_path)
        created = service.create()

        fetched = service.get(created["session_id"])

        assert fetched["session_id"] == created["session_id"]
        assert fetched["status"] == "active"

    def test_get_nonexistent_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.get("missing")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_get_auto_expires_active_session_and_persists(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        fetched = service.get(session["session_id"])

        assert fetched["status"] == "expired"
        persisted = JsonStore(str(tmp_path)).read(f"sessions/{session['session_id']}.json")
        assert persisted["status"] == "expired"


class TestSessionPages:
    def test_add_page_appends_page_and_updates_page_count(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        updated = service.add_page(session["session_id"])

        assert updated["page_count"] == 1
        assert len(updated["pages"]) == 1
        assert updated["pages"][0]["page_no"] == 1
        assert updated["pages"][0]["upload_ref"] is None

    def test_add_page_assigns_incrementing_page_no(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        first = service.add_page(session["session_id"])
        second = service.add_page(session["session_id"])

        assert [p["page_no"] for p in second["pages"]] == [1, 2]
        assert first["pages"][0]["page_id"] != second["pages"][1]["page_id"]

    def test_delete_page_removes_page_and_renumbers(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])
        service.add_page(session["session_id"])
        current = service.add_page(session["session_id"])
        remove_id = current["pages"][1]["page_id"]

        updated = service.delete_page(session["session_id"], remove_id)

        assert updated["page_count"] == 2
        assert [p["page_no"] for p in updated["pages"]] == [1, 2]
        assert remove_id not in [p["page_id"] for p in updated["pages"]]

    def test_delete_missing_page_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        with pytest.raises(AppError) as exc_info:
            service.delete_page(session["session_id"], "missing-page")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_reorder_pages_persists_requested_order_and_renumbers(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])
        service.add_page(session["session_id"])
        current = service.add_page(session["session_id"])
        order = [current["pages"][2]["page_id"], current["pages"][0]["page_id"], current["pages"][1]["page_id"]]

        updated = service.reorder_pages(session["session_id"], order)

        assert [p["page_id"] for p in updated["pages"]] == order
        assert [p["page_no"] for p in updated["pages"]] == [1, 2, 3]

    def test_reorder_with_missing_page_id_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        current = service.add_page(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.reorder_pages(session["session_id"], [current["pages"][0]["page_id"], "missing"])

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_expired_session_rejects_page_writes(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        with pytest.raises(AppError) as exc_info:
            service.add_page(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

    def test_locked_session_rejects_page_writes(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.finish(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.add_page(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_LOCKED.code
