import os

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.file_validator import FileValidator
from app.backend.services.page_service import PageService
from app.backend.storage.json_store import JsonStore
from app.backend.tests.fixtures.images import PDF_BYTES, PNG_BYTES


def make_page_service(tmp_path, max_size_mb=10):
    return PageService(
        file_validator=FileValidator(max_size_mb=max_size_mb, base_dir="pages"),
        store=JsonStore(str(tmp_path)),
        storage_dir=str(tmp_path),
    )


def test_save_task_image_appends_page_no_and_omits_quad(tmp_path):
    service = make_page_service(tmp_path)
    task = {
        "task_id": "task_001",
        "status": "uploading",
        "images": [],
    }

    first = service.save_task_image(task, PNG_BYTES, image_width=120, image_height=80)
    task["images"].append(first)
    second = service.save_task_image(task, PNG_BYTES, image_width=120, image_height=80)

    assert first["page_no"] == 1
    assert second["page_no"] == 2
    assert first["task_id"] == "task_001"
    assert "session_id" not in first
    assert "quad_points" not in first
    assert "processed_image_path" not in first


def test_save_task_image_creates_file_and_metadata(tmp_path):
    service = make_page_service(tmp_path)
    task = {"task_id": "task_001", "status": "uploading", "images": []}

    page = service.save_task_image(task, PNG_BYTES, image_width=120, image_height=80)

    assert os.path.isfile(page["original_image_path"])
    assert page["preview_url"] == "/api/tasks/task_001/images/page_001"
    meta = JsonStore(str(tmp_path)).read("pages/task_001/page_001.json")
    assert meta["page_id"] == "page_001"
    assert meta["task_id"] == "task_001"
    assert meta["image_width"] == 120
    assert meta["image_height"] == 80


def test_save_task_image_accepts_missing_dimensions(tmp_path):
    service = make_page_service(tmp_path)
    task = {"task_id": "task_001", "status": "uploading", "images": []}

    page = service.save_task_image(task, PNG_BYTES)

    assert page["image_width"] is None
    assert page["image_height"] is None


@pytest.mark.parametrize(
    ("image_width", "image_height"),
    [(0, 80), (120, 0), ("120", 80), (120, "80")],
)
def test_save_task_image_rejects_invalid_dimensions(tmp_path, image_width, image_height):
    service = make_page_service(tmp_path)
    task = {"task_id": "task_001", "status": "uploading", "images": []}

    with pytest.raises(AppError) as exc_info:
        service.save_task_image(task, PNG_BYTES, image_width=image_width, image_height=image_height)

    assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code


def test_save_task_image_rejects_non_image_without_writing_files(tmp_path):
    service = make_page_service(tmp_path)
    task = {"task_id": "task_001", "status": "uploading", "images": []}

    with pytest.raises(AppError) as exc_info:
        service.save_task_image(task, PDF_BYTES)

    assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code
    assert not os.path.isdir(tmp_path / "pages")
