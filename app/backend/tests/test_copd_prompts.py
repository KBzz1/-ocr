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

    prompt = build_verification_prompt("原文", [{"field_key": "bmi", "original_value": "24.2"}])

    assert "verdict" in prompt
    assert "evidence_supported" in prompt
    assert "numeric_value_preserved" in prompt
    assert "ocr_correction_reasonable" in prompt
