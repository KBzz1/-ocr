import os
import re

from ..errors import AppError, ErrorCode

_MAGIC_BYTES = {
    b'\xff\xd8\xff': "jpg",
    b'\x89PNG': "png",
    b'BM': "bmp",
}
_MAX_HEADER_LEN = max(len(m) for m in _MAGIC_BYTES)
_SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]+$')


class FileValidator:
    def __init__(self, max_size_mb: int = 10, base_dir: str = "data/pages"):
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._base_dir = base_dir

    def build_path(self, session_id: str, page_id: str, ext: str) -> str:
        """生成安全保存路径，拒绝路径穿越字符。返回相对路径。"""
        for value in (session_id, page_id, ext):
            if not _SAFE_ID_PATTERN.match(value):
                raise ValueError("非法路径字符")
        return os.path.join(self._base_dir, session_id, f"{page_id}.{ext}")

    def validate(self, data: bytes) -> dict:
        if len(data) == 0:
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
        if len(data) > self._max_size_bytes:
            raise AppError(ErrorCode.FILE_TOO_LARGE)
        header = data[:_MAX_HEADER_LEN]
        for magic, ext in _MAGIC_BYTES.items():
            if header.startswith(magic):
                return {"ext": ext}
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
