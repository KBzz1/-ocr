# app/backend/main.py
"""后端开发/调试启动入口。在生产部署中使用 run.bat。"""
import atexit
import logging
import os
import signal
import sys

from app.backend.config import PROJECT_ROOT as _project_root
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logger = logging.getLogger(__name__)

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


def _redirect_stdouterr_to_boot_log(log_dir: str) -> None:
    """将进程 stdout/stderr 重定向到 boot.log（冷），避免污染热日志。"""
    boot_path = os.path.join(log_dir, "boot.log")
    os.makedirs(log_dir, exist_ok=True)
    boot_fh = open(boot_path, "a", encoding="utf-8")
    os.dup2(boot_fh.fileno(), sys.stdout.fileno())
    os.dup2(boot_fh.fileno(), sys.stderr.fileno())


def main():
    app = create_backend_app()
    config = app.config["BACKEND_CONFIG"]
    debug = os.environ.get("MANZUFEI_BACKEND_DEBUG") == "1"

    pid_file = _pid_file_path(config)
    _write_pid_file(pid_file)
    _register_pid_cleanup(pid_file)

    _redirect_stdouterr_to_boot_log(config["log_dir"])

    logger.info("后端服务启动中... PID=%d PID文件=%s 本地访问=http://%s:%d",
                os.getpid(), pid_file, config["local_host"], config["port"])
    app.run(host=config["bind_host"], port=config["port"], debug=debug)


if __name__ == "__main__":
    main()
