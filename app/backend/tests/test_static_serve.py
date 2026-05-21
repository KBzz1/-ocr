"""NW-002 ~ NW-008: 静态文件托管 + SPA fallback 测试。"""

import pytest


@pytest.fixture
def static_app(tmp_path, monkeypatch):
    """创建带 static_dir 的测试 app，包含模拟 dist 目录。"""
    from app.backend import create_backend_app

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text(
        "<!DOCTYPE html><html><head><title>工作台</title></head><body>App</body></html>",
        encoding="utf-8",
    )
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('hello');", encoding="utf-8")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
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
  static_dir: "{dist_dir}"
sessions:
  capture_session_ttl_minutes: 30
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def static_client(static_app):
    return static_app.test_client()


class TestStaticServe:
    """BE-NW-002 ~ BE-NW-008。"""

    def test_root_returns_html_not_json(self, static_client):
        """BE-NW-002: GET / 返回 HTML，Content-Type 为 text/html。"""
        resp = static_client.get("/")

        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"<!DOCTYPE html>" in resp.data

    def test_mobile_upload_returns_spa(self, static_client):
        """BE-NW-003: GET /mobile/upload/{task_id} 返回 SPA index.html。"""
        resp = static_client.get("/mobile/upload/task_001")

        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"<!DOCTYPE html>" in resp.data

    def test_spa_index_is_not_cached(self, static_client):
        """手机扫码入口不能缓存旧 index，否则会继续加载旧 UI 资源。"""
        resp = static_client.get("/mobile/upload/task_001")

        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "no-store, max-age=0"

    def test_api_status_not_eaten_by_fallback(self, static_client):
        """BE-NW-004: GET /api/system/status 不被 fallback 吃掉。"""
        resp = static_client.get("/api/system/status")

        assert resp.status_code == 200
        assert resp.is_json
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"

    def test_api_not_exists_returns_json_404(self, static_client):
        """BE-NW-005: GET /api/not-exists 返回 API JSON 404。"""
        resp = static_client.get("/api/not-exists")

        assert resp.status_code == 404
        assert resp.is_json
        data = resp.get_json()
        assert data["error"]["code"] == "REQUEST_NOT_FOUND"

    def test_missing_asset_returns_404_not_html(self, static_client):
        """BE-NW-006: GET /assets/missing.js 返回 404，不返回 index.html。"""
        resp = static_client.get("/assets/missing.js")

        assert resp.status_code == 404
        assert b"<!DOCTYPE html>" not in resp.data

    def test_existing_asset_returns_file(self, static_client):
        """BE-NW-007: GET /assets/app.js 存在时返回静态文件。"""
        resp = static_client.get("/assets/app.js")

        assert resp.status_code == 200
        assert b"console.log" in resp.data

    def test_root_without_dist_returns_json_404(self, tmp_path, monkeypatch):
        """BE-NW-008: GET / 在 dist/index.html 缺失时返回统一 JSON 404。"""
        from app.backend import create_backend_app

        empty_dist = tmp_path / "empty_dist"
        empty_dist.mkdir()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default.yaml").write_text(
            f"""
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
  static_dir: "{empty_dist}"
sessions:
  capture_session_ttl_minutes: 30
""",
            encoding="utf-8",
        )

        monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
        app = create_backend_app(config_dir=str(config_dir))
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/")

        assert resp.status_code == 404
        assert resp.is_json
        data = resp.get_json()
        assert data["error"]["code"] == "REQUEST_NOT_FOUND"
