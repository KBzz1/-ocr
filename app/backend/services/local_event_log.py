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
ID_CARD_RE = re.compile(r"(?<!\d)\d{6}\d{8}\d{3}[\dXx](?!\d)")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
BASE64_RE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/]{40,}={0,2}")

ALLOWED_EVENTS = {
    "system_started",
    "config_default_used",
    "algorithm_module_not_configured",
    "session_created",
    "session_finished",
    "page_uploaded",
    "task_processing_started",
    "task_processing_failed",
    "task_ready_for_review",
    "review_field_saved",
    "review_confirmed",
    "export_succeeded",
    "export_failed",
}

EVENT_FIELDS = {
    "system_started": {"port", "lan_addresses_count"},
    "config_default_used": {"config_key"},
    "algorithm_module_not_configured": {"stage"},
    "session_created": {"session_id"},
    "session_finished": {"session_id", "task_id", "page_count"},
    "page_uploaded": {"session_id", "page_id", "image_width", "image_height"},
    "task_processing_started": {"task_id", "session_id"},
    "task_processing_failed": {"task_id", "session_id", "error_code", "stage", "reason"},
    "task_ready_for_review": {"task_id", "schema_version"},
    "review_field_saved": {"task_id", "field_key", "status"},
    "review_confirmed": {"task_id", "field_count"},
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
        if len(text) > 120:
            text = text[:80] + "...[truncated]"
        text = ID_CARD_RE.sub("[id_card]", text)
        text = PHONE_RE.sub("[phone]", text)
        text = BASE64_RE.sub("[base64]", text)
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

    def safe_write(self, event: str, level: str = "INFO", **payload) -> None:
        try:
            self.write(event, level=level, **payload)
        except Exception:
            return

    def _rotate_if_needed(self) -> None:
        if not os.path.exists(self.current_path) or os.path.getsize(self.current_path) < self.max_bytes:
            return
        for index in range(self.backup_count - 1, 0, -1):
            src = f"{self.current_path}.{index}"
            dst = f"{self.current_path}.{index + 1}"
            if os.path.exists(src):
                os.replace(src, dst)
        if self.backup_count > 0:
            os.replace(self.current_path, f"{self.current_path}.1")
        else:
            os.remove(self.current_path)
