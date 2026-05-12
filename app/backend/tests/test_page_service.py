import json
import os
import pytest
from datetime import datetime, timezone
from app.backend.storage.json_store import JsonStore


def _make_jpg():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


def make_page_service(tmp_path, max_size_mb=10):
    from app.backend.services.file_validator import FileValidator
    from app.backend.services.session_service import SessionService
    from app.backend.services.page_service import PageService

    store = JsonStore(str(tmp_path))
    ss = SessionService(store, ["192.168.1.5:8081"], 30)
    fv = FileValidator(max_size_mb=max_size_mb, base_dir="data/pages")
    return PageService(
        session_service=ss,
        file_validator=fv,
        store=store,
        storage_dir=str(tmp_path),
        min_quad_area_ratio=0.01,
    )


class TestPageService:
    def test_save_page_creates_image_file(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        full = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        assert os.path.isdir(full)
        files = os.listdir(full)
        assert any(f == f"{page_id}.jpg" for f in files)

    def test_save_page_creates_metadata_json(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        meta_dir = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        meta_path = os.path.join(meta_dir, f"{page_id}.json")
        assert os.path.isfile(meta_path)
        meta = json.loads(open(meta_path, encoding="utf-8").read())
        assert meta["page_id"] == page_id
        assert meta["image_width"] == 1920
        assert meta["image_height"] == 1080
        assert meta["processed_image_path"] is None

    def test_save_page_returns_page_dict(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["page_id"] == page_id
        assert result["session_id"] == session["session_id"]
        assert result["page_no"] == 1
        assert "original_image_path" in result
        assert result["uploaded_at"] is not None

    def test_page_id_and_page_no_from_session_service(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        ss.add_page(session["session_id"])
        updated = ss.add_page(session["session_id"])
        page2 = updated["pages"][-1]

        result = ps.save(session["session_id"], page2["page_id"], _make_jpg(), 1920, 1080)
        assert result["page_no"] == page2["page_no"]
        assert result["page_no"] == 2

    def test_upload_ref_written_back(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        current = ss.get(session["session_id"])
        assert current["pages"][0]["upload_ref"] is not None
        assert current["pages"][0]["upload_ref"].endswith(".json")

    def test_quad_points_null_when_not_provided(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["quad_points"] is None

    def test_quad_points_preserved_when_valid(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        quad = [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]
        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080,
                         quad_points_raw=json.dumps(quad))
        assert result["quad_points"] == quad

    def test_session_isolation_different_directories(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        s1 = ss.create()
        p1 = ss.add_page(s1["session_id"])["pages"][0]["page_id"]
        ps.save(s1["session_id"], p1, _make_jpg(), 1920, 1080)

        s2 = ss.create()
        p2 = ss.add_page(s2["session_id"])["pages"][0]["page_id"]
        ps.save(s2["session_id"], p2, _make_jpg(), 1920, 1080)

        d1 = os.path.join(str(tmp_path), "data", "pages", s1["session_id"])
        d2 = os.path.join(str(tmp_path), "data", "pages", s2["session_id"])
        assert d1 != d2
        assert os.path.isdir(d1)
        assert os.path.isdir(d2)

    def test_processed_image_path_is_null(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["processed_image_path"] is None

    def test_image_width_height_must_be_positive(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        with pytest.raises(AppError) as exc_info:
            ps.save(session["session_id"], page_id, _make_jpg(), 0, 1080)
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code

    def test_file_save_failure_keeps_upload_ref_null(self, tmp_path):
        from app.backend.errors import AppError
        ps = make_page_service(tmp_path, max_size_mb=1)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        big = b'\xff\xd8\xff\xe0' + b'\x00' * (2 * 1024 * 1024)
        try:
            ps.save(session["session_id"], page_id, big, 1920, 1080)
        except AppError:
            pass

        current = ss.get(session["session_id"])
        page = current["pages"][0]
        assert page["page_id"] == page_id
        assert page["upload_ref"] is None
