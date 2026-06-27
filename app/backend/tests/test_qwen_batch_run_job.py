import json
from pathlib import Path

from algorithms.qwen_batch_engine.adapter.run_job import normalize_upstream_output, run_job


def test_qwen_batch_run_job_normalizes_upstream_outputs(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v1.yaml").resolve()
    merged_text = "主诉：咳嗽。\n精神睡眠食欲可。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "主诉": {"值": "咳嗽", "证据": "主诉：咳嗽。"},
                "现病史": {
                    "精神睡眠食欲": {"状态": "正常", "证据": "精神睡眠食欲可。"}
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["schema_version"] == "qwen_batch_admission_record.v1"
    assert result["document_result"]["merged_text"] == merged_text
    assert len(result["review_fields"]) == 51
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "咳嗽"
    assert fields["chief_complaint"]["evidence"][0]["start_offset"] == 0
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "正常"
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "normal"
    assert fields["hpi_stool"]["extraction_status"] == "not_found"


def test_qwen_batch_run_job_normalizes_raw_compact_response(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v1.yaml").resolve()
    merged_text = "主诉：反复咳嗽。患者精神、食欲欠佳，睡眠一般。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    raw_response = {
        "主诉": {"v": "反复咳嗽", "p": ["<s2>", "<s2>"]},
        "现病史": {
            "精神睡眠食欲": {"s": 1, "p": ["<s3>", "<s3>"]},
            "大便情况": {"s": 0, "p": ["<s4>", "<s4>"]},
        },
    }
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {"_raw_response": json.dumps(raw_response, ensure_ascii=False), "_parse_error": True},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "反复咳嗽"
    assert fields["chief_complaint"]["evidence"][0]["text"] == "反复咳嗽。"
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "异常"
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "abnormal"
    assert fields["hpi_mental_sleep_appetite"]["evidence"][0]["text"] == "患者精神、食欲欠佳，"
    assert fields["hpi_stool"]["original_value"] == "正常"
    assert fields["hpi_stool"]["qwen_status"] == "normal"


def test_qwen_batch_run_job_falls_back_to_local_raw_leaf_parse(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v1.yaml").resolve()
    (upstream_group / "merged_ocr.txt").write_text("主诉：反复咳嗽。", encoding="utf-8")
    malformed_raw = (
        '{"主诉":{"v":"反复咳嗽","p":["<s1>","<s1>"]}},'
        '"个人史":{"吸烟史":{"s":0,"p":["<s2>","<s2>"]}}'
    )
    (upstream_group / "merged_structured.json").write_text(
        json.dumps({"_raw_response": malformed_raw, "_parse_error": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "反复咳嗽"
    assert fields["personal_smoking"]["original_value"] == "正常"


def test_qwen_batch_run_job_normalize_only_writes_error_when_upstream_missing(tmp_path):
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v1.yaml").resolve()

    exit_code = run_job(
        job_dir=str(tmp_path / "job"),
        schema_path=str(schema_path),
        normalize_only=True,
    )

    assert exit_code == 1
    error = json.loads((tmp_path / "job" / "error.json").read_text(encoding="utf-8"))
    assert error["reason"] == "normalize_failed"
