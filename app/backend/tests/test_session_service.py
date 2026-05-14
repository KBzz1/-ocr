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

        assert session["qr_code_url"] == f"http://10.0.0.2:8081/mobile/sessions/{session['session_id']}"

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
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")
        service.finish(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.add_page(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_LOCKED.code

    def test_attach_page_upload_updates_upload_ref(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        current = service.add_page(session["session_id"])
        page_id = current["pages"][0]["page_id"]

        updated = service.attach_page_upload(
            session["session_id"],
            page_id,
            f"pages/{session['session_id']}/{page_id}.json",
        )

        assert updated["pages"][0]["upload_ref"] == f"pages/{session['session_id']}/{page_id}.json"

    def test_attach_missing_page_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        with pytest.raises(AppError) as exc_info:
            service.attach_page_upload(session["session_id"], "missing-page", "pages/x.json")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_attach_upload_rejects_locked_session(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        current = service.add_page(session["session_id"])
        page_id = current["pages"][0]["page_id"]
        service.attach_page_upload(session["session_id"], page_id, "pages/existing.json")
        service.finish(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.attach_page_upload(session["session_id"], page_id, "pages/x.json")

        assert exc_info.value.code == ErrorCode.SESSION_LOCKED.code


class TestRemoveUnuploadedPage:
    def test_removes_only_empty_page_and_renumbers(self, tmp_path):
        """移除 upload_ref 为空的 page，保持剩余页面顺序。"""
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")
        current = service.add_page(session["session_id"])
        empty_page_id = current["pages"][1]["page_id"]

        updated = service.remove_unuploaded_page(session["session_id"], empty_page_id)

        assert updated["page_count"] == 1
        assert len(updated["pages"]) == 1
        assert updated["pages"][0]["page_no"] == 1
        assert updated["pages"][0]["upload_ref"] == "pages/page-1.json"
        assert empty_page_id not in [p["page_id"] for p in updated["pages"]]

    def test_is_idempotent_for_missing_page(self, tmp_path):
        """page 不存在时幂等返回当前 session。"""
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")

        updated = service.remove_unuploaded_page(session["session_id"], "nonexistent-page")

        assert updated["page_count"] == 1
        assert len(updated["pages"]) == 1

    def test_rejects_page_with_upload_ref(self, tmp_path):
        """已有 upload_ref 的 page 不能被补偿删除。"""
        service = make_service(tmp_path)
        session = service.create()
        current = service.add_page(session["session_id"], upload_ref="pages/page-1.json")
        page_id = current["pages"][0]["page_id"]

        with pytest.raises(AppError) as exc_info:
            service.remove_unuploaded_page(session["session_id"], page_id)

        assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code
        assert "已有上传引用" in exc_info.value.message
        # page still exists
        after = service.get(session["session_id"])
        assert len(after["pages"]) == 1

    def test_respects_expired_and_locked_guards(self, tmp_path):
        """expired/locked session 保持现有 guard 行为。"""
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        service.add_page(session["session_id"])
        current = service.get(session["session_id"])
        page_id = current["pages"][0]["page_id"]

        # expired
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        with pytest.raises(AppError) as exc_info:
            service.remove_unuploaded_page(session["session_id"], page_id)
        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

        # locked: recreate session, upload, finish
        service2 = make_service(tmp_path)
        s2 = service2.create()
        c2 = service2.add_page(s2["session_id"], upload_ref="pages/page-x.json")
        p2 = c2["pages"][0]["page_id"]
        service2.finish(s2["session_id"])

        with pytest.raises(AppError) as exc_info2:
            service2.remove_unuploaded_page(s2["session_id"], p2)
        assert exc_info2.value.code == ErrorCode.SESSION_LOCKED.code


class TestSessionFinish:
    def test_finish_locks_active_session_and_sets_locked_at(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")

        finished = service.finish(session["session_id"])

        assert finished["status"] == "locked"
        assert finished["locked_at"] is not None

    def test_finish_creates_task_stub_with_frozen_page_order(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")
        service.add_page(session["session_id"], upload_ref="pages/page-2.json")
        current = service.get(session["session_id"])
        expected_order = [p["page_id"] for p in current["pages"]]

        finished = service.finish(session["session_id"])

        task = JsonStore(str(tmp_path)).read(f"tasks/{finished['task_id']}.json")
        assert task["task_id"] == finished["task_id"]
        assert task["session_id"] == session["session_id"]
        assert task["status"] == "uploaded"
        assert task["page_count"] == 2
        assert task["page_order"] == expected_order
        assert task["source"] == "capture_session"

    def test_finish_persists_task_id_to_session(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")

        finished = service.finish(session["session_id"])
        persisted = JsonStore(str(tmp_path)).read(f"sessions/{session['session_id']}.json")

        assert persisted["task_id"] == finished["task_id"]

    def test_finish_idempotent_on_locked_session(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"], upload_ref="pages/page-1.json")

        first = service.finish(session["session_id"])
        second = service.finish(session["session_id"])

        assert second["task_id"] == first["task_id"]
        assert second["locked_at"] == first["locked_at"]
        assert len(os.listdir(tmp_path / "tasks")) == 1

    def test_finish_expired_session_raises_session_expired(self, tmp_path):
        service = make_service(tmp_path, ttl_minutes=1)
        session = service.create()
        session["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        JsonStore(str(tmp_path)).write(f"sessions/{session['session_id']}.json", session)

        with pytest.raises(AppError) as exc_info:
            service.finish(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EXPIRED.code

    def test_finish_nonexistent_session_raises_session_not_found(self, tmp_path):
        service = make_service(tmp_path)

        with pytest.raises(AppError) as exc_info:
            service.finish("missing")

        assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

    def test_finish_empty_session_raises_session_empty(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()

        with pytest.raises(AppError) as exc_info:
            service.finish(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EMPTY.code

    def test_finish_placeholder_page_without_upload_ref_raises_session_empty(self, tmp_path):
        service = make_service(tmp_path)
        session = service.create()
        service.add_page(session["session_id"])

        with pytest.raises(AppError) as exc_info:
            service.finish(session["session_id"])

        assert exc_info.value.code == ErrorCode.SESSION_EMPTY.code
        assert not (tmp_path / "tasks").exists()
