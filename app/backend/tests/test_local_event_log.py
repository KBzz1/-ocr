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
    def test_writes_qwen_vllm_ocr_events_without_text_or_base64(self, tmp_path):
        """`backend=qwen_vision_vllm` 的 ocr_vlm_started/finished 事件必须仅含诊断字段，不含 OCR 文本或 base64。"""
        log = LocalEventLog(str(tmp_path))
        log.write(
            "ocr_vlm_started",
            task_id="task-001",
            backend="qwen_vision_vllm",
            server_url="http://qwen-vision-vllm-server:8000/v1",
            model="Qwen3.5-4B-AWQ-4bit",
            page_count=3,
            timeout_seconds=240,
            temperature=0.0,
            max_tokens=4096,
            top_p=1.0,
            input_files=[
                {"page_id": "p1", "page_no": 1, "filename": "p1.jpg", "bytes": 1024, "exists": True},
            ],
        )
        log.write(
            "ocr_vlm_finished",
            task_id="task-001",
            backend="qwen_vision_vllm",
            elapsed_ms=1234,
            exit_code=0,
            output_exists=True,
            output_bytes=2048,
            failed_page_count=0,
        )

        records = read_jsonl(log.current_path)
        started, finished = records[0], records[1]
        assert started["backend"] == "qwen_vision_vllm"
        assert started["server_url"] == "http://qwen-vision-vllm-server:8000/v1"
        assert started["model"] == "Qwen3.5-4B-AWQ-4bit"
        assert started["page_count"] == 3
        assert started["timeout_seconds"] == 240
        assert started["temperature"] == 0.0
        assert started["max_tokens"] == 4096
        assert started["top_p"] == 1.0
        # 隐私：不得包含 OCR 文本或图片 base64
        assert "ocr_text" not in started
        assert "merged_text" not in started
        assert "image_base64" not in started
        assert finished["failed_page_count"] == 0
        assert "elapsed_ms" in finished

    def test_writes_qwen_vllm_extraction_events_without_prompt_or_output(self, tmp_path):
        """新增 llm_extraction_started/finished 事件仅含诊断字段，不含 prompt 或模型输出。"""
        log = LocalEventLog(str(tmp_path))
        log.write(
            "llm_extraction_started",
            task_id="task-001",
            backend="qwen_vision_vllm",
            server_url="http://qwen-vision-vllm-server:8000/v1",
            model="Qwen3.5-4B-AWQ-4bit",
            schema_version="admission_record_structured_fields.v1",
            field_count=61,
            evidence_unit_count=12,
            timeout_seconds=360,
            temperature=0.0,
            max_tokens=8192,
        )
        log.write(
            "llm_extraction_finished",
            task_id="task-001",
            backend="qwen_vision_vllm",
            schema_version="admission_record_structured_fields.v1",
            field_count=61,
            elapsed_ms=5678,
            exit_code=0,
        )

        records = read_jsonl(log.current_path)
        started, finished = records[0], records[1]
        assert started["backend"] == "qwen_vision_vllm"
        assert started["schema_version"] == "admission_record_structured_fields.v1"
        assert started["field_count"] == 61
        assert started["evidence_unit_count"] == 12
        for forbidden in ("prompt", "model_output", "evidence", "image_base64", "patient_name"):
            assert forbidden not in started
            assert forbidden not in finished
        assert finished["elapsed_ms"] == 5678
        assert finished["exit_code"] == 0

    def test_qwen_ocr_event_drops_disallowed_keys_via_allowlist(self, tmp_path):
        """allowlist 是权威：尝试传入敏感键不会写盘。"""
        log = LocalEventLog(str(tmp_path))
        log.write(
            "ocr_vlm_started",
            task_id="task-001",
            backend="qwen_vision_vllm",
            server_url="http://qwen-vision-vllm-server:8000/v1",
            model="Qwen3.5-4B-AWQ-4bit",
            page_count=1,
            timeout_seconds=240,
            temperature=0.0,
            max_tokens=4096,
            top_p=1.0,
            input_files=[],
            ocr_text="完整OCR文本",
            image_base64="data:image/jpeg;base64," + "A" * 100,
            patient_name="张三",
        )

        record = read_jsonl(log.current_path)[0]
        assert "ocr_text" not in record
        assert "image_base64" not in record
        assert "patient_name" not in record

    def test_writes_single_json_line_with_required_fields(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write("task_processing_started", task_id="task-001")

        records = read_jsonl(log.current_path)
        assert len(records) == 1
        assert records[0]["event"] == "task_processing_started"
        assert records[0]["level"] == "INFO"
        assert records[0]["task_id"] == "task-001"
        assert "ts" in records[0]

    def test_writes_system_started_public_base_url(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write(
            "system_started",
            port=8081,
            lan_addresses_count=1,
            public_base_url="http://172.20.10.5:8081",
        )

        record = read_jsonl(log.current_path)[0]
        assert record["public_base_url"] == "http://172.20.10.5:8081"

    def test_writes_ocr_vlm_diagnostic_events_without_ocr_text(self, tmp_path):
        log = LocalEventLog(str(tmp_path))

        log.write(
            "ocr_vlm_started",
            task_id="task-001",
            backend="vlm_server",
            page_count=2,
            timeout_seconds=30,
            server_url="http://qwen-vision-vllm-server:8000/v1",
            merged_text="完整 OCR 文本不应进入日志",
        )
        log.write(
            "ocr_vlm_finished",
            task_id="task-001",
            backend="vlm_server",
            elapsed_ms=1200,
            exit_code=0,
            output_exists=True,
            output_bytes=128,
        )

        records = read_jsonl(log.current_path)
        assert [record["event"] for record in records] == ["ocr_vlm_started", "ocr_vlm_finished"]
        assert records[0]["page_count"] == 2
        assert "merged_text" not in records[0]

    def test_preserves_ocr_vlm_error_reason_for_diagnostics(self, tmp_path):
        log = LocalEventLog(str(tmp_path))
        reason = "OCR 服务超时（> 240 秒）"

        log.write(
            "ocr_vlm_finished",
            task_id="task-001",
            backend="vlm_server",
            exit_code=1,
            output_exists=False,
            output_bytes=0,
            reason=reason,
        )

        record = read_jsonl(log.current_path)[0]
        assert record["reason"] == reason

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

    def test_allows_gpu_stage_events(self, tmp_path):
        from app.backend.services.local_event_log import LocalEventLog

        log = LocalEventLog(str(tmp_path))
        log.write("gpu_stage_waiting", task_id="task-001", stage="document_parsing")
        log.write("gpu_stage_started", task_id="task-001", stage="document_parsing", wait_ms=3)
        log.write("gpu_stage_finished", task_id="task-001", stage="document_parsing", elapsed_ms=5, status="success")

        content = (tmp_path / "backend-events.jsonl").read_text(encoding="utf-8")
        assert "gpu_stage_waiting" in content
        assert "gpu_stage_started" in content
        assert "gpu_stage_finished" in content
