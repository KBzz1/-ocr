"""后端 E2E 契约测试 — 覆盖采集、处理、审核主流程。"""
import io

from app.backend import create_backend_app
from app.backend.services.algorithm_ports.fixtures import (
    FixtureDocPort,
    FixtureFieldPort,
    FixtureImagePort,
)
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.tests.fixtures.images import JPEG_BYTES


def _write_config(tmp_path):
    """写入测试用 YAML 配置，所有路径指向 tmp_path。"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config = f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
  model_dir: "{tmp_path}/models"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
"""
    (config_dir / "default.yaml").write_text(config, encoding="utf-8")
    return config_dir


def _make_client(tmp_path, monkeypatch):
    """创建 Flask test client，所有路径隔离在 tmp_path 中。"""
    config_dir = _write_config(tmp_path)
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(str(config_dir))
    app.config["TESTING"] = True
    return app.test_client(), app


def _install_fixture_task_service(app, field_port=None, image_port=None, doc_port=None):
    """替换 app 的 TASK_SERVICE 和 REVIEW_SERVICE 使用 fixture 算法端口。"""
    store = app.config["CLEANUP_SERVICE"]._store if hasattr(app.config["CLEANUP_SERVICE"], "_store") else None
    # 从现有服务获取 store
    from app.backend.storage.json_store import JsonStore
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])

    schema_service = app.config["SCHEMA_SERVICE"]

    orchestrator = ProcessingOrchestrator(
        store=store,
        session_service=app.config["SESSION_SERVICE"],
        image_port=image_port or FixtureImagePort(),
        doc_port=doc_port or FixtureDocPort(),
        field_port=field_port or FixtureFieldPort(),
        schema_validator=schema_service.build_validator(),
    )
    task_service = TaskService(
        store=store,
        orchestrator=orchestrator,
        schema_provider=schema_service.get_current,
    )
    app.config["TASK_SERVICE"] = task_service
    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=task_service,
        schema_provider=schema_service.get_current,
    )


def _upload_page(client, session_id, image_bytes=JPEG_BYTES, filename="test.jpg",
                 image_width=1920, image_height=1080, quad_points=None):
    """上传一个图片页面，返回响应 JSON。"""
    data = {
        "image": (io.BytesIO(image_bytes), filename),
        "image_width": str(image_width),
        "image_height": str(image_height),
    }
    if quad_points is not None:
        data["quad_points"] = quad_points
    resp = client.post(
        f"/api/mobile/{session_id}/pages",
        data=data,
        content_type="multipart/form-data",
    )
    return resp


class TestFixtureClient:
    def test_fixture_client_starts_with_system_status(self, tmp_path, monkeypatch):
        client, _app = _make_client(tmp_path, monkeypatch)

        resp = client.get("/api/system/status")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"
