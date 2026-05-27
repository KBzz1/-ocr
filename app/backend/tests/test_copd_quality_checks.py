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


def test_quality_check_flags_blood_gas_label_ocr_ambiguity_when_value_matches():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("blood_gas_pao2", "76.00mmHg", "血气分析：P62 76.00mmHg↓")]

    result = apply_quality_checks(fields, "血气分析：P62 76.00mmHg↓")

    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "ocr_label_ambiguity" for flag in result[0]["quality_flags"])


def test_quality_check_flags_unit_symbol_ambiguity():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("wbc", "6.63+10^9/L", "血常规：白细胞(WBC)6.63+10^9/L")]

    result = apply_quality_checks(fields, "血常规：白细胞(WBC)6.63+10^9/L")

    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "unit_symbol_ambiguity" for flag in result[0]["quality_flags"])


def test_quality_check_flags_numeric_conflict_in_same_evidence():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("pulse", "9次/分", "体温：36.7℃ 脉搏：9次/分 呼吸：21次/分。心率99次/分，心律规则。")]

    result = apply_quality_checks(fields, "体温：36.7℃ 脉搏：9次/分 呼吸：21次/分。心率99次/分，心律规则。")

    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "ocr_numeric_conflict" for flag in result[0]["quality_flags"])


def test_quality_check_negation_risk_only_uses_local_value_context():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "36.7℃", "体温：36.7℃ 脉搏：99次/分。皮肤无黄染，无出血点。")]

    result = apply_quality_checks(fields, "体温：36.7℃ 脉搏：99次/分。皮肤无黄染，无出血点。")

    assert not any(flag["flag"] == "negation_or_uncertainty_risk" for flag in result[0]["quality_flags"])


def test_quality_check_duplicate_stitching_only_marks_field_evidence():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "36.7℃", "体温：36.7℃ 脉搏：99次/分。")]
    full_text = "体温：36.7℃ 脉搏：99次/分。\n腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"

    result = apply_quality_checks(fields, full_text)

    assert not any(flag["flag"] == "possible_duplicate_or_stitching" for flag in result[0]["quality_flags"])


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
