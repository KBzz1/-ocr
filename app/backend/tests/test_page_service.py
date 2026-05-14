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

        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)

        full = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        assert os.path.isdir(full)
        files = os.listdir(full)
        assert any(f == f"{page_id}.jpg" for f in files)

    def test_save_page_creates_metadata_json(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)

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

        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)
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

        result = ps.save(session["session_id"], page2["page_id"], page2["page_no"], _make_jpg(), 1920, 1080)
        assert result["page_no"] == page2["page_no"]
        assert result["page_no"] == 2

    def test_upload_ref_written_back(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)

        current = ss.get(session["session_id"])
        assert current["pages"][0]["upload_ref"] is not None
        assert not os.path.isabs(current["pages"][0]["upload_ref"])
        assert current["pages"][0]["upload_ref"].endswith(".json")

    def test_quad_points_null_when_not_provided(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)
        assert result["quad_points"] is None

    def test_quad_points_preserved_when_valid(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        quad = [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]
        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080,
                         quad_points_raw=json.dumps(quad))
        assert result["quad_points"] == quad

    def test_session_isolation_different_directories(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        s1 = ss.create()
        p1 = ss.add_page(s1["session_id"])["pages"][0]["page_id"]
        ps.save(s1["session_id"], p1, 1, _make_jpg(), 1920, 1080)

        s2 = ss.create()
        p2 = ss.add_page(s2["session_id"])["pages"][0]["page_id"]
        ps.save(s2["session_id"], p2, 1, _make_jpg(), 1920, 1080)

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

        result = ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)
        assert result["processed_image_path"] is None

    def test_image_width_height_must_be_positive(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        with pytest.raises(AppError) as exc_info:
            ps.save(session["session_id"], page_id, 1, _make_jpg(), 0, 1080)
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code

    def test_file_save_failure_keeps_upload_ref_null(self, tmp_path):
        from app.backend.errors import AppError
        ps = make_page_service(tmp_path, max_size_mb=1)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        big = b'\xff\xd8\xff\xe0' + b'\x00' * (2 * 1024 * 1024)
        try:
            ps.save(session["session_id"], page_id, 1, big, 1920, 1080)
        except AppError:
            pass

        current = ss.get(session["session_id"])
        page = current["pages"][0]
        assert page["page_id"] == page_id
        assert page["upload_ref"] is None


class TestPageServiceSaveCleanup:
    """失败上传时 PageService 应清理本次已写出的半成品文件。"""

    def test_save_invalid_file_type_writes_no_files(self, tmp_path):
        """文件类型非法时不会写入任何文件。"""
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        pdf_data = b'%PDF-1.4 fake pdf'
        try:
            ps.save(session["session_id"], page_id, 1, pdf_data, 1920, 1080)
        except AppError as e:
            assert e.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code

        base = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        if os.path.isdir(base):
            files = os.listdir(base)
            assert not files, f"不应写入任何文件，实际: {files}"

    def test_save_invalid_quad_writes_no_files(self, tmp_path):
        """quad 非法时不会写入任何文件。"""
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        try:
            ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080,
                    quad_points_raw="[[0,0],[2000,0]]")
        except AppError as e:
            assert e.code == ErrorCode.INVALID_QUAD_POINTS.code

        base = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        if os.path.isdir(base):
            files = os.listdir(base)
            assert not files, f"不应写入任何文件，实际: {files}"

    def test_save_metadata_write_failure_removes_image(self, tmp_path):
        """元数据写入失败时删除已写出的图片文件。"""
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        original_write = ps._store.write
        def fail_on_metadata(path, data):
            if path.endswith(".json"):
                raise OSError("disk full")
            return original_write(path, data)

        from unittest.mock import patch
        with patch.object(ps._store, "write", side_effect=fail_on_metadata):
            with pytest.raises(OSError, match="disk full"):
                ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)

        base = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        files = os.listdir(base) if os.path.isdir(base) else []
        jpg_files = [f for f in files if f.endswith(".jpg")]
        assert not jpg_files, f"图片文件应已被删除，实际: {jpg_files}"

    def test_save_attach_failure_removes_image_and_metadata(self, tmp_path):
        """attach 失败时同时删除图片文件和元数据文件。"""
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        from unittest.mock import patch
        with patch.object(ps._session_service, "attach_page_upload",
                          side_effect=AppError(ErrorCode.SESSION_NOT_FOUND)):
            with pytest.raises(AppError) as exc_info:
                ps.save(session["session_id"], page_id, 1, _make_jpg(), 1920, 1080)
            assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code

        base = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        if os.path.isdir(base):
            files = os.listdir(base)
            assert not files, f"图片和元数据文件应都被删除，实际: {files}"

    def test_save_cleanup_does_not_remove_other_page_files(self, tmp_path):
        """清理只删除本次 page 对应文件，不删除同 session 其他 page 的文件。"""
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()

        # 第一个页面成功上传
        updated1 = ss.add_page(session["session_id"])
        page1 = updated1["pages"][0]
        ps.save(session["session_id"], page1["page_id"], 1, _make_jpg(), 1920, 1080)

        # 第二个页面上传时模拟 attach 失败
        updated2 = ss.add_page(session["session_id"])
        page2 = updated2["pages"][1]

        from app.backend.errors import AppError, ErrorCode
        from unittest.mock import patch
        with patch.object(ps._session_service, "attach_page_upload",
                          side_effect=AppError(ErrorCode.SESSION_NOT_FOUND)):
            with pytest.raises(AppError):
                ps.save(session["session_id"], page2["page_id"], 2, _make_jpg(), 1920, 1080)

        # 第一个页面的文件仍然存在
        base = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        files = os.listdir(base)
        assert f"{page1['page_id']}.jpg" in files
        assert f"{page1['page_id']}.json" in files
        # 第二个页面的文件已被清理
        assert f"{page2['page_id']}.jpg" not in files
        assert f"{page2['page_id']}.json" not in files


class TestPageServiceQuadUpdate:
    def test_update_quad_preserves_image_and_page_order(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        ps.save(session["session_id"], page["page_id"], page["page_no"], _make_jpg(), 1920, 1080)

        new_quad = json.dumps([
            [100, 100],
            [1800, 100],
            [1800, 900],
            [100, 900],
        ])

        updated = ps.update_quad(session["session_id"], page["page_id"], new_quad)

        assert updated["page_id"] == page["page_id"]
        assert updated["page_no"] == 1
        assert updated["quad_points"] == [
            [100, 100],
            [1800, 100],
            [1800, 900],
            [100, 900],
        ]
        assert updated["quad_updated_at"] is not None
        current = ss.get(session["session_id"])
        assert current["pages"][0]["page_id"] == page["page_id"]
        assert current["pages"][0]["page_no"] == 1

    def test_update_quad_rejects_invalid_points_without_changing_metadata(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode

        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(
            session["session_id"],
            page["page_id"],
            page["page_no"],
            _make_jpg(),
            1920,
            1080,
            quad_points_raw=json.dumps([[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
        )

        with pytest.raises(AppError) as exc_info:
            ps.update_quad(session["session_id"], page["page_id"], "not json")

        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code
        meta = ps._store.read(f"data/pages/{session['session_id']}/{page['page_id']}.json")
        assert meta["quad_points"] == original["quad_points"]
        assert "quad_updated_at" not in meta


class TestPageServiceReplaceImage:
    def test_replace_image_preserves_page_id_and_page_no(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(session["session_id"], page["page_id"], page["page_no"], _make_jpg(), 1920, 1080)

        replacement_quad = json.dumps([
            [50, 60],
            [950, 60],
            [950, 1260],
            [50, 1260],
        ])

        updated = ps.replace_image(
            session["session_id"],
            page["page_id"],
            b"\xff\xd8\xff\xe0" + b"\x11" * 120,
            1000,
            1400,
            replacement_quad,
        )

        assert updated["page_id"] == original["page_id"]
        assert updated["page_no"] == original["page_no"]
        assert updated["image_width"] == 1000
        assert updated["image_height"] == 1400
        assert updated["quad_points"] == [
            [50, 60],
            [950, 60],
            [950, 1260],
            [50, 1260],
        ]
        assert updated["uploaded_at"] is not None
        assert updated["quad_updated_at"] is not None
        assert ss.get(session["session_id"])["pages"][0]["page_id"] == page["page_id"]

    def test_replace_image_failure_keeps_previous_metadata(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode

        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(
            session["session_id"],
            page["page_id"],
            page["page_no"],
            _make_jpg(),
            1920,
            1080,
            quad_points_raw=json.dumps([[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
        )

        with pytest.raises(AppError) as exc_info:
            ps.replace_image(
                session["session_id"],
                page["page_id"],
                b"%PDF-1.4 fake pdf",
                1000,
                1400,
                json.dumps([[0, 0], [1000, 0], [1000, 1400], [0, 1400]]),
            )

        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code
        meta = ps._store.read(f"data/pages/{session['session_id']}/{page['page_id']}.json")
        assert meta["original_image_path"] == original["original_image_path"]
        assert meta["image_width"] == 1920
        assert meta["image_height"] == 1080
        assert meta["quad_points"] == original["quad_points"]
