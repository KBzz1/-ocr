import json
from pathlib import Path

from algorithms.qwen_batch_engine.adapter.run_job import normalize_upstream_output, run_job
from algorithms.qwen_batch_engine.upstream.scripts.process import _clean_ocr_text_for_extraction


def test_qwen_batch_run_job_normalizes_upstream_outputs(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "主诉：咳嗽。\n精神可。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "主诉": {"值": "咳嗽", "证据": "主诉：咳嗽。"},
                "现病史": {"精神睡眠食欲": {"状态": "正常", "证据": "精神可。"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["schema_version"] == "qwen_batch_admission_record.v2"
    assert result["document_result"]["merged_text"] == merged_text
    assert result["document_result"]["anchors"][0] == {
        "id": "<s1>",
        "text": "主诉：",
        "start_offset": 0,
        "end_offset": 3,
    }
    anchors = json.loads((job_dir / "anchors.json").read_text(encoding="utf-8"))
    assert anchors == result["document_result"]["anchors"]
    assert len(result["review_fields"]) == 51
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "咳嗽"
    assert fields["chief_complaint"]["evidence"][0]["start_offset"] == 0
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "正常"
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "normal"
    assert fields["hpi_stool"]["extraction_status"] == "not_found"
    assert "pe_vital_signs" in fields
    assert "aux_blood_gas" in fields
    assert "aux_crp" in fields


def test_qwen_batch_run_job_normalizes_raw_compact_response(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "主诉：反复咳嗽。患者精神、食欲欠佳，睡眠一般。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    raw_response = {
        "主诉": {"v": "反复咳嗽", "p": ["<s2>", "<s2>"]},
        "现病史": {
            "精神睡眠食欲": {"s": 1, "p": ["<s3>", "<s3>"]},
            "大便情况": {"v": "睡眠一般", "p": ["<s4>", "<s4>"]},
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
    assert fields["hpi_stool"]["original_value"] == "睡眠一般"


def test_qwen_batch_run_job_infers_normal_judgement_from_value_evidence_node(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "外耳道无异常分泌物，双侧乳突区无压痛，双耳粗测听力正常。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "体格检查": {
                    "耳部": {
                        "值": "外耳道无异常分泌物，双侧乳突区无压痛，双耳粗测听力正常",
                        "证据": merged_text,
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    field = {field["field_key"]: field for field in result["review_fields"]}["pe_ears"]
    assert field["original_value"] == "正常"
    assert field["qwen_status"] == "normal"
    assert field["extraction_status"] == "extracted"
    assert field["evidence"][0]["text"] == merged_text


def test_qwen_batch_run_job_accepts_abnormal_status_with_evidence_suffix(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "皮肤可见散在皮疹。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {"体格检查": {"皮肤": {"状态": "异常：皮肤可见散在皮疹", "证据": merged_text}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    field = {field["field_key"]: field for field in result["review_fields"]}["pe_skin"]
    assert field["original_value"] == "异常"
    assert field["qwen_status"] == "abnormal"
    assert field["evidence"][0]["text"] == merged_text


def test_qwen_batch_run_job_uses_anchor_position_before_restored_evidence_text(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "精神差。主诉：反复咳嗽。精神差。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "现病史": {
                    "精神睡眠食欲": {
                        "状态": "异常",
                        "证据": "精神差。",
                        "_position": ["<s4>", "<s4>"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    field = {field["field_key"]: field for field in result["review_fields"]}[
        "hpi_mental_sleep_appetite"
    ]
    evidence = field["evidence"][0]
    expected_start = merged_text.rfind("精神差。")
    assert evidence["text"] == "精神差。"
    assert evidence["start_offset"] == expected_start
    assert evidence["end_offset"] == expected_start + len("精神差。")


def test_qwen_batch_run_job_uses_raw_slice_for_multi_anchor_evidence(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "主诉：反复咳嗽。\n\n现病史：患者精神、食欲欠佳。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "现病史": {
                    "精神睡眠食欲": {
                        "状态": "异常",
                        "证据": "主诉：反复咳嗽。现病史：患者精神、食欲欠佳。",
                        "_position": ["<s1>", "<s4>"],
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    field = {field["field_key"]: field for field in result["review_fields"]}[
        "hpi_mental_sleep_appetite"
    ]
    evidence = field["evidence"][0]
    assert evidence["text"] == merged_text
    assert merged_text[evidence["start_offset"] : evidence["end_offset"]] == evidence["text"]


def test_qwen_batch_upstream_cleans_ocr_markdown_wrappers_for_extraction():
    raw = (
        "# OCR 完整结果 - page_001.jpg\n\n"
        "生成时间: 2026-06-27 10:34:07\n\n"
        "---\n\n"
        "```text\n"
        "主诉：反复咳嗽。\n\n"
        "第 1 页\n"
        "```\n"
    )

    cleaned = _clean_ocr_text_for_extraction(raw)

    assert cleaned == "主诉：反复咳嗽。"


def test_qwen_batch_run_job_falls_back_to_local_raw_leaf_parse(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    (upstream_group / "merged_ocr.txt").write_text("主诉：反复咳嗽。", encoding="utf-8")
    malformed_raw = (
        '{"主诉":{"v":"反复咳嗽","p":["<s1>","<s1>"]}},'
        '"个人史":{"吸烟史":{"v":"无吸烟史","p":["<s2>","<s2>"]}}'
    )
    (upstream_group / "merged_structured.json").write_text(
        json.dumps({"_raw_response": malformed_raw, "_parse_error": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "反复咳嗽"
    assert fields["personal_smoking_history"]["original_value"] == "无吸烟史"


def test_qwen_batch_run_job_normalize_only_writes_error_when_upstream_missing(tmp_path):
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()

    exit_code = run_job(
        job_dir=str(tmp_path / "job"),
        schema_path=str(schema_path),
        normalize_only=True,
    )

    assert exit_code == 1
    error = json.loads((tmp_path / "job" / "error.json").read_text(encoding="utf-8"))
    assert error["reason"] == "normalize_failed"
