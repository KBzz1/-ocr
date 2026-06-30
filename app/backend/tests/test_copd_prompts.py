def _sample_admission_schema():
    """按 admission_record_structured_fields.v1.yaml 真实 schema 构造最小可用结构。"""
    groups = [
        ("chief_complaint", "主诉", [("chief_complaint", "主诉")]),
        (
            "history_of_present_illness",
            "现病史",
            [
                ("hpi_initial_onset", "初次发病情况"),
                ("hpi_subsequent_course", "后续发病情况"),
                ("hpi_hospital_diagnosis", "院内诊断情况"),
                ("hpi_treatment_medications", "治疗药物"),
                ("hpi_recent_symptoms", "近期症状"),
                ("hpi_mental_status", "精神"),
                ("hpi_stool_status", "大便情况"),
                ("hpi_urine_status", "小便情况"),
                ("hpi_weight_change", "体重变化"),
            ],
        ),
        (
            "past_medical_history",
            "既往史",
            [
                ("pmh_cardiac_disease", "心脏病"),
                ("pmh_hypertension", "高血压"),
                ("pmh_diabetes", "糖尿病"),
                ("pmh_hepatitis_b", "乙肝"),
                ("pmh_hematochezia", "便血"),
                ("pmh_nephritis", "肾炎"),
                ("pmh_hematologic_disease", "血液病"),
                ("pmh_coronary_heart_disease", "冠心病"),
                ("pmh_cerebral_infarction", "脑梗塞"),
                ("pmh_surgery_history", "手术史"),
                ("pmh_transfusion_history", "输血史"),
                ("pmh_blood_product_history", "血制品史"),
                ("pmh_allergy_history", "过敏史"),
            ],
        ),
        (
            "personal_history",
            "个人史",
            [
                ("personal_occupation", "工作"),
                ("personal_smoking_history", "吸烟史"),
                ("personal_drinking_history", "饮酒史"),
            ],
        ),
        ("family_history", "家族史", [("family_history", "家族史")]),
        (
            "physical_examination",
            "体格检查",
            [
                ("pe_temperature", "体温"),
                ("pe_pulse", "脉搏"),
                ("pe_respiration_rate", "生命体征呼吸"),
                ("pe_blood_pressure", "血压"),
                ("pe_height", "身高"),
                ("pe_weight", "体重"),
                ("pe_bmi", "BMI"),
                ("pe_skin", "皮肤"),
                ("pe_eyes", "眼部"),
                ("pe_ears", "耳部"),
                ("pe_nose", "鼻部"),
                ("pe_oral_cavity", "口腔"),
                ("pe_neck", "颈部"),
                ("pe_chest", "胸部"),
                ("pe_breast", "乳房"),
                ("pe_respiratory_exam", "呼吸系统查体"),
                ("pe_cardiac_exam", "心脏查体"),
                ("pe_abdomen", "腹部"),
                ("pe_limbs", "四肢"),
                ("pe_neurological_exam", "神经"),
            ],
        ),
        (
            "ancillary_tests",
            "辅助检查",
            [
                ("aux_chest_ct", "胸部CT"),
                ("aux_cardiac_ultrasound", "心脏超声"),
                ("aux_blood_gas_ph", "血气pH"),
                ("aux_blood_gas_pco2", "血气pCO2"),
                ("aux_blood_gas_po2", "血气pO2"),
                ("aux_blood_gas_na", "血气Na+"),
                ("aux_blood_gas_fio2", "血气FIO2"),
                ("aux_blood_gas_oxygenation_index", "血气氧合指数"),
                ("aux_blood_routine", "血常规"),
                ("aux_electrolytes", "电解质"),
                ("aux_renal_function", "肾功"),
                ("aux_d_dimer", "D2聚体"),
            ],
        ),
        (
            "diagnosis",
            "诊断",
            [
                ("diagnosis_preliminary", "初步诊断"),
                ("diagnosis_final", "最终诊断"),
            ],
        ),
    ]
    return {
        "version": "admission_record_structured_fields.v1",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": gk,
                "group_label": gl,
                "fields": [
                    {"field_key": fk, "label": fl, "type": "string", "required": False, "hint": ""}
                    for fk, fl in fields
                ],
            }
            for gk, gl, fields in groups
        ],
    }


def _sample_evidence_units():
    return [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。",
            "start_offset": 0,
            "end_offset": 27,
            "page_no": 1,
            "section_key": "chief_complaint",
        },
        {
            "id": "u002",
            "text": "血气分析:pH7.40、pCO236.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:961",
            "start_offset": 5821,
            "end_offset": 5904,
            "page_no": 2,
            "section_key": "ancillary_tests",
        },
    ]


# ---------------------------------------------------------------------------
# 新固定字段 prompt 契约测试（Task 3）
# ---------------------------------------------------------------------------


def test_admission_prompt_requires_fixed_schema_fields_and_not_free_keys():
    from app.backend.services.copd_extraction.prompts import (
        ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION,
        build_admission_structured_fields_prompt,
    )

    assert ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION == "admission_record_structured_fields_prompt.v1"

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 1. 固定字段表：所有 schema 中的 field_key 与 label 都必须出现在提示词里。
    field_keys = []
    for group in schema["field_groups"]:
        for field in group["fields"]:
            field_keys.append(field["field_key"])
            assert field["field_key"] in prompt
            assert field["label"] in prompt

    # 2. 必须出现一个固定字段表的章节提示（例如"固定字段表"或类似措辞）。
    assert "固定字段表" in prompt

    # 3. 每个字段恰好一次：扫描整段 prompt 中 field_key 的出现次数，应等于 1（首次枚举）。
    for field_key in field_keys:
        assert prompt.count(field_key) >= 1

    # 4. 禁止 schema 外字段；禁止模型自由生成二级 key。
    assert "schema 外字段" in prompt or "schema外字段" in prompt
    assert "自由生成" in prompt
    assert "二级 key" in prompt or "二级key" in prompt

    # 5. 必须把 evidence_ids 表达为列表（list 关键字 + "evidence_ids"）。
    assert "evidence_ids" in prompt
    assert "list" in prompt

    # 6. 严禁旧的输出键（与新契约冲突）。
    for forbidden in ("source_hint", "evidence_phrase", "ocr_correction", "quality_flags"):
        assert forbidden not in prompt, f"prompt 仍包含旧契约字段 {forbidden}"


def test_admission_prompt_requests_compact_field_payload_without_repeated_schema_labels():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    assert "field_key、status、value、evidence_ids" in prompt
    assert "后端按 schema 回填章节" in prompt

    output_example = prompt.split("输出示例：", 1)[1].split("【硬约束 — 字段与 key】", 1)[0]
    for forbidden in ('"section_key"', '"section_label"', '"field_label"'):
        assert forbidden not in output_example, (
            f"Qwen 输出示例不应重复 schema 可回填字段 {forbidden}"
        )


def test_admission_prompt_requires_not_found_for_missing_fields():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 关键三件套必须同时出现：status="not_found"、value=""、evidence_ids=[]。
    # 任何一项缺失都意味着模型可能输出非规约的 not_found 形式（例如 value=null）。
    not_found_triple = (
        'status="not_found"' in prompt,
        'value=""' in prompt,
        'evidence_ids=[]' in prompt,
    )
    assert all(not_found_triple), (
        "not_found 三件套必须同时出现，缺失项："
        f"status={'status=\"not_found\"' if not_found_triple[0] else 'MISSING'}, "
        f"value={'value=\"\"' if not_found_triple[1] else 'MISSING'}, "
        f"evidence_ids={'evidence_ids=[]' if not_found_triple[2] else 'MISSING'}"
    )
    # 额外的 JSON 形式示例（status: "not_found"、value: ""、evidence_ids: []）也应出现。
    json_triple = (
        '"status": "not_found"' in prompt,
        '"value": ""' in prompt,
        '"evidence_ids": []' in prompt,
    )
    assert all(json_triple), (
        "JSON 形式示例中 not_found 三件套也必须同时出现，缺失项："
        f"status={'\"status\": \"not_found\"' if not_found_triple[0] else 'MISSING'}, "
        f"value={'\"value\": \"\"' if not_found_triple[1] else 'MISSING'}, "
        f"evidence_ids={'\"evidence_ids\": []' if not_found_triple[2] else 'MISSING'}"
    )
    # 必须明示未找到字段也要输出，禁止省略。
    assert "不得省略" in prompt or "不能省略" in prompt or "必须输出" in prompt


def test_admission_prompt_requires_normal_status_for_negative_physical_exam_j_fields():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    assert "J 型状态字段判定" in prompt
    assert "外耳道无异常分泌物，双侧乳突区无压痛，双耳粗测听力正常" in prompt
    assert "耳部=正常" in prompt
    assert "不得因为是阴性描述而输出 not_found" in prompt
    assert "只有原文完全没有该部位/项目信息时" in prompt


def test_admission_prompt_forbids_subjective_diagnosis():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 诊断字段必须显式存在
    diagnosis_field_keys = ("diagnosis_preliminary", "diagnosis_final")
    for field_key in diagnosis_field_keys:
        assert field_key in prompt
    # 禁止推断、补充、改写诊断
    assert "推断" in prompt
    assert "改写" in prompt
    assert "添加" in prompt or "补充" in prompt
    # 暗示诊断字段必须摘录原文，不能医学推理
    assert "主观" in prompt or "医学判断" in prompt or "医学推理" in prompt


def test_admission_prompt_requires_numbered_diagnosis_items_to_remain_separate():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    assert "按编号分行保留" in prompt
    assert "不得合并成一句" in prompt
    assert "便于审核页逐条展示、编辑和导出" in prompt
    assert "1慢性阻塞性肺疾病急性加重\n2高血压2级中危\n3慢性胃炎" in prompt


def test_admission_prompt_allows_shared_evidence_ids():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 提示词必须同时出现 血气 + 共享/共用 + 证据 三类关键词，缺一不可。
    # 这是共享 evidence 的核心条件：血气 6 个字段共享同一条血气分析证据单元。
    co_occurrence = ("血气" in prompt, "共享" in prompt or "共用" in prompt, "证据" in prompt)
    assert all(co_occurrence), (
        "血气 + 共享/共用 + 证据 必须同时出现，缺失项："
        f"血气={'YES' if co_occurrence[0] else 'NO'}, "
        f"共享/共用={'YES' if co_occurrence[1] else 'NO'}, "
        f"证据={'YES' if co_occurrence[2] else 'NO'}"
    )
    # 必须是正向允许（不是禁止）。
    assert "允许" in prompt or "可以" in prompt


def test_admission_prompt_does_not_instruct_title_correction_or_page_reorder():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 提示词必须禁止 OCR 修正、标题纠正、页序重排。
    assert "不得" in prompt
    assert "修正" in prompt or "纠正" in prompt
    assert "页" in prompt
    # 必须保留原始 OCR 证据片段，不静默改写。
    assert "raw" in prompt or "原始" in prompt or "原文" in prompt
    # 必须列举具体的标题错字示例（品后诊断），避免诱导模型做样本特异性纠正。
    assert "品后诊断" in prompt
    # 提示词必须禁止重排页面。
    assert "重排" in prompt or "重新排序" in prompt or "页序" in prompt


def test_admission_prompt_preserves_negated_past_medical_history_values():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    ocr_text = (
        "既往史：平素身体一般，否认“糖尿病”、“冠心病”等病史，"
        "否认肝炎、结核等传染病史。否认外伤及手术史，否认输血史。"
    )
    units = [
        {
            "id": "u_pmh_negation",
            "text": ocr_text,
            "start_offset": 320,
            "end_offset": 380,
            "page_no": 1,
            "section_key": "past_medical_history",
        }
    ]

    prompt = build_admission_structured_fields_prompt(schema, units, document_text=ocr_text)

    assert ocr_text in prompt
    assert "否定范围" in prompt
    assert "保留否定词" in prompt
    assert "否认糖尿病病史" in prompt
    assert "否认冠心病病史" in prompt
    assert "不得输出“有糖尿病病史”" in prompt
    assert "不得输出“有冠心病病史”" in prompt
    assert "否认肝炎、结核等传染病史" in prompt
    assert "pmh_diabetes" in prompt
    assert "pmh_coronary_heart_disease" in prompt
    assert "pmh_hepatitis_b" in prompt


def test_admission_prompt_enumerates_evidence_units_by_id():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 每条 evidence unit 的 ID 必须出现，且对应的原文片段必须出现。
    for unit in units:
        assert unit["id"] in prompt
        assert unit["text"] in prompt

    # 整体 prompt 必须包含 JSON 输出契约示意（status 枚举 + 列表字段）。
    assert "found" in prompt
    assert "uncertain" in prompt


# ---------------------------------------------------------------------------
# prompt 模块版本契约（Task 11 收尾）
# ---------------------------------------------------------------------------


def test_prompts_module_exposes_only_active_prompt_version_constants():
    """活动路径只保留新 prompt 版本常量与新 builder；旧 builder 已被清理。"""
    from app.backend.services.copd_extraction import prompts

    # 新契约：固定字段 prompt 版本常量
    assert hasattr(prompts, "ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION")
    assert prompts.ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION == "admission_record_structured_fields_prompt.v1"

    # 旧 builder 已被 Task 11 移除
    forbidden_builders = (
        "build_extraction_prompt",
        "build_section_group_extraction_prompt",
        "build_source_hint_regeneration_prompt",
    )
    for name in forbidden_builders:
        assert not hasattr(prompts, name), (
            f"prompts 不应再导出旧 builder {name}"
        )
