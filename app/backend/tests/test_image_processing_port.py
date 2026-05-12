import pytest
from app.backend.services.algorithm_ports.fixtures import FixtureImagePort


class TestFixtureImagePort:
    def test_fixture_returns_processed_path_from_page_id(self):
        port = FixtureImagePort(processed_dir="/tmp/processed")
        result = port.process({
            "task_id": "t1", "page_id": "p1", "page_no": 1,
            "original_path": "/tmp/original.jpg", "quad_points": None,
            "image_width": 1920, "image_height": 1080,
        })
        assert result == {"processed_path": "/tmp/processed/p1_processed.jpg"}

    def test_fixture_should_fail_raises(self):
        port = FixtureImagePort(should_fail=True)
        with pytest.raises(RuntimeError, match="fixture image processing failure"):
            port.process({
                "task_id": "t1", "page_id": "p1", "page_no": 1,
                "original_path": "/tmp/orig.jpg", "quad_points": None,
                "image_width": 1920, "image_height": 1080,
            })

    def test_fixture_records_calls(self):
        port = FixtureImagePort()
        port.process({
            "task_id": "t1", "page_id": "p1", "page_no": 1,
            "original_path": "/tmp/orig.jpg", "quad_points": None,
            "image_width": 1920, "image_height": 1080,
        })
        assert len(port.calls) == 1
        assert port.calls[0]["page_id"] == "p1"

    def test_fixture_does_not_open_files(self):
        port = FixtureImagePort(processed_dir="/nonexistent")
        result = port.process({
            "task_id": "t1", "page_id": "p1", "page_no": 1,
            "original_path": "/nonexistent/img.jpg", "quad_points": None,
            "image_width": 1920, "image_height": 1080,
        })
        assert result["processed_path"] == "/nonexistent/p1_processed.jpg"
