import json
import os
import pytest
from app.backend.storage.json_store import JsonStore


class TestJsonStoreInit:
    def test_creates_base_dir(self, tmp_path):
        base = tmp_path / "store"
        JsonStore(str(base))
        assert base.is_dir()

    def test_existing_dir_ok(self, tmp_path):
        store = JsonStore(str(tmp_path))
        assert store._base_dir == str(tmp_path)


class TestReadWrite:
    def test_write_and_read_dict(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("tasks/task_001.json", {"status": "created", "pages": 3})
        data = store.read("tasks/task_001.json")
        assert data == {"status": "created", "pages": 3}

    def test_read_with_default(self, tmp_path):
        store = JsonStore(str(tmp_path))
        data = store.read("nonexistent.json", default={"fallback": True})
        assert data == {"fallback": True}

    def test_read_nonexistent_without_default(self, tmp_path):
        store = JsonStore(str(tmp_path))
        data = store.read("nonexistent.json")
        assert data is None

    def test_atomic_write_does_not_leave_tmp(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("data.json", {"key": "value"})
        tmp_files = list(tmp_path.glob("*.tmp"))
        nested_tmp = list(tmp_path.glob("**/*.tmp"))
        assert len(tmp_files) == 0
        assert len(nested_tmp) == 0

    def test_write_creates_parent_dir(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("a/b/c/data.json", {"x": 1})
        assert (tmp_path / "a" / "b" / "c" / "data.json").is_file()


class TestExists:
    def test_exists_returns_true(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("test.json", {"a": 1})
        assert store.exists("test.json") is True

    def test_exists_returns_false(self, tmp_path):
        store = JsonStore(str(tmp_path))
        assert store.exists("nonexistent.json") is False


class TestDelete:
    def test_delete_removes_file(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.write("test.json", {"a": 1})
        store.delete("test.json")
        assert not store.exists("test.json")

    def test_delete_nonexistent_does_not_raise(self, tmp_path):
        store = JsonStore(str(tmp_path))
        store.delete("nonexistent.json")


class TestPathSecurity:
    def test_rejects_parent_traversal(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.write("../outside.json", {"bad": True})

    def test_rejects_absolute_path(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.read("/etc/passwd")

    def test_rejects_double_dot_middle(self, tmp_path):
        store = JsonStore(str(tmp_path))
        with pytest.raises(ValueError, match="路径越权"):
            store.write("tasks/../../outside.json", {"bad": True})
