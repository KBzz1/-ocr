import os

from ..config import PROJECT_ROOT


class OfflineCheckService:
    def __init__(self, config: dict):
        self._config = config

    def run(self) -> dict:
        schema_file = self._config.get(
            "schema_file",
            os.path.join(PROJECT_ROOT, "app", "config", "schemas", "medical_record.v1.yaml"),
        )
        model_dir = self._config["model_dir"]
        checks = [
            self._ensure_dir("storage_dir", self._config["storage_dir"], critical=True),
            self._ensure_dir("exports_dir", self._config["export_dir"], critical=True),
            self._ensure_dir("logs_dir", self._config["log_dir"], critical=True),
            self._check_file("schema_file", schema_file, critical=True),
            self._check_dir_exists("embedded_python", os.path.join(PROJECT_ROOT, "runtime", "python"), critical=False),
            self._check_dir_exists("ppstructure_models", os.path.join(model_dir, "ppstructure"), critical=False),
            self._check_dir_exists("llm_models", os.path.join(model_dir, "llm"), critical=False),
        ]
        if any(item["status"] == "failed" for item in checks):
            status = "failed"
        elif any(item["status"] == "warning" for item in checks):
            status = "warning"
        else:
            status = "ok"
        return {"status": status, "checks": checks}

    def _ensure_dir(self, key: str, path: str, critical: bool) -> dict:
        try:
            os.makedirs(path, exist_ok=True)
            return {"key": key, "status": "ok", "path": self._display(path)}
        except OSError:
            return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _check_file(self, key: str, path: str, critical: bool) -> dict:
        if os.path.isfile(path):
            return {"key": key, "status": "ok", "path": self._display(path)}
        return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _check_dir_exists(self, key: str, path: str, critical: bool) -> dict:
        if os.path.isdir(path) and os.listdir(path):
            return {"key": key, "status": "ok", "path": self._display(path)}
        return {"key": key, "status": "failed" if critical else "warning", "path": self._display(path)}

    def _display(self, path: str) -> str:
        try:
            return os.path.relpath(path, PROJECT_ROOT)
        except ValueError:
            return os.path.basename(path)
