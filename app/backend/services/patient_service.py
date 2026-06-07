"""患者档案服务。

轻量档案:首版只保存患者姓名、系统生成的患者编号、创建/更新时间、逻辑删除状态和姓名历史。
所有持久化通过 JsonStore 写入 patients/{patient_id}.json,姓名历史属于后台维护字段,公共
序列化(to_public)必须过滤。
"""
from typing import Callable

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore
from . import patient_uuid as _patient_uuid


class PatientService:
    def __init__(
        self,
        store: JsonStore,
        *,
        now: Callable[[], str] | None = None,
        uuid_module=None,
    ):
        self._store = store
        self._now = now or self._default_now
        self._uuid = uuid_module or _patient_uuid

    def _default_now(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    # -- CRUD --

    def create(self, name: str) -> dict:
        clean_name = (name or "").strip()
        if not clean_name:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="patient name 不能为空")
        now = self._now()
        patient_id = self._new_patient_id()
        record = {
            "patient_id": patient_id,
            "name": clean_name,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "name_history": [],
        }
        self._write_patient(record)
        return record

    def get(self, patient_id: str, *, include_deleted: bool = False) -> dict:
        record = self._store.read(f"patients/{patient_id}.json")
        if record is None:
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        if record.get("deleted_at") and not include_deleted:
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        return self._normalize(record)

    def get_bindable(self, patient_id: str) -> dict:
        record = self._read_raw(patient_id)
        if record.get("deleted_at"):
            raise AppError(ErrorCode.PATIENT_DELETED)
        return self._normalize(record)

    def rename(self, patient_id: str, name: str) -> dict:
        clean_name = (name or "").strip()
        if not clean_name:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="patient name 不能为空")
        record = self.get(patient_id)
        if record["name"] == clean_name:
            return record
        now = self._now()
        record.setdefault("name_history", []).append(
            {
                "from_name": record["name"],
                "to_name": clean_name,
                "changed_at": now,
            }
        )
        record["name"] = clean_name
        record["updated_at"] = now
        self._write_patient(record)
        return record

    def mark_deleted(self, patient_id: str) -> dict:
        record = self.get(patient_id)
        if record.get("deleted_at"):
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        now = self._now()
        record["deleted_at"] = now
        record["updated_at"] = now
        self._write_patient(record)
        return record

    def list(self, query: str | None = None) -> list[dict]:
        records = [self._normalize(item) for item in self._store.list_json("patients")]
        records = [item for item in records if not item.get("deleted_at")]
        query = (query or "").strip()
        if not query:
            return records
        lowered = query.lower()
        exact_id = [item for item in records if item["patient_id"].lower() == lowered]
        if exact_id:
            return exact_id
        return [item for item in records if query in item["name"]]

    # -- public shape --

    def to_public(self, record: dict) -> dict:
        """过滤后台维护字段(name_history)。"""
        if record is None:
            return record
        return {key: value for key, value in record.items() if key != "name_history"}

    # -- internals --

    def _new_patient_id(self) -> str:
        while True:
            patient_id = f"P-{self._uuid.uuid4().hex[:8].upper()}"
            if not self._store.exists(f"patients/{patient_id}.json"):
                return patient_id

    def _read_raw(self, patient_id: str) -> dict:
        record = self._store.read(f"patients/{patient_id}.json")
        if record is None:
            raise AppError(ErrorCode.PATIENT_NOT_FOUND)
        return self._normalize(record)

    def _write_patient(self, record: dict) -> None:
        self._store.write(f"patients/{record['patient_id']}.json", record)

    def _normalize(self, record: dict) -> dict:
        normalized = dict(record)
        normalized.setdefault("name_history", [])
        normalized.setdefault("deleted_at", None)
        return normalized
