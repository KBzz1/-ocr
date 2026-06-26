"""Tests for QwenBatchAlgorithmPort -- adapter between backend and Qwen batch engine."""

import json
from pathlib import Path

from app.backend.services.algorithm_ports.qwen_batch_adapter import QwenBatchAlgorithmPort


def test_qwen_batch_adapter_creates_manifest_and_reads_result(tmp_path):
    job_root = tmp_path / "jobs"
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        "version: qwen_batch_admission_record.v1\n"
        "document_type: qwen_batch_admission_record\n"
        "field_groups: []\n",
        encoding="utf-8",
    )
    source = tmp_path / "page.jpg"
    source.write_bytes(b"image")

    def fake_runner(job_dir: str, schema_path: str, timeout_seconds: int):
        job = Path(job_dir)
        result = {
            "job_id": "task_001",
            "status": "success",
            "engine": {"name": "qwen_batch_engine"},
            "document_result": {
                "merged_text": "主诉：咳嗽",
                "pages": [
                    {
                        "page_id": "p1",
                        "page_no": 1,
                        "status": "success",
                        "text": "主诉：咳嗽",
                    }
                ],
            },
            "review_fields": [
                {
                    "field_key": "chief_complaint",
                    "original_value": "咳嗽",
                    "evidence": [
                        {
                            "id": "s1-s1",
                            "text": "主诉：咳嗽",
                            "start_offset": 0,
                            "end_offset": 5,
                        }
                    ],
                    "extraction_status": "extracted",
                    "verification_status": "not_checked",
                    "quality_flags": [],
                    "ocr_correction": {
                        "applied": False,
                        "raw": "",
                        "normalized": "",
                        "reason": "",
                    },
                }
            ],
            "warnings": [],
        }
        (job / "result.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        return 0

    port = QwenBatchAlgorithmPort(
        job_root=str(job_root),
        schema_path=str(schema_path),
        runner=fake_runner,
        timeout_seconds=30,
    )

    result = port.run(
        {
            "task_id": "task_001",
            "images": [
                {"page_id": "p1", "page_no": 1, "original_image_path": str(source)}
            ],
            "schema_version": "qwen_batch_admission_record.v1",
        }
    )

    manifest = json.loads(
        (job_root / "task_001" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["job_id"] == "task_001"
    assert manifest["input_files"][0]["filename"] == "page_001.jpg"
    assert (
        job_root / "task_001" / "input" / "page_001.jpg"
    ).read_bytes() == b"image"
    assert result["status"] == "success"
    assert result["review_fields"][0]["field_key"] == "chief_complaint"


def test_qwen_batch_adapter_returns_failed_result_when_runner_fails(tmp_path):
    source = tmp_path / "page.jpg"
    source.write_bytes(b"image")
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        "version: qwen_batch_admission_record.v1\n", encoding="utf-8"
    )

    def failing_runner(job_dir: str, schema_path: str, timeout_seconds: int):
        Path(job_dir, "error.json").write_text(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "upstream_failed",
                    "message": "runner failed",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 1

    port = QwenBatchAlgorithmPort(
        job_root=str(tmp_path / "jobs"),
        schema_path=str(schema_path),
        runner=failing_runner,
        timeout_seconds=30,
    )

    result = port.run(
        {
            "task_id": "task_001",
            "images": [
                {"page_id": "p1", "page_no": 1, "original_image_path": str(source)}
            ],
            "schema_version": "qwen_batch_admission_record.v1",
        }
    )

    assert result["status"] == "failed"
    assert result["error"]["reason"] == "upstream_failed"
