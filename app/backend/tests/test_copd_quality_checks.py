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

    fields = [_field("aux_blood_gas_po2", "PO2 76.00mmHg", "P8276.00mmHg")]

    result = apply_quality_checks(fields, "辅助检查: P8276.00mmHg")

    assert result[0]["verification_status"] == "suspicious"
    assert result[0]["quality_flags"][0]["flag"] == "value_not_in_evidence"


def test_quality_check_checks_single_digit_values_when_relevant():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("aux_blood_gas_po2", "2", "mMRC 3级")]

    result = apply_quality_checks(fields, "mMRC 3级")

    assert result[0]["verification_status"] == "suspicious"
    assert result[0]["quality_flags"][0]["flag"] == "value_not_in_evidence"


def test_quality_check_flags_vital_sign_range_risks():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [
        _field("temperature", "31.0℃", "体温31.0℃"),
        _field("pulse", "280次/分", "脉搏280次/分"),
        _field("respiration", "2次/分", "呼吸2次/分"),
        _field("blood_pressure", "280/20mmHg", "血压280/20mmHg"),
        _field("bmi", "6kg/m2", "BMI 6kg/m2"),
    ]

    result = apply_quality_checks(fields, "体格检查：体温31.0℃，脉搏280次/分，呼吸2次/分，血压280/20mmHg，BMI 6kg/m2")

    assert all(any(flag["flag"] == "physiologic_range_risk" for flag in item["quality_flags"]) for item in result)


def test_quality_check_flags_blood_gas_range_risks():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [
        _field("aux_blood_gas_ph", "6.8", "pH 6.8"),
        _field("aux_blood_gas_po2", "8mmHg", "PaO2 8mmHg"),
        _field("aux_blood_gas_pco2", "180mmHg", "PaCO2 180mmHg"),
    ]

    result = apply_quality_checks(fields, "血气分析：pH 6.8，PaO2 8mmHg，PaCO2 180mmHg")

    assert all(any(flag["flag"] == "physiologic_range_risk" for flag in item["quality_flags"]) for item in result)


def test_quality_check_flags_blood_gas_label_ocr_ambiguity_when_value_matches():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("aux_blood_gas_po2", "76.00mmHg", "血气分析：P62 76.00mmHg↓")]

    result = apply_quality_checks(fields, "血气分析：P62 76.00mmHg↓")

    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "ocr_label_ambiguity" for flag in result[0]["quality_flags"])


def test_quality_check_flags_blood_gas_label_not_whitelisted():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("aux_blood_gas_po2", "8276.00mmHg", "血气分析：P8276.00mmHg↓")]

    result = apply_quality_checks(fields, "血气分析：P8276.00mmHg↓")

    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "blood_gas_label_not_whitelisted" for flag in result[0]["quality_flags"])


def test_quality_check_accepts_standard_blood_gas_labels():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [
        _field("aux_blood_gas_po2", "76.00mmHg", "血气分析：PaO2 76.00mmHg"),
        _field("aux_blood_gas_pco2", "36.00mmHg", "血气分析：PCO2 36.00mmHg"),
    ]

    result = apply_quality_checks(fields, "血气分析：PaO2 76.00mmHg，PCO2 36.00mmHg")

    assert not any(flag["flag"] == "blood_gas_label_not_whitelisted" for item in result for flag in item["quality_flags"])
    assert not any(flag["flag"] == "ocr_label_ambiguity" for item in result for flag in item["quality_flags"])


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


def test_quality_check_flags_zero_weight_loss_as_counterintuitive_ocr_value():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("weight_loss", "0g", "现病史：近来体重减轻0g，食欲下降。")]

    result = apply_quality_checks(fields, "现病史：近来体重减轻0g，食欲下降。")

    assert result[0]["original_value"] == "0g"
    assert result[0]["verification_status"] == "suspicious"
    assert any(flag["flag"] == "counterintuitive_zero_weight_loss" for flag in result[0]["quality_flags"])


def test_quality_check_negation_risk_only_uses_local_value_context():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "36.7℃", "体温：36.7℃ 脉搏：99次/分。皮肤无黄染，无出血点。")]

    result = apply_quality_checks(fields, "体温：36.7℃ 脉搏：99次/分。皮肤无黄染，无出血点。")

    assert not any(flag["flag"] == "negation_or_uncertainty_risk" for flag in result[0]["quality_flags"])


def test_quality_check_duplicate_stitching_applied_from_full_text():
    """文档级重复检测应对 full_text 执行并将 flag 附加到所有字段。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "36.7℃", "体温：36.7℃ 脉搏：99次/分。")]
    full_text = "体温：36.7℃ 脉搏：99次/分。\n腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"

    result = apply_quality_checks(fields, full_text)

    # 修复后：文档级重复 flag 应被正确应用到字段
    assert any(flag["flag"] == "possible_duplicate_or_stitching" for flag in result[0]["quality_flags"])


def test_quality_check_no_duplicate_when_full_text_clean():
    """无重复的文档不产生重复 flag。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "36.7℃", "体温：36.7℃")]
    full_text = "体温：36.7℃ 脉搏：99次/分。腹部软无压痛，四肢活动自如。"

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

    fields = [_field("pe_respiratory_exam", "咯血", "否认咯血")]

    result = apply_quality_checks(fields, "否认咯血")

    assert result[0]["quality_flags"][0]["flag"] == "negation_or_uncertainty_risk"


def test_quality_check_flags_positive_pmh_hallucination_from_denied_history():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    evidence = (
        "既往史：平素身体一般，否认“糖尿病”、“冠心病”等病史，"
        "否认肝炎、结核等传染病史。"
    )
    fields = [
        _field("pmh_coronary_heart_disease", "有冠心病病史", evidence),
        _field("pmh_diabetes", "糖尿病病史", evidence),
    ]

    result = apply_quality_checks(fields, evidence)

    for item in result:
        assert item["verification_status"] == "suspicious"
        assert any(
            flag["flag"] in {"negation_or_uncertainty_risk", "value_not_in_evidence"}
            for flag in item["quality_flags"]
        ), item


# —— 新增：文档级重复检测应用到字段 ——


def test_document_quality_flags_applied_to_all_fields():
    """full_text 文档级重复检测结果应附加到所有字段。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    full_text = "腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"
    fields = [
        _field("temperature", "36.7℃", "体温：36.7℃"),
        _field("pulse", "99次/分", "脉搏：99次/分"),
    ]

    result = apply_quality_checks(fields, full_text)

    for item in result:
        assert any(
            flag["flag"] == "possible_duplicate_or_stitching"
            for flag in item["quality_flags"]
        ), f"field {item['field_key']} should have duplicate flag"


def test_document_quality_flags_not_duplicated():
    """文档级 flag 不应在每个字段中重复添加。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    full_text = "腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"
    fields = [_field("temperature", "36.7℃", "体温：36.7℃")]

    result = apply_quality_checks(fields, full_text)

    duplicate_count = sum(
        1 for flag in result[0]["quality_flags"]
        if flag["flag"] == "possible_duplicate_or_stitching"
    )
    assert duplicate_count == 1, "文档级 flag 不应重复出现"


# —— 新增：纯文本值 evidence 检查 ——


def test_value_not_in_evidence_for_pure_text():
    """纯文本值（不含数字）未在 evidence 中出现应标记。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("comorbidities", "高血压", "否认高血压、糖尿病、冠心病")]

    result = apply_quality_checks(fields, "否认高血压、糖尿病、冠心病")

    # "高血压" 在 evidence 中能找到，不应标记
    assert not any(
        flag["flag"] == "value_not_in_evidence" for flag in result[0]["quality_flags"]
    )


def test_value_not_in_evidence_for_hallucinated_text():
    """LLM 编造的纯文本值应被检测。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("comorbidities", "高血压", "否认糖尿病、冠心病")]

    result = apply_quality_checks(fields, "否认糖尿病、冠心病")

    # "高血压" 不在 evidence 中，应标记
    assert any(
        flag["flag"] == "value_not_in_evidence" for flag in result[0]["quality_flags"]
    )


# —— 新增：数值矛盾检查泛化 ——


def test_numeric_conflict_for_respiration():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("respiration", "2次/分", "呼吸：2次/分。呼吸21次/分。")]

    result = apply_quality_checks(fields, "呼吸：2次/分。呼吸21次/分。")

    assert any(
        flag["flag"] == "ocr_numeric_conflict" for flag in result[0]["quality_flags"]
    )


def test_numeric_conflict_for_temperature():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("temperature", "3.7℃", "体温：3.7℃。体温36.7℃。")]

    result = apply_quality_checks(fields, "体温：3.7℃。体温36.7℃。")

    assert any(
        flag["flag"] == "ocr_numeric_conflict" for flag in result[0]["quality_flags"]
    )


def test_numeric_conflict_not_triggered_for_normal_value():
    """正常数值不应触发矛盾检测。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("pulse", "99次/分", "脉搏：99次/分，心率99次/分")]

    result = apply_quality_checks(fields, "脉搏：99次/分，心率99次/分")

    assert not any(
        flag["flag"] == "ocr_numeric_conflict" for flag in result[0]["quality_flags"]
    )


# —— 新增：体重下降零值增强覆盖 ——


def test_counterintuitive_zero_weight_loss_with_jin():
    """「斤」作为单位应被检测。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("weight_loss", "0斤", "现病史：体重下降0斤")]

    result = apply_quality_checks(fields, "现病史：体重下降0斤")

    assert any(
        flag["flag"] == "counterintuitive_zero_weight_loss"
        for flag in result[0]["quality_flags"]
    )


def test_counterintuitive_zero_weight_loss_with_letter_O():
    """OCR 将 0 误读为大写字母 O 时应被检测。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("weight_loss", "Og", "现病史：体重减轻Og")]

    result = apply_quality_checks(fields, "现病史：体重减轻Og")

    assert any(
        flag["flag"] == "counterintuitive_zero_weight_loss"
        for flag in result[0]["quality_flags"]
    )


def test_counterintuitive_zero_weight_loss_with_xiaoshou():
    """「消瘦」作为体重下降同义词应被检测。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("weight_loss", "0kg", "近1月消瘦0kg")]

    result = apply_quality_checks(fields, "近1月消瘦0kg")

    assert any(
        flag["flag"] == "counterintuitive_zero_weight_loss"
        for flag in result[0]["quality_flags"]
    )


# —— 新增：生理范围边界值测试 ——


def test_physiologic_range_respiration_lower_bound():
    """呼吸频率下限 3：< 3 触发，≥ 3 不触发。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    # 边界值 3 不应触发
    fields_ok = [_field("respiration", "3次/分", "呼吸：3次/分")]
    result_ok = apply_quality_checks(fields_ok, "呼吸：3次/分")
    assert not any(
        flag["flag"] == "physiologic_range_risk"
        for flag in result_ok[0]["quality_flags"]
    ), "respiration=3 应在合理范围内"

    # 低于下限应触发
    fields_risk = [_field("respiration", "2次/分", "呼吸：2次/分")]
    result_risk = apply_quality_checks(fields_risk, "呼吸：2次/分")
    assert any(
        flag["flag"] == "physiologic_range_risk"
        for flag in result_risk[0]["quality_flags"]
    ), "respiration=2 应触发范围风险"


def test_physiologic_range_boundary_values():
    """验证边界值本身不触发范围风险。"""
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [
        _field("temperature", "32.0℃", "体温32.0℃"),
        _field("pulse", "20次/分", "脉搏20次/分"),
        _field("bmi", "8.0kg/m2", "BMI 8.0kg/m2"),
    ]

    result = apply_quality_checks(fields, "体温32.0℃，脉搏20次/分，BMI 8.0kg/m2")

    for item in result:
        assert not any(
            flag["flag"] == "physiologic_range_risk"
            for flag in item["quality_flags"]
        ), f"{item['field_key']} 边界值不应触发范围风险"
