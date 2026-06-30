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

    def create(self, name: str, *, gender: str | None = None, age: int | None = None) -> dict:
        clean_name = (name or "").strip()
        if not clean_name:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="patient name 不能为空")
        normalized_gender = self._normalize_gender(gender)
        normalized_age = self._normalize_age(age)
        now = self._now()
        patient_id = self._new_patient_id()
        record = {
            "patient_id": patient_id,
            "name": clean_name,
            "gender": normalized_gender,
            "age": normalized_age,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
            "name_history": [],
        }
        self._write_patient(record)
        return record

    def update_demographics(self, patient_id: str, *, gender: str | None = None, age: int | None = None) -> dict:
        """仅更新患者人口学字段（性别/年龄），不触发姓名历史与任务快照刷新。

        字段值为 None 表示不更新对应字段；显式空字符串表示清空。
        """
        record = self.get(patient_id)
        if gender is not None:
            record["gender"] = self._normalize_gender(gender)
        if age is not None:
            record["age"] = self._normalize_age(age)
        record["updated_at"] = self._now()
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

    def refresh_snapshots_for_active_tasks(self, patient_id: str, *, deleted_task_ids: set[str] | None = None) -> int:
        """仅对 patient_id 仍指向该患者且未删除的任务刷新 patient_snapshot。

        返回被刷新的任务数。
        """
        deleted_task_ids = deleted_task_ids or set()
        patient = self._read_raw(patient_id)
        snapshot = {
            "patient_id": patient["patient_id"],
            "name": patient.get("name"),
        }
        updated = 0
        for task in self._store.list_json("tasks"):
            if not isinstance(task, dict):
                continue
            if task.get("patient_id") != patient_id:
                continue
            if task.get("deleted_at"):
                continue
            if task.get("task_id") in deleted_task_ids:
                continue
            current_snapshot = task.get("patient_snapshot") or {}
            if current_snapshot == snapshot:
                continue
            task["patient_snapshot"] = snapshot
            self._store.write(f"tasks/{task['task_id']}.json", task)
            updated += 1
        return updated

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
        normalized.setdefault("gender", None)
        normalized.setdefault("age", None)
        return normalized

    @staticmethod
    def _normalize_gender(value) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="gender 必须为字符串")
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned not in {"男", "女", "未知"}:
            raise AppError(
                ErrorCode.INVALID_REQUEST_PARAMS,
                message="gender 仅支持 男 / 女 / 未知",
            )
        return cleaned

    @staticmethod
    def _normalize_age(value) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="age 必须为整数")
        if value < 0 or value > 150:
            raise AppError(
                ErrorCode.INVALID_REQUEST_PARAMS,
                message="age 必须在 0-150 之间",
            )
        return value
