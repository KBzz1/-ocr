COPD_OCR_SAMPLES = [
    {
        "name": "blood_gas_label_ocr",
        "error_families": ["indicator_label_ocr", "numeric_unit_range_anomaly"],
        "text": "辅助检查: 血气分析：pH 7.40、P8276.00mmHg、PCO2 36.00mmHg、F102 21.00、502 98.10%。",
        "expected_flags": ["value_not_in_evidence"],
    },
    {
        "name": "medication_terms_ocr",
        "error_families": ["medication_or_medical_term_ocr"],
        "text": "现病史: 予硫酸氨氯吡格雷片、氨酸氨溴索注射液、复方异丙托溴安溶液治疗后症状缓解不明显。",
        "expected_flags": [],
    },
    {
        "name": "duplicate_stitching",
        "error_families": ["duplicate_or_stitching"],
        "text": "体格检查: 腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。杵状指(趾)，四/部左右对称。",
        "expected_flags": ["possible_duplicate_or_stitching"],
    },
    {
        "name": "date_institution_ocr",
        "error_families": ["date_or_institution_ocr"],
        "text": "既往史: 20天前于合川区人名医院就诊。2028-04-30执行胸部CT检查。",
        "expected_flags": ["suspicious_date"],
    },
    {
        "name": "negation_uncertainty",
        "error_families": ["negation_or_uncertainty"],
        "text": "现病史: 无发热，否认咯血，胸部CT提示炎性结节或增殖灶可能，建议治疗后复查。",
        "expected_flags": ["negation_or_uncertainty_risk"],
    },
]
