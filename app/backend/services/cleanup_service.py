import os
import shutil

from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class CleanupService:
    def __init__(self, config: dict, store: JsonStore):
        self._config = config
        self._store = store

    def plan_task_cleanup(self, task_id: str) -> dict:
        task = self._store.read(f"tasks/{task_id}.json")
        session_id = task.get("session_id") if isinstance(task, dict) else None
        return {
            "task_id": task_id,
            "session_id": session_id,
            "requires_confirm": True,
            "storage_paths": [f"results/{task_id}", f"tasks/{task_id}.json"],
            "export_paths": [f"exports/{task_id}"],
            "log_cleanup": "日志按轮转策略处理，不按任务物理删除",
        }

    def cleanup_task(self, task_id: str, confirm: bool) -> dict:
        if confirm is not True:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理任务必须显式传入 confirm=true")
        plan = self.plan_task_cleanup(task_id)
        deleted = []
        failed = []
        for rel in plan["storage_paths"]:
            try:
                self._delete_under_root(self._config["storage_dir"], rel)
                deleted.append(rel)
            except OSError:
                failed.append(rel)
        for rel in plan["export_paths"]:
            export_rel = rel.removeprefix("exports/")
            try:
                self._delete_under_root(self._config["export_dir"], export_rel)
                deleted.append(rel)
            except OSError:
                failed.append(rel)
        return {"task_id": task_id, "deleted": deleted, "failed": failed, "log_cleanup": plan["log_cleanup"]}

    def _delete_under_root(self, root: str, relative_path: str) -> None:
        safe = self._safe_relative_path(relative_path)
        root_abs = os.path.abspath(root)
        target = os.path.abspath(os.path.join(root_abs, safe))
        if not target.startswith(root_abs + os.sep) and target != root_abs:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径越权")
        if os.path.islink(target):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="拒绝删除符号链接")
        if os.path.isdir(target):
            shutil.rmtree(target)
        elif os.path.isfile(target):
            os.remove(target)

    def _safe_relative_path(self, value: str) -> str:
        if not value or value in (".", os.sep) or os.path.isabs(value):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径非法")
        normalized = os.path.normpath(value)
        if normalized == "." or normalized.startswith("..") or os.path.isabs(normalized):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="清理路径越权")
        return normalized
