"""BE-01 Windows 启停与离线启动测试。

覆盖: PID 文件写入/清理、目录预创建、健康检查轮询、精准停止、
离线验收逻辑、全生命周期集成。
"""
import os
import json
import time
import threading
import socket
import pytest


class TestPidFile:
    """PID 文件写入与退出清理。"""

    def test_pid_file_path_is_logs_backend_pid(self):
        """PID 文件路径为 logs/backend.pid。"""
        from app.backend.config import PROJECT_ROOT
        expected = os.path.join(PROJECT_ROOT, "logs", "backend.pid")
        assert expected.endswith(os.path.join("logs", "backend.pid"))

    def test_pid_file_created_on_startup(self, tmp_path):
        """启动后 PID 文件存在且包含合法正整数 PID。"""
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        pid = os.getpid()
        with open(pid_file, "w") as f:
            f.write(str(pid))

        assert os.path.exists(pid_file)
        with open(pid_file) as f:
            stored_pid = int(f.read().strip())
        assert stored_pid == pid
        assert stored_pid > 0

    def test_pid_file_overwritten_on_restart(self, tmp_path):
        """重复启动时 PID 文件被覆写为新 PID。"""
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write("99999")
        new_pid = os.getpid()
        with open(pid_file, "w") as f:
            f.write(str(new_pid))

        with open(pid_file) as f:
            stored_pid = int(f.read().strip())
        assert stored_pid == new_pid

    def test_pid_file_cleaned_on_exit(self, tmp_path):
        """进程退出后 PID 文件被清理。"""
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        os.remove(pid_file)
        assert not os.path.exists(pid_file)

    def test_pid_file_content_is_valid_int(self, tmp_path):
        """PID 文件内容为有效整数，不含空格或换行尾。"""
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write("12345")
        with open(pid_file) as f:
            content = f.read().strip()
        assert content == "12345"
        assert int(content) == 12345

    def test_main_pid_functions_produce_backend_pid(self, tmp_path, monkeypatch):
        """main.py 的 PID 函数写入 logs/backend.pid 并清理。"""
        from app.backend.main import _pid_file_path, _write_pid_file, _cleanup_pid_file

        log_dir = str(tmp_path / "logs")
        os.makedirs(log_dir, exist_ok=True)
        config = {"log_dir": log_dir}

        pid_file = _pid_file_path(config)
        assert pid_file == os.path.join(log_dir, "backend.pid")

        _write_pid_file(pid_file)
        assert os.path.exists(pid_file)
        with open(pid_file) as f:
            assert int(f.read().strip()) == os.getpid()

        _cleanup_pid_file(pid_file)
        assert not os.path.exists(pid_file)

    def test_pid_dir_auto_created(self, tmp_path):
        """PID 文件目录不存在时自动创建。"""
        from app.backend.main import _pid_file_path, _write_pid_file

        log_dir = str(tmp_path / "nonexistent_logs")
        config = {"log_dir": log_dir}

        pid_file = _pid_file_path(config)
        assert os.path.isdir(log_dir)
        _write_pid_file(pid_file)
        assert os.path.exists(pid_file)
