import json
import os
import re

from app.backend.services.local_event_log import LocalEventLog, sanitize_log_payload


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestSanitizeLogPayload:
    def test_redacts_sensitive_keys_and_patterns(self):
        payload = {
            "task_id": "task-001",
            "ocr_text": "完整OCR文本不应进入日志",
            "merged_text": "完整病历原文不应进入日志",
            "model_output": {"field": "长模型输出"},
            "patient_id": "110101199001011234",
            "phone": "13812345678",
            "image_base64": "data:image/jpeg;base64," + "A" * 160,
            "reason": "x" * 200,
        }

        clean = sanitize_log_payload(payload)

        serialized = json.dumps(clean, ensure_ascii=False)
        assert clean["ocr_text"] == "[redacted]"
        assert clean["merged_text"] == "[redacted]"
        assert clean["model_output"] == "[redacted]"
        assert "110101199001011234" not in serialized
        assert "13812345678" not in serialized
        assert "data:image/jpeg;base64" not in serialized
        assert clean["reason"].endswith("...[truncated]")

    def test_limits_lists_dicts_and_complex_objects(self):
        clean = sanitize_log_payload(
            {
                "items": list(range(20)),
                "nested": {str(i): i for i in range(20)},
                "object": object(),
            }
        )

        assert len(clean["items"]) == 10
        assert clean["items"][-1] == "[truncated]"
        assert len(clean["nested"]) <= 11
        assert clean["object"] == "[object]"

    def test_redacts_base64_like_reason_before_writing_log(self):
        clean = sanitize_log_payload({"reason": "A" * 60 + "+" + "/" + "B" * 60 + "=="})

        assert clean["reason"] == "[base64]"


class TestLocalEventLog:
    def test_writes_single_json_line_with_required_fields(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write("task_processing_started", task_id="task-001")

        records = read_jsonl(log.current_path)
        assert len(records) == 1
        assert records[0]["event"] == "task_processing_started"
        assert records[0]["level"] == "INFO"
        assert records[0]["task_id"] == "task-001"
        assert "ts" in records[0]

    def test_writes_ocr_runner_diagnostic_events_without_ocr_text(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write(
            "ocr_runner_started",
            task_id="task-001",
            backend="python",
            page_count=2,
            timeout_seconds=30,
            work_dir="/tmp/ocr-runs/task-001",
            run_log_path="/tmp/ocr-runs/task-001/runner-progress.jsonl",
            command="python paddleocr_vl_batch_runner.py",
            merged_text="完整 OCR 文本不应进入日志",
        )
        log.write(
            "ocr_runner_finished",
            task_id="task-001",
            backend="python",
            elapsed_ms=1200,
            exit_code=0,
            output_exists=True,
            output_bytes=128,
            stdout_tail="done",
            stderr_tail="",
        )

        records = read_jsonl(log.current_path)
        assert [record["event"] for record in records] == ["ocr_runner_started", "ocr_runner_finished"]
        assert records[0]["page_count"] == 2
        assert "merged_text" not in records[0]

    def test_rejects_unknown_event_name(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        try:
            log.write("unknown_event", task_id="task-001")
        except ValueError as exc:
            assert "unknown_event" in str(exc)
        else:
            raise AssertionError("unknown_event should be rejected")

    def test_strips_disallowed_fields_and_sensitive_values(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write(
            "task_processing_failed",
            task_id="task-001",
            error_code="ALGORITHM_MODULE_FAILED",
            stage="field_extraction",
            reason="身份证110101199001011234 手机13812345678 " + "x" * 200,
            merged_text="完整病历原文",
        )

        content = open(log.current_path, encoding="utf-8").read()
        assert "110101199001011234" not in content
        assert "13812345678" not in content
        assert "完整病历原文" not in content
        record = read_jsonl(log.current_path)[0]
        assert record["reason"].endswith("...[truncated]")
        assert "merged_text" not in record

    def test_rotates_when_file_exceeds_max_bytes(self, tmp_path):
        log = LocalEventLog(str(tmp_path), max_bytes=300, backup_count=2)
        for i in range(50):
            log.write("task_processing_started", task_id=f"task-{i}")

        backups = [name for name in os.listdir(tmp_path) if re.match(r"backend-events\.jsonl\.\d+", name)]
        assert backups
