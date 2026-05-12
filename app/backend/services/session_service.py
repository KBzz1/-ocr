import uuid
from datetime import datetime, timedelta, timezone

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
            qr_code_url = f"http://{self._lan_addresses[0]}/mobile/{session_id}"

        session = {
            "session_id": session_id,
            "status": "active",
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

        if session["status"] == "active":
            expires_at = datetime.fromisoformat(session["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                session["status"] = "expired"
                self._store.write(f"sessions/{session_id}.json", session)

        return session
