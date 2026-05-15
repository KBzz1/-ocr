"""BE-01 Windows 启停与离线启动测试。

覆盖: PID 文件写入/清理、目录预创建、健康检查轮询、精准停止、
离线验收逻辑、全生命周期集成。
"""
import os
import time
import pytest
from flask import Flask

from app.backend.routes.system import system_bp
from app.backend.errors import register_error_handlers


def _make_minimal_app(config_overrides=None, lan_addresses=None):
    """构建最小 Flask app，挂载 system_bp。"""
    overrides = config_overrides or {}
    app = Flask(__name__)
    app.config["BACKEND_CONFIG"] = {
        "version": "0.1.0",
        "port": 8081,
        "bind_host": "0.0.0.0",
        "local_host": "127.0.0.1",
        **overrides,
    }
    app.config["STARTED_AT"] = "2026-05-12T00:00:00+00:00"
    app.config["LAN_ADDRESSES"] = lan_addresses or []
    register_error_handlers(app)
    app.register_blueprint(system_bp)
    return app


class TestPidFile:
    """PID 文件写入与退出清理。"""

    def test_pid_file_path_is_logs_backend_pid(self):
        from app.backend.config import PROJECT_ROOT
        expected = os.path.join(PROJECT_ROOT, "logs", "backend.pid")
        assert expected.endswith(os.path.join("logs", "backend.pid"))

    def test_pid_file_created_on_startup(self, tmp_path):
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
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        os.remove(pid_file)
        assert not os.path.exists(pid_file)

    def test_pid_file_content_is_valid_int(self, tmp_path):
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write("12345")
        with open(pid_file) as f:
            content = f.read().strip()
        assert content == "12345"
        assert int(content) == 12345

    def test_main_pid_functions_produce_backend_pid(self, tmp_path):
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
        from app.backend.main import _pid_file_path, _write_pid_file

        log_dir = str(tmp_path / "nonexistent_logs")
        config = {"log_dir": log_dir}

        pid_file = _pid_file_path(config)
        assert os.path.isdir(log_dir)
        _write_pid_file(pid_file)
        assert os.path.exists(pid_file)


class TestStopBatch:
    """stop.bat 精准停止行为验证。"""

    def test_stop_uses_pid_file_not_port_indiscriminate(self):
        stop_content = open("stop.bat").read()
        assert "netstat" not in stop_content, (
            "stop.bat 不应使用 netstat 批量查找端口进程，应改用 PID 文件精准停止"
        )

    def test_stop_reads_logs_backend_pid(self, tmp_path):
        pid_file = os.path.join(str(tmp_path), "logs", "backend.pid")
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        test_pid = 12345
        with open(pid_file, "w") as f:
            f.write(str(test_pid))
        with open(pid_file) as f:
            stored_pid = f.read().strip()
        assert stored_pid == str(test_pid)

    def test_stop_handles_missing_pid_file_gracefully(self, tmp_path):
        pid_file = os.path.join(str(tmp_path), "nonexistent.pid")
        assert not os.path.exists(pid_file)
        result = "PID 文件不存在，后端可能未运行"
        assert "PID 文件不存在" in result

    def test_stop_cleans_pid_file_after_kill(self, tmp_path):
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write("12345")
        os.remove(pid_file)
        assert not os.path.exists(pid_file)

    def test_stop_verifies_command_line_before_kill(self):
        stop_content = open("stop.bat").read()
        assert "app.backend.main" in stop_content or "app.backend" in stop_content, (
            "stop.bat 应校验进程命令行属于本项目（包含 app.backend.main）后才终止"
        )

    def test_stop_pid_file_empty_graceful(self, tmp_path):
        pid_file = os.path.join(str(tmp_path), "backend.pid")
        with open(pid_file, "w") as f:
            f.write("")
        with open(pid_file) as f:
            content = f.read().strip()
        assert content == ""
        os.remove(pid_file)
        assert not os.path.exists(pid_file)

    def test_stop_cleans_stale_pid_when_process_is_not_backend(self):
        stop_content = open("stop.bat").read()
        assert "not a manzufei_ocr backend process" in stop_content
        assert 'del "%PID_FILE%"' in stop_content
        assert "exit /b 0" in stop_content

    def test_stop_uses_pushd_for_unc_project_paths(self):
        stop_content = open("stop.bat").read()
        assert 'pushd "%~dp0"' in stop_content
        assert 'cd /d "%~dp0"' not in stop_content

    def test_stop_uses_ascii_output_to_avoid_cmd_codepage_mojibake(self):
        stop_content = open("stop.bat", encoding="utf-8").read()
        assert stop_content.isascii()


class TestDirectoryCreation:
    """目录预创建逻辑验证 — run.bat 行为对应。"""

    def test_directories_auto_created_on_config_load(self, tmp_path):
        from app.backend.config import load_config

        config_dir = str(tmp_path)
        config = load_config(config_dir)
        for key in ("data_dir", "log_dir", "export_dir"):
            assert os.path.isdir(config[key]), f"{key} 目录应自动创建"

    def test_missing_dirs_created_before_backend_start(self, tmp_path):
        data = str(tmp_path / "data")
        logs = str(tmp_path / "logs")
        exports = str(tmp_path / "exports")
        for d in (data, logs, exports):
            assert not os.path.exists(d)
            os.makedirs(d, exist_ok=True)
            assert os.path.isdir(d)

    def test_log_file_append(self, tmp_path):
        log_file = str(tmp_path / "backend.log")
        with open(log_file, "a") as f:
            f.write("line 1\n")
        with open(log_file, "a") as f:
            f.write("line 2\n")
        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert lines[0].strip() == "line 1"
        assert lines[1].strip() == "line 2"


class TestHealthCheckPolling:
    """健康检查轮询逻辑验证。"""

    def test_health_check_timeout_on_closed_port(self):
        import urllib.request
        import urllib.error

        port = 18081
        max_wait = 3
        url = f"http://127.0.0.1:{port}/api/system/status"
        waited = 0
        ready = False

        while waited < max_wait:
            try:
                urllib.request.urlopen(url, timeout=1)
                ready = True
                break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(1)
            waited += 1

        assert not ready
        assert waited == max_wait

    def test_health_check_success_returns_running(self, tmp_path):
        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"

    def test_health_check_response_has_required_fields(self):
        app = _make_minimal_app(lan_addresses=["192.168.1.100:8081"])
        client = app.test_client()
        resp = client.get("/api/system/status")
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"
        assert "version" in data["data"]
        assert "started_at" in data["data"]
        assert "lan_addresses" in data["data"]

    def test_lan_addresses_excludes_localhost(self):
        app = _make_minimal_app(lan_addresses=[
            "192.168.1.100:8081",
            "127.0.0.1:8081",
            "10.0.0.5:8081",
        ])
        client = app.test_client()
        resp = client.get("/api/system/status")
        data = resp.get_json()
        assert "127.0.0.1:8081" not in data["data"]["lan_addresses"]
        assert "192.168.1.100:8081" in data["data"]["lan_addresses"]
        assert "10.0.0.5:8081" in data["data"]["lan_addresses"]


class TestOfflineVerification:
    """离线验收关键逻辑验证。"""

    def test_config_missing_uses_defaults(self, tmp_path):
        from app.backend.config import load_config

        nonexistent_dir = str(tmp_path / "nonexistent_config")
        config = load_config(nonexistent_dir)
        assert config["port"] == 8081
        assert config["bind_host"] == "0.0.0.0"
        assert config["version"] == "0.1.0"

    def test_directories_auto_created_on_startup(self, tmp_path):
        from app.backend.config import load_config

        config_dir = str(tmp_path)
        config = load_config(config_dir)
        for key in ("data_dir", "log_dir", "export_dir"):
            assert os.path.isdir(config[key]), f"{key} 目录应自动创建"

    def test_no_external_network_on_status_check(self):
        app = _make_minimal_app(lan_addresses=["192.168.1.100:8081"])
        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"

    def test_offline_startup_check_only_uses_loopback_status(self):
        content = open("scripts/offline_startup_check.py").read().lower()

        assert "http://127.0.0.1:8081/api/system/status" in content
        assert "8.8.8.8" not in content
        assert "ping" not in content
        assert "subprocess" not in content
        assert "popen" not in content

    def test_offline_startup_check_reports_required_directories(self, tmp_path, monkeypatch):
        import scripts.offline_startup_check as check

        monkeypatch.setattr(check, "PROJECT_ROOT", tmp_path)
        for name in ("data", "exports", "logs"):
            (tmp_path / name).mkdir()

        check.check_directories()


class TestStartupShutdownIntegration:
    """启动 → 健康检查 → 停止 全周期集成测试。"""

    def test_full_lifecycle_directories_and_pid(self, tmp_path):
        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))
        config = app.config["BACKEND_CONFIG"]

        assert os.path.isdir(config["data_dir"]), "data_dir 应已创建"
        assert os.path.isdir(config["log_dir"]), "log_dir 应已创建"
        assert os.path.isdir(config["export_dir"]), "export_dir 应已创建"

        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"
        assert "version" in data["data"]
        assert "started_at" in data["data"]
        assert "lan_addresses" in data["data"]

    def test_offline_startup_no_external_requests(self, tmp_path, monkeypatch):
        import socket as sock_module

        external_calls = []
        original_create_connection = sock_module.create_connection

        def tracked_create_connection(address, *args, **kwargs):
            host = address[0]
            if not host.startswith("127.") and host != "localhost":
                external_calls.append(address)
                raise OSError("Blocked: external connection in offline mode")
            return original_create_connection(address, *args, **kwargs)

        monkeypatch.setattr(sock_module, "create_connection", tracked_create_connection)

        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        assert len(external_calls) == 0, (
            f"离线模式下不应发起外部连接，实际: {external_calls}"
        )

    def test_status_contains_required_fields(self):
        app = _make_minimal_app(lan_addresses=[
            "192.168.1.100:8081",
            "127.0.0.1:8081",
            "10.0.0.5:8081",
        ])
        client = app.test_client()
        resp = client.get("/api/system/status")
        data = resp.get_json()
        assert data["data"]["status"] == "running"
        assert data["data"]["version"] == "0.1.0"
        assert "T" in data["data"]["started_at"]
        assert "127.0.0.1:8081" not in data["data"]["lan_addresses"]
        assert "192.168.1.100:8081" in data["data"]["lan_addresses"]
        assert "10.0.0.5:8081" in data["data"]["lan_addresses"]


def test_run_bat_opens_frontend_workstation_not_health_check():
    """run.bat 打开后端托管的工作台入口，而不是健康检查 JSON 或 Vite。"""
    content = open("run.bat").read()
    assert "WORKSTATION_URL=http://127.0.0.1:8081/" in content
    assert 'start "" "%WORKSTATION_URL%"' in content
    assert "127.0.0.1:5173" not in content
    assert 'start "" "http://127.0.0.1:8081/api/system/status"' not in content


def test_run_bat_health_check_still_uses_status_endpoint():
    """WIN-NW-002: run.bat 健康检查仍使用 /api/system/status"""
    content = open("run.bat").read()
    assert "http://127.0.0.1:8081/api/system/status" in content


def test_run_bat_starts_backend_without_vite_dev_server():
    """run.bat 不应启动 Vite dev server，手机扫码统一访问后端 8081。"""
    content = open("run.bat").read()
    assert "-m app.backend.main" in content
    assert "npm run dev" not in content
    assert "FRONTEND_HEALTH_URL" not in content
    assert "WORKSTATION_URL=http://127.0.0.1:8081/" in content


def test_run_bat_rebuilds_frontend_dist_before_backend_start():
    """run.bat 每次启动前构建前端，避免后端托管旧扫码逻辑。"""
    content = open("run.bat").read()
    assert 'set "FRONTEND_DIST_INDEX=%FRONTEND_DIR%\\dist\\index.html"' in content
    assert "npm run build" in content
    assert "ensure_frontend_dist" in content
    assert "if exist \"%FRONTEND_DIST_INDEX%\"" not in content


def test_run_bat_handles_stale_pid_before_starting_backend():
    """run.bat 启动前必须处理旧 PID，避免把脏 PID 当成启动成功。"""
    content = open("run.bat").read()
    assert "Found existing PID file" in content
    assert 'del "%PID_FILE%"' in content
    assert "backend_ready_existing" in content


def test_run_bat_uses_pushd_for_unc_project_paths():
    """run.bat 从 \\wsl.localhost 这类 UNC 路径启动时必须能进入仓库目录。"""
    content = open("run.bat").read()
    assert 'pushd "%~dp0"' in content
    assert 'cd /d "%~dp0"' not in content


def test_run_bat_uses_ascii_output_to_avoid_cmd_codepage_mojibake():
    """run.bat 不依赖中文输出，避免 CMD 代码页不匹配时乱码成错误命令。"""
    content = open("run.bat", encoding="utf-8").read()
    assert content.isascii()


def test_wsl_run_script_starts_backend_without_vite_dev_server():
    """run.sh 在 WSL 内只启动后端，不依赖 Vite dev server。"""
    content = open("run.sh").read()
    assert "CONDA_PYTHON" in content
    assert "miniconda3/envs/manzufei_ocr/bin/python" in content
    assert "-m app.backend.main" in content
    assert "setsid -f" in content
    assert "npm run dev" not in content
    assert "http://127.0.0.1:5173/" not in content
    assert "http://127.0.0.1:8081/" in content
    assert "cmd.exe" not in content
    assert "start " not in content


def test_wsl_stop_script_stops_backend_and_frontend_pids():
    """stop.sh 读取 WSL PID 文件停止前后端。"""
    content = open("stop.sh").read()
    assert 'BACKEND_PID_FILE="$LOG_DIR/backend.pid"' in content
    assert 'FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"' in content
    assert "kill" in content
    assert "cmd.exe" not in content
