import uuid
from datetime import datetime, timedelta, timezone

from ..enums import SessionStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class SessionService:
    def __init__(self, store: JsonStore, lan_addresses: list[str], ttl_minutes: int):
        self._store = store
        self._lan_addresses = lan_addresses
        self._ttl_minutes = ttl_minutes

    def create(self) -> dict:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self._ttl_minutes)
        qr_code_url = None
        if self._lan_addresses:
            qr_code_url = f"http://{self._lan_addresses[0]}/mobile/sessions/{session_id}"

        session = {
            "session_id": session_id,
            "status": SessionStatus.ACTIVE.value,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "qr_code_url": qr_code_url,
            "page_count": 0,
            "pages": [],
            "locked_at": None,
            "task_id": None,
        }
        self._store.write(f"sessions/{session_id}.json", session)
        return session

    def get(self, session_id: str) -> dict:
        session = self._store.read(f"sessions/{session_id}.json")
        if session is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND)

        if session["status"] == SessionStatus.ACTIVE.value:
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                session["status"] = SessionStatus.EXPIRED.value
                self._store.write(f"sessions/{session_id}.json", session)

        return session

    def _persist_session(self, session: dict) -> dict:
        self._store.write(f"sessions/{session['session_id']}.json", session)
        return session

    def _ensure_editable(self, session: dict) -> None:
        if session["status"] != SessionStatus.ACTIVE.value:
            if session["status"] == SessionStatus.EXPIRED.value:
                raise AppError(ErrorCode.SESSION_EXPIRED)
            raise AppError(ErrorCode.SESSION_LOCKED)

    def _renumber_pages(self, pages: list[dict]) -> list[dict]:
        return [
            {**page, "page_no": index}
            for index, page in enumerate(pages, start=1)
        ]

    def add_page(self, session_id: str, upload_ref=None) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        page = {
            "page_id": str(uuid.uuid4()),
            "page_no": len(session["pages"]) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "upload_ref": upload_ref,
        }
        session["pages"].append(page)
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def attach_page_upload(self, session_id: str, page_id: str, upload_ref: str) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        for page in session["pages"]:
            if page["page_id"] == page_id:
                page["upload_ref"] = upload_ref
                return self._persist_session(session)

        raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

    def delete_page(self, session_id: str, page_id: str) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        pages = [p for p in session["pages"] if p["page_id"] != page_id]
        if len(pages) == len(session["pages"]):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        session["pages"] = self._renumber_pages(pages)
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def remove_unuploaded_page(self, session_id: str, page_id: str) -> dict:
        """仅当 page.upload_ref 为空时移除 page，防止误删已成功上传页面。"""
        session = self.get(session_id)
        self._ensure_editable(session)
        target = next((p for p in session["pages"] if p["page_id"] == page_id), None)
        if target is None:
            return session
        if target.get("upload_ref"):
            raise AppError(
                ErrorCode.INVALID_REQUEST_PARAMS,
                message="页面已有上传引用，不能按失败上传撤销",
            )
        session["pages"] = self._renumber_pages(
            [p for p in session["pages"] if p["page_id"] != page_id]
        )
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def reorder_pages(self, session_id: str, page_ids: list[str]) -> dict:
        session = self.get(session_id)
        self._ensure_editable(session)

        page_by_id = {p["page_id"]: p for p in session["pages"]}
        if set(page_ids) != set(page_by_id.keys()) or len(page_ids) != len(page_by_id):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        session["pages"] = self._renumber_pages([page_by_id[page_id] for page_id in page_ids])
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)

    def finish(self, session_id: str) -> dict:
        session = self.get(session_id)

        if session["status"] == SessionStatus.LOCKED.value:
            return session

        self._ensure_editable(session)

        now = datetime.now(timezone.utc)
        page_order = []
        for page in session["pages"]:
            if not page.get("upload_ref"):
                raise AppError(ErrorCode.SESSION_EMPTY)
            page_order.append(page["page_id"])

        if not page_order:
            raise AppError(ErrorCode.SESSION_EMPTY)

        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "session_id": session_id,
            "status": "uploaded",
            "created_at": now.isoformat(),
            "page_count": len(page_order),
            "page_order": page_order,
            "source": "capture_session",
        }
        self._store.write(f"tasks/{task_id}.json", task)

        session["status"] = SessionStatus.LOCKED.value
        session["locked_at"] = now.isoformat()
        session["task_id"] = task_id
        session["page_count"] = len(session["pages"])
        return self._persist_session(session)
