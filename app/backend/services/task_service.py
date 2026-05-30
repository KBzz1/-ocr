from datetime import datetime, timezone
from secrets import token_urlsafe
from threading import Thread
from typing import Callable

from ..enums import TaskStatus
from ..errors import ErrorCode, AppError
from ..routes import _safe_event
from ..storage.json_store import JsonStore


class TaskService:
    def __init__(
        self,
        store: JsonStore,
        orchestrator=None,
        schema_provider: Callable[[], dict] | None = None,
        background_runner: Callable[[Callable[[], None]], None] | None = None,
        document_profiles=None,
    ):
        self._store = store
        self._orchestrator = orchestrator
        self._schema_provider = schema_provider
        self._background_runner = background_runner or self._run_in_thread
        self._document_profiles = document_profiles

    def _document_summary_for(self, document_type: str | None = None) -> dict:
        if self._document_profiles is None:
            schema = self._schema_provider() if self._schema_provider else {}
            return {
                "document_type": document_type or schema.get("document_type") or "copd_admission_record",
                "document_type_label": "入院记录",
                "schema_version": schema.get("version"),
                "prompt_version": None,
                "extraction_profile": document_type or schema.get("document_type") or "copd_admission_record",
            }
        resolved_type = document_type or self._document_profiles.get_default_document_type()
        return self._document_profiles.to_task_document_summary(resolved_type)

    def create_uploading_task(self, base_url: str) -> dict:
        existing_count = len(self._store.list_json("tasks"))
        task_id = str(existing_count + 1)
        now = self._now()
        upload_token = token_urlsafe(24)
        document_summary = self._document_summary_for()
        task = {
            "task_id": task_id,
            "display_name": task_id,
            "status": TaskStatus.UPLOADING.value,
            "created_at": now,
            "updated_at": now,
            "upload_token": upload_token,
            "images": [],
            "error_code": None,
            "error_message": None,
            "failed_at": None,
            "review_summary": None,
            "export_summary": {"last_exported_at": None, "formats": [], "files": []},
            "document_type": document_summary["document_type"],
            "document_type_label": document_summary["document_type_label"],
            "schema_version": document_summary["schema_version"],
            "prompt_version": document_summary["prompt_version"],
            "extraction_profile": document_summary["extraction_profile"],
            "status_history": [
                {
                    "from_status": None,
                    "to_status": TaskStatus.UPLOADING.value,
                    "changed_at": now,
                    "reason": "创建上传任务",
                }
            ],
        }
        self._write_task(task)
        task = self._normalize_task(task)
        task["mobile_upload_url"] = self._build_mobile_upload_url(base_url, task_id, upload_token)
        return task

    def _build_mobile_upload_url(self, base_url: str, task_id: str, upload_token: str) -> str:
        return f"{base_url.rstrip('/')}/mobile/upload/{task_id}?token={upload_token}"

    def list_tasks(self, status: str | None = None, base_url: str | None = None) -> list[dict]:
        tasks = [self._normalize_task(task) for task in self._store.list_json("tasks")]
        tasks = [task for task in tasks if self._should_list_task(task)]
        if status is not None:
            tasks = [task for task in tasks if task["status"] == status]
        return [self._to_task_summary(task, base_url=base_url) for task in sorted(tasks, key=lambda item: item["task_id"])]

    def _should_list_task(self, task: dict) -> bool:
        return not (task["status"] == TaskStatus.UPLOADING.value and task["page_count"] == 0)

    def delete_task(self, task_id: str) -> dict:
        """永久删除任务：校验状态后移除任务 JSON 文件。

        processing 状态的任务不可删除，需先取消处理。
        关联的 pages/results/exports 目录由 CleanupService 清理。
        """
        task = self._read_task(task_id)
        if task["status"] == TaskStatus.PROCESSING.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": "deleted"},
            )
        self._store.delete(f"tasks/{task_id}.json")
        return task

    def rename_task(self, task_id: str, display_name: str) -> dict:
        task = self._read_task(task_id)
        task["display_name"] = display_name
        task["updated_at"] = self._now()
        self._write_task(task)
        return self._normalize_task(task)

    def change_document_type(self, task_id: str, document_type: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.UPLOADING.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": "document_type_change"},
            )
        document_summary = self._document_summary_for(document_type)
        task.update(document_summary)
        task["updated_at"] = self._now()
        self._write_task(task)
        if self._document_profiles is not None:
            self._document_profiles.remember_last_document_type(document_summary["document_type"])
        return self._normalize_task(task)

    def _to_task_summary(self, task: dict, base_url: str | None = None) -> dict:
        summary = {
            "task_id": task["task_id"],
            "display_name": task.get("display_name", task["task_id"]),
            "status": task["status"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "page_count": task["page_count"],
            "review_summary": task["review_summary"],
            "export_summary": task["export_summary"],
            "processing_summary": task.get("processing_summary"),
            "error_code": task["error_code"],
            "error_message": task["error_message"],
            "document_type": task.get("document_type"),
            "document_type_label": task.get("document_type_label"),
            "schema_version": task.get("schema_version"),
            "prompt_version": task.get("prompt_version"),
        }
        upload_token = task.get("upload_token")
        if task["status"] == TaskStatus.UPLOADING.value and upload_token and base_url:
            summary["upload_token"] = upload_token
            summary["mobile_upload_url"] = self._build_mobile_upload_url(base_url, task["task_id"], upload_token)
        return summary

    def get_task(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        return self._normalize_task(task)

    def process(self, task_id: str, schema: dict | None = None) -> dict:
        task = self._start_processing(task_id, "触发任务处理")
        return self._dispatch_orchestrator(task, schema=schema)

    def retry(self, task_id: str, schema: dict | None = None) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.FAILED.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": TaskStatus.PROCESSING.value},
            )
        task = self._start_processing(task_id, "失败任务重试")
        return self._dispatch_orchestrator(task, schema=schema)

    def assert_upload_token(self, task: dict, token: str | None) -> None:
        if not token or token != task.get("upload_token"):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="上传令牌无效")

    def add_image(self, task_id: str, page: dict) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.UPLOADING.value:
            raise AppError(ErrorCode.TASK_UPLOAD_CLOSED)
        task.setdefault("images", []).append(page)
        task["updated_at"] = self._now()
        self._write_task(task)
        return page

    def finish_upload(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.UPLOADING.value:
            return task
        if not task.get("images"):
            raise AppError(ErrorCode.TASK_EMPTY)
        task = self._transition(task, TaskStatus.PROCESSING.value, "完成上传")
        task["processing_at"] = self._now()
        task["updated_at"] = task["processing_at"]
        task["processing_summary"] = self._build_processing_summary(
            "queued",
            "running",
            task["processing_at"],
            page_count=len(task.get("images") or []),
        )
        self._write_task(task)
        _safe_event("task_processing_started", task_id=task_id)
        return self._dispatch_orchestrator(task)

    def cancel_processing(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.PROCESSING.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                details={"current": task["status"], "target": TaskStatus.FAILED.value},
            )
        task = self._transition(task, TaskStatus.FAILED.value, "用户取消处理")
        task["error_code"] = ErrorCode.TASK_PROCESSING_CANCELLED.code
        task["error_message"] = "用户取消处理"
        task["failed_at"] = self._now()
        task["updated_at"] = task["failed_at"]
        task["details"] = {"stage": "processing", "reason": "user_cancelled"}
        task["processing_summary"] = self._build_processing_summary(
            task.get("processing_summary", {}).get("stage", "processing") if isinstance(task.get("processing_summary"), dict) else "processing",
            "cancelled",
            task.get("processing_at"),
            page_count=len(task.get("images") or []),
        )
        self._write_task(task)
        _safe_event("task_processing_cancelled", task_id=task_id)
        return self._normalize_task(task)

    def mark_ready(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.PROCESSING.value and task.get("error_code") == ErrorCode.TASK_PROCESSING_CANCELLED.code:
            return task
        task = self._transition(task, TaskStatus.REVIEW.value, "算法处理完成")
        task["ready_at"] = self._now()
        task["updated_at"] = task["ready_at"]
        task["processing_summary"] = self._build_processing_summary(
            "done",
            "success",
            task.get("processing_at"),
            page_count=len(task.get("images") or []),
        )
        self._write_task(task)
        _safe_event("task_review_ready", task_id=task_id, schema_version=task.get("schema_version"))
        return task

    def mark_failed(
        self,
        task_id: str,
        error_code: str,
        error_message: str,
        stage: str = "processing",
        details: dict | None = None,
    ) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.PROCESSING.value and task.get("error_code") == ErrorCode.TASK_PROCESSING_CANCELLED.code:
            return task
        task = self._transition(task, TaskStatus.FAILED.value, error_message)
        task["error_code"] = error_code
        task["error_message"] = error_message
        task["failed_at"] = self._now()
        task["updated_at"] = task["failed_at"]
        task["details"] = {"stage": stage, **(details or {})}
        task["processing_summary"] = self._build_processing_summary(
            stage,
            "failed",
            task.get("processing_at"),
            page_count=len(task.get("images") or []),
        )
        self._write_task(task)
        _safe_event(
            "task_processing_failed",
            level="ERROR",
            task_id=task_id,
            error_code=error_code,
            stage=stage,
            reason=error_message,
        )
        return task

    def complete_review(self, task_id: str, review_summary: dict | None = None) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.DONE.value, "审核完成")
        task["done_at"] = self._now()
        task["updated_at"] = task["done_at"]
        if review_summary is not None:
            task["review_summary"] = review_summary
        self._write_task(task)
        return task

    def reopen_review(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.REVIEW.value, "重新审核")
        task["updated_at"] = self._now()
        self._write_task(task)
        return task

    def record_export(self, task_id: str, format: str, relative_path: str) -> dict:
        task = self._read_task(task_id)
        self._update_export_summary(task, format=format, relative_path=relative_path)
        task["updated_at"] = self._now()
        self._write_task(task)
        return task

    def mark_exported(self, task_id: str, format: str | None = None, relative_path: str | None = None, task: dict | None = None) -> dict:
        task = task or self._read_task(task_id)
        self._update_export_summary(task, format=format, relative_path=relative_path)
        self._write_task(task)
        return task

    def _update_export_summary(self, task: dict, format: str | None, relative_path: str | None) -> None:
        summary = task.setdefault("export_summary", {"last_exported_at": None, "formats": [], "files": []})
        summary["last_exported_at"] = self._now()

        if format is not None:
            # Deduplicate formats list
            if format not in summary["formats"]:
                summary["formats"].append(format)

            # Update or append files entry
            files = summary.setdefault("files", [])
            existing = next((f for f in files if f["format"] == format), None)
            if existing is not None:
                existing["relative_path"] = relative_path
            else:
                files.append({"format": format, "relative_path": relative_path})

    def _start_processing(self, task_id: str, reason: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, reason)
        task["processing_at"] = self._now()
        task["updated_at"] = task["processing_at"]
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        task["processing_summary"] = self._build_processing_summary(
            "queued",
            "running",
            task["processing_at"],
            page_count=len(task.get("images") or []),
        )
        task.pop("details", None)
        self._write_task(task)
        _safe_event("task_processing_started", task_id=task_id)
        return task

    def _dispatch_orchestrator(self, task: dict, schema: dict | None = None) -> dict:
        dispatched_task = dict(task)
        self._background_runner(lambda: self._run_orchestrator(dispatched_task, schema=schema))
        return task

    def mark_processing_stage(self, task_id: str, stage: str, status: str, page_count: int | None = None) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.PROCESSING.value:
            return task
        task["processing_summary"] = self._build_processing_summary(
            stage,
            status,
            task.get("processing_at"),
            page_count=page_count if page_count is not None else len(task.get("images") or []),
        )
        task["updated_at"] = self._now()
        self._write_task(task)
        return task

    def _run_orchestrator(self, task: dict, schema: dict | None = None) -> dict:
        if self.is_processing_cancelled(task["task_id"]):
            return self.get_task(task["task_id"])
        if self._orchestrator is None:
            return self.mark_failed(
                task["task_id"],
                ErrorCode.ALGORITHM_MODULE_NOT_CONFIGURED.code,
                "图像处理模块未配置",
                stage="image_processing",
                details={"stage": "image_processing", "reason": "module_not_configured"},
        )

        schema_for_run = schema
        if self._document_profiles is not None:
            try:
                profile = self._document_profiles.get_profile(task.get("document_type"))
            except AppError as exc:
                return self.mark_failed(
                    task["task_id"],
                    ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                    "文书模板未注册或未完成接入",
                    stage="field_extraction",
                    details={
                        "stage": "field_extraction",
                        "reason": "document_type_not_registered",
                        "document_type": task.get("document_type"),
                        "error_code": exc.code,
                    },
                )
            schema_for_run = profile.schema
        elif schema_for_run is None and self._schema_provider is not None:
            schema_for_run = self._schema_provider()

        return self._orchestrator.run(task, self, schema=schema_for_run)

    def is_processing_cancelled(self, task_id: str) -> bool:
        task = self._read_task(task_id)
        return task["status"] != TaskStatus.PROCESSING.value

    def _read_task(self, task_id: str) -> dict:
        task = self._store.read(f"tasks/{task_id}.json")
        if task is None:
            raise AppError(ErrorCode.TASK_NOT_FOUND)
        return self._normalize_task(task)

    def _write_task(self, task: dict) -> None:
        self._store.write(f"tasks/{task['task_id']}.json", task)

    def _normalize_task(self, task: dict) -> dict:
        normalized = dict(task)
        normalized.setdefault("display_name", task["task_id"])
        normalized.setdefault("images", [])
        normalized.setdefault("error_code", None)
        normalized.setdefault("error_message", None)
        normalized.setdefault("failed_at", None)
        normalized.setdefault("processing_at", None)
        normalized.setdefault("ready_at", None)
        normalized.setdefault("confirmed_at", None)
        normalized.setdefault("updated_at", normalized.get("created_at"))
        normalized.setdefault(
            "status_history",
            [
                {
                    "from_status": None,
                    "to_status": normalized["status"],
                    "changed_at": normalized["created_at"],
                    "reason": "创建上传任务",
                }
            ],
        )
        normalized["page_count"] = len(normalized["images"])
        normalized.setdefault("document_summary", None)
        normalized.setdefault("review_summary", None)
        normalized.setdefault("export_summary", {"last_exported_at": None, "formats": [], "files": []})
        normalized.setdefault("processing_summary", None)
        normalized.setdefault("document_type", "copd_admission_record")
        normalized.setdefault("document_type_label", "入院记录")
        normalized.setdefault("schema_version", None)
        normalized.setdefault("prompt_version", None)
        normalized.setdefault("extraction_profile", normalized.get("document_type"))
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

    def _build_processing_summary(
        self,
        stage: str,
        status: str,
        started_at: str | None,
        page_count: int = 0,
    ) -> dict:
        now = self._now()
        elapsed_seconds = 0
        if started_at:
            try:
                elapsed_seconds = max(0, int((datetime.fromisoformat(now) - datetime.fromisoformat(started_at)).total_seconds()))
            except ValueError:
                elapsed_seconds = 0
        return {
            "stage": stage,
            "status": status,
            "label": _PROCESSING_STAGE_LABELS.get(stage, "处理中"),
            "progress_percent": _PROCESSING_STAGE_PROGRESS.get(stage, 10),
            "page_count": page_count,
            "started_at": started_at,
            "updated_at": now,
            "elapsed_seconds": elapsed_seconds,
        }

    def _run_in_thread(self, run: Callable[[], None]) -> None:
        Thread(target=run, daemon=True).start()


_PROCESSING_STAGE_LABELS = {
    "queued": "等待处理",
    "image_processing": "准备图片",
    "document_parsing": "OCR 文档解析",
    "field_extraction": "正在利用LLM结构化提取",
    "done": "处理完成",
}

_PROCESSING_STAGE_PROGRESS = {
    "queued": 5,
    "image_processing": 20,
    "document_parsing": 55,
    "field_extraction": 85,
    "done": 100,
}
