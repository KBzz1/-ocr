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
