# app/backend/main.py
"""后端开发/调试启动入口。在生产部署中使用 run.bat。"""
import atexit
import os
import signal
import sys

from app.backend.config import PROJECT_ROOT as _project_root
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.backend import create_backend_app


def _pid_file_path(config):
    log_dir = config.get("log_dir", os.path.join(_project_root, "logs"))
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "backend.pid")


def _write_pid_file(pid_file):
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid_file(pid_file):
    try:
        os.remove(pid_file)
    except FileNotFoundError:
        pass


def _register_pid_cleanup(pid_file):
    def _handle_shutdown(signum, frame):
        _cleanup_pid_file(pid_file)
        raise SystemExit(0)

    atexit.register(_cleanup_pid_file, pid_file)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_shutdown)
        except (ValueError, OSError):
            pass


def main():
    app = create_backend_app()
    config = app.config["BACKEND_CONFIG"]
    debug = os.environ.get("MANZUFEI_BACKEND_DEBUG") == "1"

    pid_file = _pid_file_path(config)
    _write_pid_file(pid_file)
    _register_pid_cleanup(pid_file)

    print("后端服务启动中...")
    print(f"  PID: {os.getpid()}")
    print(f"  PID 文件: {pid_file}")
    print(f"  本地访问: http://{config['local_host']}:{config['port']}")
    print(f"  健康检查: http://{config['local_host']}:{config['port']}/api/system/status")
    app.run(host=config["bind_host"], port=config["port"], debug=debug)


if __name__ == "__main__":
    main()
