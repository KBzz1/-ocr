import pytest
from app.backend.services.algorithm_ports.fixtures import FixtureDocPort


class TestFixtureDocPort:
    def test_fixture_presets_pages_verbatim(self):
        pages = [{"page_id": "p1", "page_no": 1, "status": "success", "text": "preset", "blocks": [], "tables": []}]
        port = FixtureDocPort(pages=pages, merged_text="preset merged")
        result = port.parse({"task_id": "t1", "image_paths": [], "pages": []})
        assert result["pages"] is pages
        assert result["merged_text"] == "preset merged"

    def test_fixture_generates_pages_from_input(self):
        port = FixtureDocPort(merged_text="generated")
        result = port.parse({
            "task_id": "t1", "image_paths": ["/tmp/p1.jpg"],
            "pages": [{"page_id": "p1", "page_no": 1, "processed_path": "/tmp/p1.jpg"}],
        })
        assert len(result["pages"]) == 1
        assert result["pages"][0]["status"] == "success"
        assert result["pages"][0]["text"] == "text of p1"

    def test_fixture_return_empty(self):
        port = FixtureDocPort(return_empty=True)
        result = port.parse({"task_id": "t1", "image_paths": [], "pages": []})
        assert result["pages"] == []

    def test_fixture_should_fail_raises(self):
        port = FixtureDocPort(should_fail=True)
        with pytest.raises(RuntimeError, match="fixture document parsing failure"):
            port.parse({"task_id": "t1", "image_paths": [], "pages": []})

    def test_fixture_partial_page_failure(self):
        port = FixtureDocPort(partial_fail_page_id="p1")
        result = port.parse({
            "task_id": "t1", "image_paths": ["/tmp/p1.jpg", "/tmp/p2.jpg"],
            "pages": [
                {"page_id": "p1", "page_no": 1, "processed_path": "/tmp/p1.jpg"},
                {"page_id": "p2", "page_no": 2, "processed_path": "/tmp/p2.jpg"},
            ],
        })
        assert result["pages"][0]["status"] == "failed"
        assert result["pages"][1]["status"] == "success"

    def test_fixture_does_not_read_image_content(self):
        port = FixtureDocPort()
        result = port.parse({
            "task_id": "t1", "image_paths": ["/nonexistent/img.jpg"],
            "pages": [{"page_id": "p1", "page_no": 1, "processed_path": "/nonexistent/img.jpg"}],
        })
        assert len(result["pages"]) == 1
