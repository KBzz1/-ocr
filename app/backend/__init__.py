# app/backend/__init__.py
import logging
import os
import socket
from datetime import datetime, timezone
from ipaddress import ip_address

from flask import Flask, request, send_file, send_from_directory
from werkzeug.exceptions import NotFound
from werkzeug.utils import safe_join

from .config import PROJECT_ROOT, load_config
from .errors import register_error_handlers
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


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

    def _send_spa_index(index_path: str):
        response = send_file(index_path)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

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
            return _send_spa_index(index_path)

        return error_response(AppError(ErrorCode.REQUEST_NOT_FOUND))


def create_backend_app(config_dir: str | None = None) -> Flask:
    config = load_config(config_dir)

    setup_logging(config["log_dir"])
    logger.info("日志系统已初始化: 热日志 backend.log / 冷日志 debug.log access.log")

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
        public_base_url=config.get("public_base_url"),
    )
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
                               "copd_admission_record.v1.yaml")
    schema_service = SchemaService(schema_path)
    app.config["SCHEMA_SERVICE"] = schema_service

    from .services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from .services.task_service import TaskService

    image_port = None
    doc_port = None
    if config.get("enable_local_ocr"):
        from .services.algorithm_ports.image_processing import OriginalImagePassthroughPort
        from .services.algorithm_ports.local_paddleocr import LocalPaddleOCRDocumentPort

        image_port = OriginalImagePassthroughPort()
        ocr_work_root = config.get("local_ocr_work_root") or os.path.join(config["storage_dir"], "ocr_runs")
        doc_port = LocalPaddleOCRDocumentPort(
            python_executable=config["local_ocr_python_executable"],
            script_path=config["local_ocr_script_path"],
            work_root=ocr_work_root,
            cache_dir=os.path.join(config["model_dir"], "ppstructure", "paddlex_cache"),
            device=config.get("local_ocr_device"),
            max_new_tokens=config.get("local_ocr_max_new_tokens", 1024),
            max_pixels=config.get("local_ocr_max_pixels"),
            timeout_seconds=config["local_ocr_timeout_seconds"],
            event_logger=event_log.safe_write,
        )

    field_port = None
    if config.get("enable_copd_extractor"):
        from .services.copd_extraction.port import build_default_copd_field_port
        field_port = build_default_copd_field_port(config, schema_service.get_field_order)

    from .services.copd_extraction.prompts import COPD_EXTRACTION_PROMPT_VERSION
    from .services.document_profiles import DocumentProfile, DocumentProfileRegistry

    document_profile_registry = DocumentProfileRegistry(
        store=store,
        profiles=[
            DocumentProfile(
                document_type="copd_admission_record",
                label="入院记录",
                schema=schema_service.get_current(),
                prompt_version=COPD_EXTRACTION_PROMPT_VERSION,
                field_port=field_port,
                quality_rule_profile="copd_admission_record",
            )
        ],
        default_document_type="copd_admission_record",
    )
    app.config["DOCUMENT_PROFILE_REGISTRY"] = document_profile_registry

    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=image_port,
        doc_port=doc_port,
        field_port=field_port,
        field_port_registry={"copd_admission_record": field_port},
        schema_validator=schema_service.build_validator(),
    )
    from threading import Lock

    processing_lock = Lock()

    def run_processing_background(run):
        from threading import Thread

        def target():
            with app.app_context():
                with processing_lock:
                    run()

        Thread(target=target, daemon=True).start()

    app.config["TASK_SERVICE"] = TaskService(
        store=store,
        orchestrator=orchestrator,
        schema_provider=schema_service.get_current,
        background_runner=run_processing_background,
        document_profiles=document_profile_registry,
    )

    from .services.review_service import ReviewService

    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=app.config["TASK_SERVICE"],
        schema_provider=schema_service.get_current,
    )

    from .services.copd_extraction.prompts import COPD_EXTRACTION_PROMPT_VERSION
    from .services.reextraction_service import ReextractionService

    app.config["REEXTRACTION_SERVICE"] = ReextractionService(
        store=store,
        task_service=app.config["TASK_SERVICE"],
        field_port=field_port,
        schema_provider=schema_service.get_current,
        schema_validator=schema_service.build_validator(),
        prompt_version_provider=lambda: COPD_EXTRACTION_PROMPT_VERSION,
        document_profiles=document_profile_registry,
    )

    if image_port is None or doc_port is None or field_port is None:
        missing_stages = []
        if image_port is None:
            missing_stages.append("image_processing")
        if doc_port is None:
            missing_stages.append("document_parsing")
        if field_port is None:
            missing_stages.append("field_extraction")
        event_log.safe_write(
            "algorithm_module_not_configured",
            level="WARNING",
            stages=missing_stages,
        )
        app.logger.warning("算法模块未配置: %s", ",".join(missing_stages))

    from .routes.system import system_bp
    app.register_blueprint(system_bp)

    from .routes.mobile import mobile_bp
    from .routes.task import task_bp
    from .routes.schema import schema_bp
    from .routes.maintenance import maintenance_bp
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
