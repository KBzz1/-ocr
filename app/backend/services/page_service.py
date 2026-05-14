import json
import os
from datetime import datetime, timezone

from .file_validator import FileValidator
from .quad_validator import validate_quad_points
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class PageService:
    def __init__(
        self,
        session_service,
        file_validator: FileValidator,
        store: JsonStore,
        storage_dir: str,
        min_quad_area_ratio: float = 0.01,
    ):
        self._session_service = session_service
        self._file_validator = file_validator
        self._store = store
        self._storage_dir = os.path.realpath(storage_dir)
        self._min_quad_area_ratio = min_quad_area_ratio

    def _safe_remove(self, path: str) -> None:
        """安全删除文件：确认路径位于 storage_dir 内后再删除。"""
        if not path:
            return
        real = os.path.realpath(path)
        if not real.startswith(self._storage_dir + os.sep):
            return
        try:
            os.remove(real)
        except OSError:
            pass

    def save(
        self,
        session_id: str,
        page_id: str,
        page_no: int,
        image_data: bytes,
        image_width: int,
        image_height: int,
        quad_points_raw: str | None = None,
    ) -> dict:
        if not isinstance(image_width, int) or image_width <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS,
                           message="image_width 必须为正整数")
        if not isinstance(image_height, int) or image_height <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS,
                           message="image_height 必须为正整数")

        validation = self._file_validator.validate(image_data)
        ext = validation["ext"]

        quad_points = validate_quad_points(
            quad_points_raw, image_width, image_height, self._min_quad_area_ratio
        )

        rel_path = self._file_validator.build_path(session_id, page_id, ext)
        abs_image_path = os.path.join(self._storage_dir, rel_path)
        os.makedirs(os.path.dirname(abs_image_path), exist_ok=True)
        with open(abs_image_path, "wb") as f:
            f.write(image_data)

        meta_rel = self._file_validator.build_path(session_id, page_id, "json")
        meta = {
            "page_id": page_id,
            "session_id": session_id,
            "page_no": page_no,
            "original_image_path": abs_image_path,
            "processed_image_path": None,
            "image_width": image_width,
            "image_height": image_height,
            "quad_points": quad_points,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._store.write(meta_rel, meta)
        except Exception:
            self._safe_remove(abs_image_path)
            raise

        try:
            self._session_service.attach_page_upload(session_id, page_id, meta_rel)
        except Exception:
            self._safe_remove(abs_image_path)
            meta_abs = os.path.join(self._storage_dir, meta_rel)
            self._safe_remove(meta_abs)
            raise

        return meta

    def update_quad(
        self,
        session_id: str,
        page_id: str,
        quad_points_raw: str | None,
    ) -> dict:
        session = self._session_service.get(session_id)
        page = next((p for p in session.get("pages", []) if p.get("page_id") == page_id), None)
        if page is None or not page.get("upload_ref"):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        meta = self._store.read(page["upload_ref"])
        if meta is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        quad_points = validate_quad_points(
            quad_points_raw,
            int(meta["image_width"]),
            int(meta["image_height"]),
            self._min_quad_area_ratio,
        )
        meta["quad_points"] = quad_points
        meta["quad_updated_at"] = datetime.now(timezone.utc).isoformat()
        self._store.write(page["upload_ref"], meta)
        return meta
