import os
import re

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

    def validate(self, data: bytes) -> dict:
        if len(data) == 0:
            from ..errors import AppError, ErrorCode
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
        if len(data) > self._max_size_bytes:
            from ..errors import AppError, ErrorCode
            raise AppError(ErrorCode.FILE_TOO_LARGE)
        header = data[:_MAX_HEADER_LEN]
        for magic, ext in _MAGIC_BYTES.items():
            if header.startswith(magic):
                return {"ext": ext}
        from ..errors import AppError, ErrorCode
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
