import pytest
from app.backend.errors import AppError, ErrorCode


def _make_jpg_bytes():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


def _make_png_bytes():
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * 100


def _make_bmp_bytes():
    return b'BM' + b'\x00' * 100


def make_validator(max_size_mb=10):
    from app.backend.services.file_validator import FileValidator
    return FileValidator(max_size_mb=max_size_mb)


class TestMagicBytesDetection:
    def test_accepts_jpg_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_jpg_bytes())
        assert result["ext"] == "jpg"

    def test_accepts_png_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_png_bytes())
        assert result["ext"] == "png"

    def test_accepts_bmp_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_bmp_bytes())
        assert result["ext"] == "bmp"

    def test_rejects_pdf_by_magic_bytes(self):
        validator = make_validator()
        pdf_bytes = b'%PDF-1.4' + b'\x00' * 100
        with pytest.raises(AppError) as exc_info:
            validator.validate(pdf_bytes)
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code

    def test_rejects_text_file_with_jpg_extension(self):
        validator = make_validator()
        text_bytes = b'this is not an image file'
        with pytest.raises(AppError) as exc_info:
            validator.validate(text_bytes)
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code

    def test_generates_extension_from_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_png_bytes())
        assert result["ext"] == "png"


class TestPathSafety:
    def test_rejects_path_traversal(self):
        validator = make_validator()
        dangerous = ["../etc/passwd", "..\\windows", "sess/../etc", "~/root"]
        for sid in dangerous:
            with pytest.raises(ValueError):
                validator.build_path(sid, "abc123", "jpg")

    def test_rejects_null_byte(self):
        validator = make_validator()
        with pytest.raises(ValueError):
            validator.build_path("abc\x00def", "abc123", "jpg")

    def test_accepts_valid_ids(self):
        validator = make_validator()
        path = validator.build_path("550e8400-e29b-41d4-a716-446655440000",
                                     "660e8400-e29b-41d4-a716-446655440001", "jpg")
        assert path.endswith(".jpg")
        assert "550e8400" in path

    def test_relative_path_stays_within_pages_dir(self):
        validator = make_validator()
        path = validator.build_path("sess-1", "page-1", "png")
        assert ".." not in path


class TestFileSizeValidation:
    def test_rejects_file_exceeding_size_limit(self):
        validator = make_validator(max_size_mb=1)
        big = b'\xff\xd8\xff\xe0' + b'\x00' * (1024 * 1024 + 1)
        with pytest.raises(AppError) as exc_info:
            validator.validate(big)
        assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE.code

    def test_file_size_at_boundary_accepted(self):
        validator = make_validator(max_size_mb=1)
        boundary = b'\xff\xd8\xff\xe0' + b'\x00' * (1024 * 1024 - 4)
        result = validator.validate(boundary)
        assert result["ext"] == "jpg"

    def test_empty_file_rejected(self):
        validator = make_validator(max_size_mb=1)
        with pytest.raises(AppError) as exc_info:
            validator.validate(b'')
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code
