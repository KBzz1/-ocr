from datetime import datetime, timezone

from ..enums import TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class TaskService:
    def __init__(self, store: JsonStore):
        self._store = store

    def list_tasks(self, status: str | None = None) -> list[dict]:
        tasks = [self._normalize_task(task) for task in self._store.list_json("tasks")]
        if status is not None:
            tasks = [task for task in tasks if task["status"] == status]
        return [
            {
                "task_id": task["task_id"],
                "session_id": task["session_id"],
                "status": task["status"],
                "created_at": task["created_at"],
                "page_count": task["page_count"],
            }
            for task in sorted(tasks, key=lambda item: item["task_id"])
        ]

    def get_task(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        return self._normalize_task(task)

    def process(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "触发任务处理")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")

    def retry(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.FAILED.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": TaskStatus.PROCESSING.value},
            )
        task = self._transition(task, TaskStatus.PROCESSING.value, "失败任务重试")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED", "算法模块未配置")

    def mark_ready(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.READY_FOR_REVIEW.value, "算法处理完成")
        task["ready_at"] = self._now()
        self._write_task(task)
        return task

    def mark_failed(self, task_id: str, error_code: str, error_message: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.FAILED.value, error_message)
        task["error_code"] = error_code
        task["error_message"] = error_message
        task["failed_at"] = self._now()
        self._write_task(task)
        return task

    def mark_confirmed(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.CONFIRMED.value, "审核确认")
        self._write_task(task)
        return task

    def mark_exported(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.EXPORTED.value, "导出完成")
        self._write_task(task)
        return task

    def _read_task(self, task_id: str) -> dict:
        task = self._store.read(f"tasks/{task_id}.json")
        if task is None:
            raise AppError(ErrorCode.TASK_NOT_FOUND)
        return self._normalize_task(task)

    def _write_task(self, task: dict) -> None:
        self._store.write(f"tasks/{task['task_id']}.json", task)

    def _normalize_task(self, task: dict) -> dict:
        normalized = dict(task)
        normalized.setdefault("error_code", None)
        normalized.setdefault("error_message", None)
        normalized.setdefault("failed_at", None)
        normalized.setdefault("processing_at", None)
        normalized.setdefault("ready_at", None)
        normalized.setdefault(
            "status_history",
            [
                {
                    "from_status": None,
                    "to_status": normalized["status"],
                    "changed_at": normalized["created_at"],
                    "reason": "采集会话完成采集",
                }
            ],
        )
        normalized["page_summary"] = {
            "page_count": normalized.get("page_count", 0),
            "page_order": normalized.get("page_order", []),
        }
        normalized.setdefault("document_summary", None)
        normalized.setdefault(
            "review_summary",
            {"status": None, "unreviewed_count": None, "suspicious_count": None},
        )
        normalized.setdefault("export_summary", {"last_exported_at": None, "formats": []})
        return normalized

    def _transition(self, task: dict, target: str, reason: str) -> dict:
        current = task["status"]
        self._validate_transition(current, target)
        task["status"] = target
        self._add_history(task, current, target, reason)
        return task

    def _validate_transition(self, current: str, target: str) -> None:
        try:
            valid = TaskStatus.is_valid_transition(current, target)
        except ValueError:
            valid = False
        if not valid:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": current, "target": target},
            )

    def _add_history(self, task: dict, current: str, target: str, reason: str) -> None:
        task.setdefault("status_history", [])
        task["status_history"].append(
            {
                "from_status": current,
                "to_status": target,
                "changed_at": self._now(),
                "reason": reason,
            }
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
