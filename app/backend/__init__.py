# app/backend/__init__.py
import os
import socket
from datetime import datetime, timezone
from ipaddress import ip_address

from flask import Flask, request, send_file, send_from_directory
from werkzeug.exceptions import NotFound
from werkzeug.utils import safe_join

from .config import PROJECT_ROOT, load_config
from .errors import register_error_handlers


def _is_loopback_ipv4(address: str) -> bool:
    try:
        parsed = ip_address(address)
    except ValueError:
        return True
    return parsed.version == 4 and parsed.is_loopback


def _get_lan_addresses(port: int) -> list[str]:
    """返回候选局域网地址列表，排除回环地址。

    UDP connect 只让操作系统选择本机出站地址，不发送数据包，也不依赖 DNS。
    """
    addresses = []
    for target in ("10.255.255.255", "192.0.2.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 1))
                addr = sock.getsockname()[0]
            if not _is_loopback_ipv4(addr):
                addresses.append(f"{addr}:{port}")
        except OSError:
            continue

    seen = set()
    unique = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)
    return unique


def _register_static_serve(app: Flask, static_dir: str) -> None:
    """注册静态文件服务 + SPA fallback。"""
    from .errors import AppError, ErrorCode
    from .responses import error_response

    @app.before_request
    def _serve_spa():
        if request.path.startswith("/api/"):
            return None

        relative_path = request.path.lstrip("/") or "index.html"
        file_path = safe_join(static_dir, relative_path)
        if file_path is None:
            raise NotFound()

        if os.path.splitext(request.path)[1]:
            if os.path.isfile(file_path):
                return send_from_directory(static_dir, relative_path)
            raise NotFound()

        index_path = safe_join(static_dir, "index.html")
        if index_path and os.path.isfile(index_path):
            return send_file(index_path)

        return error_response(AppError(ErrorCode.REQUEST_NOT_FOUND))


def create_backend_app(config_dir: str | None = None) -> Flask:
    config = load_config(config_dir)

    app = Flask(__name__)
    app.config["BACKEND_CONFIG"] = config
    app.config["STARTED_AT"] = datetime.now(timezone.utc).isoformat()
    app.config["LAN_ADDRESSES"] = _get_lan_addresses(config["port"])

    register_error_handlers(app)
    _register_static_serve(app, config["static_dir"])

    from .storage.json_store import JsonStore

    store = JsonStore(config["storage_dir"])

    from .services.local_event_log import LocalEventLog
    from .services.offline_check_service import OfflineCheckService

    event_log = LocalEventLog(
        config["log_dir"],
        max_bytes=config["log_max_bytes"],
        backup_count=config["log_backup_count"],
    )
    app.config["LOCAL_EVENT_LOG"] = event_log
    app.config["OFFLINE_CHECK_SERVICE"] = OfflineCheckService(config)

    from .services.cleanup_service import CleanupService

    app.config["CLEANUP_SERVICE"] = CleanupService(config=config, store=store)

    event_log.safe_write(
        "system_started",
        port=config["port"],
        lan_addresses_count=len(app.config["LAN_ADDRESSES"]),
    )
    event_log.safe_write("algorithm_module_not_configured", level="WARNING", stage="image_processing")

    from .services.file_validator import FileValidator
    from .services.page_service import PageService

    file_validator = FileValidator(
        max_size_mb=config["max_upload_file_size_mb"],
        base_dir="pages",
    )
    page_service = PageService(
        file_validator=file_validator,
        store=store,
        storage_dir=config["storage_dir"],
    )
    app.config["PAGE_SERVICE"] = page_service

    from .services.schema_service import SchemaService

    schema_path = os.path.join(PROJECT_ROOT, "app", "config", "schemas",
                               "medical_record.v1.yaml")
    schema_service = SchemaService(schema_path)
    app.config["SCHEMA_SERVICE"] = schema_service

    from .services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from .services.task_service import TaskService

    orchestrator = ProcessingOrchestrator(
        store=store,
        schema_validator=schema_service.build_validator(),
    )
    app.config["TASK_SERVICE"] = TaskService(
        store=store,
        orchestrator=orchestrator,
        schema_provider=schema_service.get_current,
    )

    from .services.review_service import ReviewService

    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=app.config["TASK_SERVICE"],
        schema_provider=schema_service.get_current,
    )

    app.logger.warning("算法模块未配置")

    from .routes.system import system_bp
    app.register_blueprint(system_bp)

    from .routes.capture_session import capture_session_bp
    from .routes.mobile import mobile_bp
    from .routes.task import task_bp
    from .routes.schema import schema_bp
    from .routes.maintenance import maintenance_bp
    app.register_blueprint(capture_session_bp)
    app.register_blueprint(mobile_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(schema_bp)
    app.register_blueprint(maintenance_bp)

    from .routes.review import review_bp
    app.register_blueprint(review_bp)

    from .services.export_service import ExportService

    app.config["EXPORT_SERVICE"] = ExportService(
        store=store,
        export_dir=config["export_dir"],
        task_service=app.config["TASK_SERVICE"],
        schema_provider=schema_service.get_current,
    )

    from .routes.export import export_bp
    app.register_blueprint(export_bp)

    return app
