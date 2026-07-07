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
    assert len(result["review_fields"]) == 64
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["chief_complaint"]["original_value"] == "咳嗽"
    assert fields["chief_complaint"]["evidence"][0]["start_offset"] == 0
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "正常"
    assert fields["hpi_mental_sleep_appetite"]["qwen_status"] == "normal"
    assert fields["hpi_stool"]["extraction_status"] == "not_found"
    assert "pe_vital_signs" not in fields
    assert "pe_temperature" in fields
    assert "pe_pulse" in fields
    assert "pe_heart_rate" in fields
    assert "pe_respiration_rate" in fields
    assert "pe_blood_pressure" in fields
    assert "pe_height" in fields
    assert "pe_weight" in fields
    assert "pe_bmi" in fields
    assert "aux_blood_gas" not in fields
    assert "aux_blood_gas_ph" in fields
    assert "aux_blood_gas_pco2" in fields
    assert "aux_blood_gas_po2" in fields
    assert "aux_blood_gas_na" in fields
    assert "aux_blood_gas_fio2" in fields
    assert "aux_blood_gas_oxygenation_index" in fields
    assert "aux_crp" in fields
    assert "aux_blood_routine" not in fields
    assert "aux_blood_routine_wbc" in fields
    assert "aux_blood_routine_mxd_percent" in fields
    assert "aux_blood_routine_mod_absolute" in fields


def test_qwen_batch_run_job_splits_legacy_composite_parameter_fields(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    vital_signs = "体温:36.7℃脉搏:99次/分呼吸:21次/分血压:142/87mmHg"
    heart_rhythm = "心率99次/分，心律规则，心音正常，心脏各瓣膜未闻及病理性杂音，无心包摩擦音。"
    height_weight_bmi = "身高:175cm体重:74kgBMI:24.2kg/m²"
    blood_gas = "pH7.40↓、pCO235.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:361%。"
    blood_routine = "白细胞(WBC)6.68*10^9/L、单核细胞百分率(MXD%)13.9%、单核细胞绝对值(MOD#)0.92*10^9/L。"
    merged_text = "\n".join([vital_signs, heart_rhythm, height_weight_bmi, blood_gas, blood_routine])
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {
                "体格检查": {
                    "生命体征": {"值": vital_signs, "证据": vital_signs},
                    "心律": {"值": heart_rhythm, "证据": heart_rhythm},
                    "身高体重BMI": {"值": height_weight_bmi, "证据": height_weight_bmi},
                },
                "辅助检查": {
                    "血气": {"值": blood_gas, "证据": blood_gas},
                    "血常规": {"值": blood_routine, "证据": blood_routine},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    fields = {field["field_key"]: field for field in result["review_fields"]}
    assert fields["pe_temperature"]["original_value"] == "36.7"
    assert fields["pe_pulse"]["original_value"] == "99"
    assert fields["pe_heart_rate"]["original_value"] == "99"
    assert fields["pe_respiration_rate"]["original_value"] == "21"
    assert fields["pe_blood_pressure"]["original_value"] == "142/87"
    assert fields["pe_height"]["original_value"] == "175"
    assert fields["pe_weight"]["original_value"] == "74"
    assert fields["pe_bmi"]["original_value"] == "24.2"
    assert fields["aux_blood_gas_ph"]["original_value"] == "7.40"
    assert fields["aux_blood_gas_pco2"]["original_value"] == "35.00"
    assert fields["aux_blood_gas_po2"]["original_value"] == "76.00"
    assert fields["aux_blood_gas_na"]["original_value"] == "130.00"
    assert fields["aux_blood_gas_fio2"]["original_value"] == "21.00"
    assert fields["aux_blood_gas_oxygenation_index"]["original_value"] == "361"
    assert fields["aux_blood_routine_wbc"]["original_value"] == "6.68"
    assert fields["aux_blood_routine_mxd_percent"]["original_value"] == "13.9"
    assert fields["aux_blood_routine_mod_absolute"]["original_value"] == "0.92"
    assert fields["pe_heart_rhythm"]["original_value"] == "正常"
    assert fields["pe_heart_rhythm"]["qwen_status"] == "normal"
    assert fields["pe_temperature"]["evidence"][0]["text"] == vital_signs
    assert fields["aux_blood_gas_po2"]["evidence"][0]["text"] == blood_gas


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
    assert fields["hpi_mental_sleep_appetite"]["original_value"] == "患者精神、食欲欠佳，"
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
    assert field["original_value"] == "皮肤可见散在皮疹"
    assert field["qwen_status"] == "abnormal"
    assert field["evidence"][0]["text"] == merged_text


def test_qwen_batch_run_job_keeps_abnormal_judgement_description_from_value(tmp_path):
    job_dir = tmp_path / "job"
    upstream_group = job_dir / "upstream_output" / "_ungrouped"
    upstream_group.mkdir(parents=True)
    schema_path = Path("app/config/schemas/qwen_batch_admission_record.v2.yaml").resolve()
    merged_text = "既往有血小板减少病史。"
    (upstream_group / "merged_ocr.txt").write_text(merged_text, encoding="utf-8")
    (upstream_group / "merged_structured.json").write_text(
        json.dumps(
            {"既往史": {"血液病": {"s": 1, "v": "血小板减少病史", "p": ["<s1>", "<s1>"]}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalize_upstream_output(job_dir=job_dir, schema_path=schema_path)

    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    field = {field["field_key"]: field for field in result["review_fields"]}["pmh_blood_disease"]
    assert field["original_value"] == "血小板减少病史"
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
