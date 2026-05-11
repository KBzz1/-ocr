# app/backend/main.py
"""后端开发/调试启动入口。在生产部署中使用 run.bat。"""
import os
import sys

# 确保项目根在 sys.path 上
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.backend import create_backend_app


def main():
    app = create_backend_app()
    config = app.config["BACKEND_CONFIG"]
    debug = os.environ.get("MANZUFEI_BACKEND_DEBUG") == "1"
    print("后端服务启动中...")
    print(f"  本地访问: http://{config['local_host']}:{config['port']}")
    print(f"  健康检查: http://{config['local_host']}:{config['port']}/api/system/status")
    app.run(host=config["bind_host"], port=config["port"], debug=debug)


if __name__ == "__main__":
    main()
