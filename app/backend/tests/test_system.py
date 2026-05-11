import json
import pytest
from flask import Flask
from app.backend.routes.system import system_bp


def _make_app(config_overrides=None):
    """为测试构建最小 Flask app，只挂载 system_bp。"""
    overrides = config_overrides or {}
    app = Flask(__name__)
    app.config["BACKEND_CONFIG"] = {
        "version": "0.1.0",
        "bind_host": "0.0.0.0",
        "port": 8080,
        "data_dir": "/tmp/test_data",
        "log_dir": "/tmp/test_logs",
        "export_dir": "/tmp/test_exports",
        "model_dir": "/tmp/test_models",
        "storage_dir": "/tmp/test_data",
        "local_host": "127.0.0.1",
        **overrides,
    }
    app.config["STARTED_AT"] = "2026-05-11T12:00:00+00:00"
    app.config["LAN_ADDRESSES"] = overrides.get("LAN_ADDRESSES", [])
    from app.backend.errors import register_error_handlers
    register_error_handlers(app)
    app.register_blueprint(system_bp)
    return app


class TestSystemStatus:
    def test_returns_200(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

    def test_response_structure(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)
        assert data["success"] is True
        assert "data" in data
        assert data["data"]["status"] == "running"
        assert data["data"]["version"] == "0.1.0"
        assert "started_at" in data["data"]
        assert "lan_addresses" in data["data"]

    def test_content_type_is_json(self):
        client = _make_app().test_client()
        resp = client.get("/api/system/status")
        assert resp.content_type == "application/json"

    def test_lan_addresses_excludes_localhost(self):
        """127.0.0.1 不应作为手机端可用的默认地址。"""
        overrides = {
            "LAN_ADDRESSES": [
                "127.0.0.1:8080",
                "192.168.1.5:8080",
                "10.0.0.8:8080",
            ]
        }
        client = _make_app(config_overrides=overrides).test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)
        assert data["data"]["lan_addresses"] == [
            "192.168.1.5:8080",
            "10.0.0.8:8080",
        ]


class TestErrorHandling:
    def test_404_returns_json_not_html(self):
        app = _make_app()
        client = app.test_client()
        resp = client.get("/api/nonexistent")
        data = json.loads(resp.data)
        assert "error" in data
        assert data["error"]["code"] == "HTTP_ERROR"
        assert resp.content_type == "application/json"

    def test_500_returns_json_without_stacktrace(self):
        app = Flask(__name__)
        app.config["BACKEND_CONFIG"] = {
            "version": "0.1.0",
            "bind_host": "0.0.0.0",
            "port": 8080,
        }
        app.config["STARTED_AT"] = "2026-05-11T12:00:00+00:00"
        app.config["LAN_ADDRESSES"] = []

        @app.route("/api/will-crash")
        def will_crash():
            raise RuntimeError("boom")

        from app.backend.errors import register_error_handlers
        register_error_handlers(app)

        client = app.test_client()
        resp = client.get("/api/will-crash")
        data = json.loads(resp.data)
        assert resp.status_code == 500
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "RuntimeError" not in json.dumps(data)
        assert "traceback" not in json.dumps(data)
        assert "stack" not in json.dumps(data)


class TestLanAddressSelection:
    def test_get_lan_addresses_excludes_loopback_and_deduplicates(self, monkeypatch):
        from app.backend import _get_lan_addresses
        import socket

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda hostname, port, family: [
                (family, None, None, "", ("127.0.0.1", 0)),
                (family, None, None, "", ("192.168.1.20", 0)),
                (family, None, None, "", ("192.168.1.20", 0)),
                (family, None, None, "", ("10.0.0.8", 0)),
            ],
        )

        assert _get_lan_addresses(8080) == ["192.168.1.20:8080", "10.0.0.8:8080"]

    def test_get_lan_addresses_returns_empty_when_lookup_fails(self, monkeypatch):
        from app.backend import _get_lan_addresses
        import socket

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")

        def raise_os_error(hostname, port, family):
            raise OSError("network unavailable")

        monkeypatch.setattr(socket, "getaddrinfo", raise_os_error)
        assert _get_lan_addresses(8080) == []


class TestCreateBackendApp:
    def test_create_backend_app_registers_system_route(self, tmp_path, monkeypatch):
        import socket
        from app.backend import create_backend_app

        monkeypatch.setattr(socket, "gethostname", lambda: "doctor-workstation")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda hostname, port, family: [
                (family, None, None, "", ("192.168.1.20", 0)),
            ],
        )

        app = create_backend_app(str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/system/status")
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["data"]["lan_addresses"] == ["192.168.1.20:8080"]
