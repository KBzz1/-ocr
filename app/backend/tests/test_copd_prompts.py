def test_extraction_prompt_contains_ocr_constraints_and_schema_keys():
    from app.backend.services.copd_extraction.prompts import build_extraction_prompt

    prompt = build_extraction_prompt({"主诉": "咳嗽15年"}, ["copd_history_years", "bmi"])

    assert "不得静默修正 OCR" in prompt
    assert "ocr_correction" in prompt
    assert "copd_history_years" in prompt
    assert "bmi" in prompt
    assert "1/I/l" in prompt
    assert "0/O/o" in prompt
    assert "P62" in prompt
    assert "PC02" in prompt
    assert "血气项目名" in prompt
    assert "药名" in prompt
    assert "噻托溴铵" in prompt
    assert "二羟丙茶碱" in prompt
    assert "+10^9/L" in prompt
    assert "脉搏：9次/分" in prompt


def test_verification_prompt_requires_structured_field_verdicts():
    from app.backend.services.copd_extraction.prompts import build_verification_prompt

    prompt = build_verification_prompt(
        [
            {
                "source_hint": "体格检查",
                "source_text": "BMI:24.2kg/m2",
                "fields": [{"field_key": "bmi", "original_value": "24.2"}],
            }
        ],
        document_context="体格检查：BMI:24.2kg/m2。",
    )

    assert "verdict" in prompt
    assert "source_text_supported" in prompt
    assert "numeric_value_preserved" in prompt
    assert "ocr_correction_reasonable" in prompt
    assert "low_ocr_quality" in prompt
    assert "P62" in prompt
    assert "药名" in prompt
    assert "单位符号" in prompt
    assert "同一字段" in prompt
    assert "reason_code" in prompt
    assert prompt.count("问题：逐字段判断字段值是否能被提供的 OCR 事实支持。") == 1
    assert "事实：" in prompt
    assert "原始 OCR 上下文" in prompt


def test_verification_prompt_mentions_counterintuitive_zero_weight_loss():
    from app.backend.services.copd_extraction.prompts import build_verification_prompt

    prompt = build_verification_prompt([{"field_key": "weight_loss", "original_value": "0g"}])

    assert "体重减轻0g" in prompt
    assert "suspicious" in prompt


def test_section_group_prompt_asks_for_short_evidence_and_ocr_audit():
    from app.backend.services.copd_extraction.prompts import build_section_group_extraction_prompt

    prompt = build_section_group_extraction_prompt("history_profile", "主诉：咳嗽15年。", ["copd_history_years"])

    assert "source_hint" in prompt
    assert "evidence_phrase" in prompt
    assert "不超过50字" in prompt
    assert "ocr_correction" in prompt
    assert "不得静默修正 OCR" in prompt


def test_source_hint_regeneration_prompt_is_explicit_not_history_based():
    from app.backend.services.copd_extraction.prompts import build_source_hint_regeneration_prompt

    prompt = build_source_hint_regeneration_prompt(
        "主诉：咳嗽15年。",
        ["copd_history_years"],
        ["主诉"],
        [{"field_key": "copd_history_years", "original_value": "15年", "source_section": "history_profile"}],
    )

    assert "重新生成字段来源指向" in prompt
    assert "显式传入" in prompt
    assert "不依赖对话历史" in prompt
    assert "history_profile" in prompt


def test_section_group_prompt_contains_full_ocr_risk_warnings():
    from app.backend.services.copd_extraction.prompts import build_section_group_extraction_prompt

    prompt = build_section_group_extraction_prompt("auxiliary_exam", "血气：P02 80mmHg。", ["pao2"])

    assert "1/I/l" in prompt
    assert "0/O/o" in prompt
    assert "BHI/BMI" in prompt
    assert "cT/CT/Ct" in prompt
    assert "P62/P02/PC02/PCO2/PO2/PaO2/PaCO2" in prompt
    assert "噻托溴铵" in prompt
    assert "二羟丙茶碱" in prompt
    assert "+10^9/L" in prompt
    assert "×10^9/L" in prompt
    assert "表格错位" in prompt
    assert "冒号和空格丢失" in prompt
    assert "常见错别字" in prompt
    assert "前后矛盾数值" in prompt
    assert "不得静默选值" in prompt
