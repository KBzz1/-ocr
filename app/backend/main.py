# app/backend/main.py
"""后端开发/调试启动入口。在生产部署中使用 run.bat。"""
import atexit
import os
import signal
import sys

# 确保项目根在 sys.path 上
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.backend import create_backend_app


def _pid_file_path(config):
    """返回 PID 文件路径，位于 logs/ 目录。"""
    log_dir = config.get("log_dir", os.path.join(_project_root, "logs"))
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "backend.pid")


def _write_pid_file(pid_file):
    """写入当前进程 PID 到文件。"""
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid_file(pid_file):
    """删除 PID 文件（退出时调用）。"""
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except OSError:
        pass


def _register_pid_cleanup(pid_file):
    """注册 PID 文件清理：atexit + SIGTERM/SIGINT。"""
    atexit.register(_cleanup_pid_file, pid_file)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda s, f, pf=pid_file: _cleanup_pid_file(pf))
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
