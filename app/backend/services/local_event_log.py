import json
import os
import re
from datetime import datetime, timezone

SENSITIVE_KEYS = {
    "text",
    "plain_text",
    "ocr_text",
    "merged_text",
    "model_output",
    "llm_output",
    "base64",
    "image_base64",
}
LONG_DIAGNOSTIC_KEYS = {"stdout_tail", "stderr_tail", "command"}
ID_CARD_RE = re.compile(r"(?<!\d)\d{6}\d{8}\d{3}[\dXx](?!\d)")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
BASE64_RE = re.compile(
    r"data:image/[^;]+;base64,[A-Za-z0-9+/]{40,}={0,2}"
    r"|(?=[A-Za-z0-9+/=]{100,})(?=[A-Za-z0-9+/=]*[+/=])[A-Za-z0-9+/]{100,}={0,2}"
)

ALLOWED_EVENTS = {
    "system_started",
    "config_default_used",
    "algorithm_module_not_configured",
    "page_uploaded",
    "task_processing_started",
    "processing_stage_started",
    "processing_stage_finished",
    "ocr_runner_started",
    "ocr_runner_finished",
    "ocr_runner_failed",
    "ocr_runner_timeout",
    "task_processing_failed",
    "task_review_ready",
    "review_field_saved",
    "review_completed",
    "export_succeeded",
    "export_failed",
}

EVENT_FIELDS = {
    "system_started": {"port", "lan_addresses_count", "public_base_url"},
    "config_default_used": {"config_key"},
    "algorithm_module_not_configured": {"stage"},
    "page_uploaded": {"task_id", "page_id", "image_width", "image_height"},
    "task_processing_started": {"task_id"},
    "processing_stage_started": {"task_id", "stage", "page_count"},
    "processing_stage_finished": {"task_id", "stage", "page_count", "elapsed_ms", "status"},
    "ocr_runner_started": {
        "task_id",
        "backend",
        "page_count",
        "timeout_seconds",
        "work_dir",
        "run_log_path",
        "container_name",
        "command",
        "python_executable",
        "script_path",
        "cache_dir",
        "device",
        "max_new_tokens",
        "max_pixels",
        "input_files",
    },
    "ocr_runner_finished": {
        "task_id",
        "backend",
        "elapsed_ms",
        "exit_code",
        "output_exists",
        "output_bytes",
        "stdout_tail",
        "stderr_tail",
    },
    "ocr_runner_failed": {
        "task_id",
        "backend",
        "elapsed_ms",
        "exit_code",
        "output_exists",
        "output_bytes",
        "stdout_tail",
        "stderr_tail",
    },
    "ocr_runner_timeout": {
        "task_id",
        "backend",
        "timeout_seconds",
        "work_dir",
        "run_log_path",
        "container_name",
        "stdout_tail",
        "stderr_tail",
    },
    "task_processing_failed": {"task_id", "error_code", "stage", "reason"},
    "task_review_ready": {"task_id", "schema_version"},
    "review_field_saved": {"task_id", "field_key", "status"},
    "review_completed": {"task_id", "field_count"},
    "export_succeeded": {"task_id", "format", "relative_path"},
    "export_failed": {"task_id", "format", "error_code"},
}


def sanitize_log_payload(payload: dict) -> dict:
    return {key: _sanitize_value(key, value) for key, value in payload.items()}


def _sanitize_value(key: str, value):
    lowered = key.lower()
    if lowered in SENSITIVE_KEYS or any(token in lowered for token in ("ocr_text", "merged_text", "model_output", "base64")):
        return "[redacted]"
    if isinstance(value, str):
        text = value
        text = ID_CARD_RE.sub("[id_card]", text)
        text = PHONE_RE.sub("[phone]", text)
        text = BASE64_RE.sub("[base64]", text)
        limit = 2000 if lowered in LONG_DIAGNOSTIC_KEYS else 120
        if len(text) > limit:
            text = text[:limit] + "...[truncated]"
        return text
    if isinstance(value, bool) or isinstance(value, int) or isinstance(value, float) or value is None:
        return value
    if isinstance(value, list):
        items = [_sanitize_value(key, item) for item in value[:9]]
        if len(value) > 9:
            items.append("[truncated]")
        return items
    if isinstance(value, dict):
        result = {}
        for index, (child_key, child_value) in enumerate(value.items()):
            if index >= 10:
                result["[truncated]"] = True
                break
            result[child_key] = _sanitize_value(child_key, child_value)
        return result
    return f"[{type(value).__name__}]"


class LocalEventLog:
    def __init__(self, log_dir: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        self.log_dir = os.path.abspath(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        os.makedirs(self.log_dir, exist_ok=True)
        self.current_path = os.path.join(self.log_dir, "backend-events.jsonl")
        self._write_count = 0

    def write(self, event: str, level: str = "INFO", **payload) -> None:
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"unknown event: {event}")
        self._rotate_if_needed()
        allowed = EVENT_FIELDS[event]
        clean = sanitize_log_payload({k: v for k, v in payload.items() if k in allowed and v is not None})
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **clean,
        }
        with open(self.current_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._write_count += 1

    def safe_write(self, event: str, level: str = "INFO", **payload) -> None:
        try:
            self.write(event, level=level, **payload)
        except Exception:
            return

    def _rotate_if_needed(self) -> None:
        if self._write_count % 10 != 0:
            return
        try:
            size = os.path.getsize(self.current_path)
        except OSError:
            return
        if size < self.max_bytes:
            return
        for index in range(self.backup_count - 1, 0, -1):
            src = f"{self.current_path}.{index}"
            dst = f"{self.current_path}.{index + 1}"
            try:
                os.replace(src, dst)
            except OSError:
                pass
        if self.backup_count > 0:
            try:
                os.replace(self.current_path, f"{self.current_path}.1")
            except OSError:
                pass
        else:
            try:
                os.remove(self.current_path)
            except OSError:
                pass
