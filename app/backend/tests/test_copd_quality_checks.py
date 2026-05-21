"""薄规则质量核验测试 —— 只输出 quality_flags，不自动纠错、不抽取字段、不导致任务失败。"""


def _field(field_key: str, value: str, evidence: str):
    return {
        "field_key": field_key,
        "original_value": value,
        "evidence": evidence,
        "confidence": 0.8,
        "source_section": "辅助检查",
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": evidence, "normalized": evidence, "reason": ""},
    }


def test_quality_check_flags_value_not_in_evidence():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("blood_gas_pao2", "PO2 76.00mmHg", "P8276.00mmHg")]

    result = apply_quality_checks(fields, "辅助检查: P8276.00mmHg")

    assert result[0]["verification_status"] == "suspicious"
    assert result[0]["quality_flags"][0]["flag"] == "value_not_in_evidence"


def test_quality_check_flags_duplicate_stitching():
    from app.backend.services.copd_extraction.quality_checks import document_quality_flags

    text = "腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"

    flags = document_quality_flags(text)

    assert any(flag["flag"] == "possible_duplicate_or_stitching" for flag in flags)


def test_quality_check_flags_future_date():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("exam_date", "2028-04-30", "2028-04-30执行胸部CT")]

    result = apply_quality_checks(fields, "2028-04-30执行胸部CT")

    assert result[0]["quality_flags"][0]["flag"] == "suspicious_date"


def test_quality_check_flags_negation_risk():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("positive_signs", "咯血", "否认咯血")]

    result = apply_quality_checks(fields, "否认咯血")

    assert result[0]["quality_flags"][0]["flag"] == "negation_or_uncertainty_risk"
