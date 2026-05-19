import os
from datetime import datetime, timezone

from .file_validator import FileValidator
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class PageService:
    def __init__(self, file_validator: FileValidator, store: JsonStore, storage_dir: str):
        self._file_validator = file_validator
        self._store = store
        self._storage_dir = os.path.realpath(storage_dir)

    def _safe_remove(self, path: str) -> None:
        if not path:
            return
        real = os.path.realpath(path)
        if not real.startswith(self._storage_dir + os.sep):
            return
        try:
            os.remove(real)
        except OSError:
            pass

    def save_task_image(
        self,
        task: dict,
        image_data: bytes,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> dict:
        if image_width is not None and (not isinstance(image_width, int) or image_width <= 0):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 必须为正整数")
        if image_height is not None and (not isinstance(image_height, int) or image_height <= 0):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_height 必须为正整数")

        validation = self._file_validator.validate(image_data)
        ext = validation["ext"]
        page_no = len(task.get("images", [])) + 1
        page_id = f"page_{page_no:03d}"
        rel_path = self._file_validator.build_path(task["task_id"], page_id, ext)
        abs_image_path = os.path.join(self._storage_dir, rel_path)
        os.makedirs(os.path.dirname(abs_image_path), exist_ok=True)

        with open(abs_image_path, "wb") as f:
            f.write(image_data)

        page = {
            "page_id": page_id,
            "task_id": task["task_id"],
            "page_no": page_no,
            "original_image_path": abs_image_path,
            "preview_url": f"/api/tasks/{task['task_id']}/images/{page_id}",
            "image_width": image_width,
            "image_height": image_height,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        meta_rel = self._file_validator.build_path(task["task_id"], page_id, "json")
        try:
            self._store.write(meta_rel, page)
        except Exception:
            self._safe_remove(abs_image_path)
            raise
        return page
