def test_extraction_prompt_contains_ocr_constraints_and_schema_keys():
    from app.backend.services.copd_extraction.prompts import build_extraction_prompt

    prompt = build_extraction_prompt({"主诉": "咳嗽15年"}, ["copd_history_years", "bmi"])

    assert "不得静默修正 OCR" in prompt
    assert "ocr_correction" in prompt
    assert "copd_history_years" in prompt
    assert "bmi" in prompt
    assert "1/I/l" in prompt
    assert "0/O/o" in prompt


def test_verification_prompt_requires_structured_field_verdicts():
    from app.backend.services.copd_extraction.prompts import build_verification_prompt

    prompt = build_verification_prompt([
        {
            "source_hint": "体格检查",
            "source_text": "BMI:24.2kg/m2",
            "fields": [{"field_key": "bmi", "original_value": "24.2"}],
        }
    ])

    assert "verdict" in prompt
    assert "source_text_supported" in prompt
    assert "numeric_value_preserved" in prompt
    assert "reason_code" in prompt


def test_section_group_prompt_asks_for_source_hint_not_evidence():
    from app.backend.services.copd_extraction.prompts import build_section_group_extraction_prompt

    prompt = build_section_group_extraction_prompt("history_profile", "主诉：咳嗽15年。", ["copd_history_years"])

    assert "source_hint" in prompt
    assert "不要输出 evidence" in prompt
