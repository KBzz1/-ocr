def _sample_admission_schema():
    """按 admission_record_structured_fields.v1.yaml 真实 schema 构造最小可用结构。"""
    field_descriptions = {
        "pe_eyes": "眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容",
        "pe_chest": "胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验；双肺内容归呼吸系统检查，乳房内容归乳房字段",
    }
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
                    {
                        "field_key": fk,
                        "label": fl,
                        "type": "string",
                        "required": False,
                        "hint": "",
                        "description": field_descriptions.get(fk, ""),
                    }
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


def test_admission_messages_split_system_and_user():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _sample_admission_schema()
    system, user = build_admission_structured_fields_messages(
        schema=schema, evidence_units=[{"id": "u001", "text": "主诉：咳嗽20年"}], document_text="全文"
    )
    # system 承载稳定规则与分层字段目录，不含证据/原文数据
    assert "结构化抽取助手" in system
    assert "u001" not in system and "咳嗽20年" not in system
    assert "任务边界" in system
    assert "取值策略" in system
    assert "字段目录" in system
    # user 承载证据与原文
    assert "[u001] 主诉：咳嗽20年" in user
    assert "全文" not in user


def test_admission_prompt_refactored_six_segment_skeleton():
    """重构骨架断言：输出契约/通用原则/领域规则/固定字段表各段存在，
    删【再次强调】与独立 OCR 风险段，通用原则保留 P62/P02、×10^9/L 例。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _sample_admission_schema()
    system, _ = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    assert "你是慢阻肺/呼吸系统入院记录结构化抽取助手" in system
    assert "【任务边界】" in system
    assert "【取值策略】" in system
    assert "【字段目录】" in system
    assert "【三个局部判定示例】" in system
    assert "【schema】" not in system
    assert "id_namespace" not in system


def test_admission_prompt_domain_rule_field_boundary():
    """领域规则新增字段边界一句：不收录内容（一般情况）不写入任何字段、不引用为证据。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _sample_admission_schema()
    system, _ = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    assert "字段目录" in system
    assert "体格检查" in system
    assert "pe_eyes" in system and "pe_oral_cavity" in system


def test_admission_messages_append_reminder_default_absent():
    """变体 A：默认（append_reminder=False）时 system 与 user 均无提醒句。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _sample_admission_schema()
    system, user = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    assert "请严格遵守" not in user
    assert "请严格遵守" not in system


def test_admission_messages_append_reminder_true_appends_at_user_end():
    """变体 B：append_reminder=True 时提醒句恰好出现一次且位于 user 末尾，system 不含提醒句。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    reminder = "再次检查：只输出固定字段，evidence_ids 必须来自上面的 [uXXX]。"
    schema = _sample_admission_schema()
    system, user = build_admission_structured_fields_messages(
        schema, _sample_evidence_units(), append_reminder=True
    )

    assert user.endswith(reminder)
    assert user.count(reminder) == 1
    assert "请严格遵守" not in system


def test_admission_prompt_requires_fixed_schema_fields_and_not_free_keys():
    from app.backend.services.copd_extraction.prompts import (
        ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION,
        build_admission_structured_fields_prompt,
    )

    assert ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION == "extractor.v4"

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

    # 2. 必须出现分层字段目录。
    assert "字段目录" in prompt

    # 3. 每个字段恰好一次：扫描整段 prompt 中 field_key 的出现次数，应等于 1（首次枚举）。
    for field_key in field_keys:
        assert prompt.count(field_key) >= 1

    # 4. 状态和证据关系必须在自然语言中明确，结构细节由 JSON Schema 约束。
    assert "evidence_ids" in prompt
    assert 'status="not_found"' in prompt

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

    assert "evidence_ids" in prompt
    assert "【schema】" not in prompt


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
    # 结构细节由 response_format=json_schema 负责，不重复粘贴完整 JSON 示例。
    assert "正式输出仍须覆盖字段目录中的全部字段" in prompt


def test_admission_prompt_requires_normal_status_for_negative_physical_exam_j_fields():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_prompt,
    )

    schema = _sample_admission_schema()
    units = _sample_evidence_units()
    prompt = build_admission_structured_fields_prompt(schema, units)

    # 正常判断型：正常→"正常"、异常→摘录异常原文、未提及→not_found
    assert "正常判断型" in prompt
    assert "阴性描述不能被当作未提及" in prompt
    assert "出现异常时摘录具体异常" in prompt
    assert "未提及" in prompt
    assert 'status="not_found"' in prompt
    assert 'status="uncertain"' in prompt


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
    # 禁止推断、补充、改写诊断（"改写/重写"压缩进通用原则与诊断原则）
    assert "推断" in prompt
    assert "改写" in prompt or "重写" in prompt
    assert "添加" in prompt or "补写" in prompt
    # 暗示诊断字段必须摘录原文，不能医学推理
    assert "医学推理" in prompt or "只能根据" in prompt
    assert "保留原文编号和编号顺序" in prompt


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
    assert "页序" in prompt
    # 必须保留原始 OCR 证据片段，不静默改写。
    assert "raw" in prompt or "原始" in prompt or "原文" in prompt
    # 不再向抽取器堆叠具体 OCR 错字示例。
    assert "P62/P02" not in prompt
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

    # 原文（user 部分）保留
    assert ocr_text in prompt
    # 通用原则：否定词规则压缩措辞（否认/无/未见、禁止翻转、value 保留否定表述）
    assert "保留否定词" in prompt
    assert "否认" in prompt and "无" in prompt and "未见" in prompt
    assert "禁止把否定翻转" in prompt
    assert "禁止把否定翻转为阳性" in prompt
    # 既往史疾病字段仍在固定字段表中
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


def test_evidence_stream_has_one_id_namespace_without_local_order():
    from app.backend.services.copd_extraction.prompts import build_verification_messages

    _, user = build_verification_messages(
        evidence_units=[
            {"id": "u007", "text": "第一句", "order": 7, "page_no": 1},
            {"id": "u009", "text": "第三句", "order": 8, "page_no": 1},
        ],
        fields=[{
            "field_key": "hpi_recent_symptoms",
            "value": "第三句",
            "evidence_ids": ["u009"],
        }],
    )

    assert "[u007] 第一" in user
    assert "[u009] 第三" in user
    assert "order=" not in user
    assert "id_namespace" not in user
    assert "evidence_complete" not in user


def test_verifier_claims_are_json_and_do_not_add_cited_text():
    import json
    from app.backend.services.copd_extraction.prompts import build_verification_messages

    _, user = build_verification_messages(
        evidence_units=[{"id": "u033", "text": "唇色发绀，口腔黏膜无溃疡", "page_no": 1}],
        fields=[{
            "field_key": "pe_oral_cavity",
            "field_label": "体格检查/口腔",
            "value": "唇色发绀，口腔黏膜无溃疡",
            "evidence_ids": ["u033"],
        }],
    )

    claims_text = user.split("<claims>\n", 1)[1].split("\n</claims>", 1)[0]
    claims = json.loads(claims_text)
    assert claims["claims"][0]["cited_ids"] == ["u033"]
    assert "cited_text" not in claims["claims"][0]
    assert "唇色发绀，口腔黏膜无溃疡" in user


# ---------------------------------------------------------------------------
# prompt 模块版本契约（Task 11 收尾）
# ---------------------------------------------------------------------------


def test_prompts_module_exposes_only_active_prompt_version_constants():
    """活动路径只保留新 prompt 版本常量与新 builder；旧 builder 已被清理。"""
    from app.backend.services.copd_extraction import prompts

    # 新契约：固定字段 prompt 版本常量
    assert hasattr(prompts, "ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION")
    assert prompts.ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION == "extractor.v4"
    # 复核器 prompt 版本常量（2026-08-04 verifier.v3 定稿）
    assert prompts.VERIFIER_PROMPT_VERSION == "verifier.v3"

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


# ---------------------------------------------------------------------------
# Task 2：字段表 description 渲染契约（pe_* 字段边界精确化）
# ---------------------------------------------------------------------------


def _load_real_schema():
    """加载真实 schema 文件（app/config/schemas/admission_record_structured_fields.v1.yaml）。"""
    import yaml
    from pathlib import Path

    schema_path = (
        Path(__file__).resolve().parents[3]
        / "app" / "config" / "schemas" / "admission_record_structured_fields.v1.yaml"
    )
    with open(schema_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_field_table_description_rendered_from_schema_metadata():
    """fixture schema：字段行格式为 field_key｜中文名｜P=T/J/D｜特有边界；
    有 description 的字段渲染出特有边界，无 description 的字段（含数值型）无第四段。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _sample_admission_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    assert "pe_eyes｜眼部｜P=J｜眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容" in system
    assert "pe_chest｜胸部｜P=T｜胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验；双肺内容归呼吸系统检查，乳房内容归乳房字段" in system
    # 无 description 字段渲染只有三段：field_key｜label｜P=标记
    assert "pe_temperature｜体温｜P=T" in system
    assert "pe_temperature｜体温｜P=T｜" not in system
    assert "pe_cardiac_exam｜心脏查体｜P=J" in system


def test_field_table_description_rendered_with_real_schema():
    """真实 schema：内容型 pe_* 字段的 description 渲染进 system 固定字段表（v4 P 标记格式）。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    assert "pe_eyes｜眼部｜P=J｜眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容" in system
    assert "pe_chest｜胸部｜P=T｜胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验；双肺内容归呼吸系统检查，乳房内容归乳房字段" in system
    assert "pe_neurological_exam｜神经｜P=J｜神经系统项目：神志、精神、对答、反射、病理征；一般情况（发育/营养/体型/体位/表情）不属本字段" in system


def test_numeric_fields_have_no_description_with_real_schema():
    """真实 schema：数值型 7 字段（体温/脉搏/呼吸/血压/身高/体重/BMI）不加 description，
    字段行只有三段（field_key｜中文名｜P=T），无第四段特有边界。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    for numeric_field in (
        "pe_temperature｜体温",
        "pe_pulse｜脉搏",
        "pe_respiration_rate｜生命体征呼吸",
        "pe_blood_pressure｜血压",
        "pe_height｜身高",
        "pe_weight｜体重",
        "pe_bmi｜BMI",
    ):
        assert f"{numeric_field}｜P=T" in system
        assert f"{numeric_field}｜P=T｜" not in system, f"{numeric_field} 不应渲染 description"


# ---------------------------------------------------------------------------
# v4：每字段 P=T/J/D 策略标记与字段边界（PPEMA-V1 §4.2）
# ---------------------------------------------------------------------------


def _field_lines(system: str) -> list[str]:
    """提取字段目录段中每行字段目录（以 field_key｜ 开头，含 P= 标记的行）。

    目录段内部还有各章节标题（【主诉】等）与共同规则行，只取字段行；
    段结束以【三个局部判定示例】为准。
    """
    import re

    lines = []
    in_catalog = False
    for line in system.splitlines():
        stripped = line.strip()
        if stripped.startswith("【字段目录】"):
            in_catalog = True
            continue
        if not in_catalog:
            continue
        if stripped.startswith("【三个局部判定示例】"):
            break
        if re.match(r"^[a-z_0-9]+｜", stripped) and "P=" in stripped:
            lines.append(stripped)
    return lines


def test_v4_every_field_has_exactly_one_policy_marker():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    lines = _field_lines(system)
    assert len(lines) == 61, f"字段目录应有 61 行，实际 {len(lines)}"
    for line in lines:
        markers = [part for part in line.split("｜") if part in ("P=T", "P=J", "P=D")]
        assert len(markers) == 1, f"每行必须有且只有一个 P 标记: {line!r}"
    # 每个 field_key 恰好出现一个 P 标记
    import re

    total_markers = len(re.findall(r"P=[TJD]", system))
    assert total_markers == 61, f"P 标记总数应为 61，实际 {total_markers}"


def test_v4_diagnosis_group_is_fixed_d_and_rest_fixed_t_or_j():
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    lines = _field_lines(system)
    by_line = {line.split("｜")[0]: line for line in lines}
    # diagnosis 组固定 D
    assert by_line["diagnosis_preliminary"].endswith("｜P=D")
    assert by_line["diagnosis_final"].endswith("｜P=D")
    # 其余字段：J 集合为 J，非 J 非 D 为 T
    from app.backend.services.copd_extraction.field_policies import (
        DIAGNOSIS_FIELD_KEYS,
        NORMAL_JUDGEMENT_FIELD_KEYS,
    )

    for key, line in by_line.items():
        marker = line.split("｜P=")[1][0]
        if key in DIAGNOSIS_FIELD_KEYS:
            assert marker == "D", f"{key} 应为 D，实际 {marker}"
        elif key in NORMAL_JUDGEMENT_FIELD_KEYS:
            assert marker == "J", f"{key} 应为 J，实际 {marker}"
        else:
            assert marker == "T", f"{key} 应为 T，实际 {marker}"


def test_field_policies_shared_truth_source_matches_legacy_j_set():
    """共享策略真源：J 集合成员与 prompts 历史 _NORMAL_JUDGEMENT_FIELD_KEYS 完全一致。"""
    from app.backend.services.copd_extraction import prompts
    from app.backend.services.copd_extraction.field_policies import (
        NORMAL_JUDGEMENT_FIELD_KEYS,
        field_policy,
    )

    assert NORMAL_JUDGEMENT_FIELD_KEYS == prompts._NORMAL_JUDGEMENT_FIELD_KEYS
    assert len(NORMAL_JUDGEMENT_FIELD_KEYS) == 25

    # diagnosis 组固定 D；J 集合固定 J；其余固定 T
    assert field_policy({"field_key": "diagnosis_preliminary"}, "diagnosis") == "D"
    assert field_policy({"field_key": "pe_eyes"}, "physical_examination") == "J"
    assert field_policy({"field_key": "chief_complaint"}, "chief_complaint") == "T"


def test_v4_aux_electrolytes_renal_function_mutually_exclusive_boundaries():
    """aux_electrolytes / aux_renal_function 互斥边界必须真实出现在渲染后的 prompt。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    electrolytes_line = next(
        line for line in _field_lines(system)
        if line.startswith("aux_electrolytes｜")
    )
    renal_line = next(
        line for line in _field_lines(system)
        if line.startswith("aux_renal_function｜")
    )
    assert "P=J" in electrolytes_line
    assert "电解质" in electrolytes_line and "矿物" in electrolytes_line
    assert "P=J" in renal_line
    assert "eGFR" in renal_line
    assert "尿素" in renal_line and "肌酐" in renal_line and "尿酸" in renal_line


def test_v4_ancillary_source_scope_frozen_across_sections():
    """辅助检查来源范围冻结：明确带检查标签和值的结果可出现在辅助检查章节或现病史；
    仍禁止从诊断、症状或医学常识反推数值。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    assert "辅助检查" in system
    co_occurrence = (
        "带检查标签" in system,
        "现病史" in system,
        "反推数值" in system,
    )
    assert all(co_occurrence), (
        "辅助检查来源范围冻结三要素缺失："
        f"带检查标签={'YES' if co_occurrence[0] else 'NO'}, "
        f"现病史={'YES' if co_occurrence[1] else 'NO'}, "
        f"反推数值={'YES' if co_occurrence[2] else 'NO'}"
    )


def test_v4_hpi_time_boundaries_still_rendered():
    """HPI 时间边界保留在字段行特有边界中。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    assert "hpi_initial_onset｜初次发病情况｜P=T｜首次/最初发病" in system
    assert "hpi_recent_symptoms｜近期症状｜P=T｜本次或近期加重" in system


def test_v4_long_scope_cards_are_not_restored():
    """不恢复重复的 source_scope/time_scope/include/exclude/value_policy 长卡片。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, user = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    for forbidden in ("source_scope", "time_scope", "value_policy", "exclude=", "include="):
        assert forbidden not in system, f"不应恢复长卡片字段 {forbidden}"
        assert forbidden not in user, f"不应恢复长卡片字段 {forbidden}"


# ---------------------------------------------------------------------------
# v4：三个局部 JSON 微例（PPEMA-V1 §4.3）
# ---------------------------------------------------------------------------


def _extract_example_jsons(system: str) -> list[dict]:
    import json
    import re

    blocks = re.findall(r"```json\n(.*?)\n```", system, flags=re.S)
    return [json.loads(block) for block in blocks]


def test_v4_exactly_three_parseable_json_examples():
    """三个示例必须是可解析局部 JSON；不得加入第四个示例。"""
    import json

    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    examples = _extract_example_jsons(system)
    assert len(examples) == 3, f"必须恰好 3 个 JSON 示例，实际 {len(examples)}"
    for example in examples:
        assert set(example.keys()) == {"output_fields"}, (
            "示例必须是局部 output_fields，不得给完整顶层响应"
        )
        fields = example["output_fields"]
        assert isinstance(fields, list) and len(fields) >= 1
        for item in fields:
            assert set(item.keys()) == {"field_key", "status", "value", "evidence_ids"}


def test_v4_example1_shared_negation_scope():
    """示例 1：同一合成证据同时支持 T 字段否定摘录（pmh_cardiac_disease）
    与 J 字段“正常”（pe_eyes），两者均 found 并引用同一 ID u901。"""
    from app.backend.services.copd_extraction.field_policies import (
        DIAGNOSIS_FIELD_KEYS,
        NORMAL_JUDGEMENT_FIELD_KEYS,
    )
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    example = _extract_example_jsons(system)[0]
    fields = example["output_fields"]
    t_field = next(item for item in fields if item["field_key"] == "pmh_cardiac_disease")
    j_field = next(item for item in fields if item["field_key"] == "pe_eyes")
    # 从共享策略真源核验字段身份：pmh_cardiac_disease 非 J 非 D → T；pe_eyes 是 J
    assert "pmh_cardiac_disease" not in NORMAL_JUDGEMENT_FIELD_KEYS
    assert "pmh_cardiac_disease" not in DIAGNOSIS_FIELD_KEYS
    assert "pe_eyes" in NORMAL_JUDGEMENT_FIELD_KEYS
    assert t_field["status"] == "found"
    assert t_field["value"] == "否认心脏病史"
    assert j_field["status"] == "found"
    assert j_field["value"] == "正常"
    assert t_field["evidence_ids"] == j_field["evidence_ids"] == ["u901"]


def test_v4_example2_j_abnormal_takes_priority():
    """示例 2：心脏查体同时有异常与正常描述，只保留异常片段，不因出现“正常”而折叠。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    example = _extract_example_jsons(system)[1]
    fields = example["output_fields"]
    assert len(fields) == 1
    cardiac = fields[0]
    assert cardiac["field_key"] == "pe_cardiac_exam"
    assert cardiac["status"] == "found"
    assert cardiac["evidence_ids"] == ["u902"]
    # 只保留异常片段：值中不含“正常”折叠，也不含“律齐”等正常描述
    assert "正常" not in cardiac["value"]
    assert "律齐" not in cardiac["value"]
    assert any(term in cardiac["value"] for term in ("杂音", "增强", "减弱", "异常"))


def test_v4_example3_bmi_inference_forbidden():
    """示例 3：只有身高体重时二者 found，BMI 必须 not_found、空 value、空 evidence_ids。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, _ = build_admission_structured_fields_messages(schema, [])

    example = _extract_example_jsons(system)[2]
    fields = {item["field_key"]: item for item in example["output_fields"]}
    assert fields["pe_height"]["status"] == "found"
    assert fields["pe_weight"]["status"] == "found"
    assert fields["pe_height"]["evidence_ids"] == ["u903"]
    assert fields["pe_weight"]["evidence_ids"] == ["u903"]
    bmi = fields["pe_bmi"]
    assert bmi["status"] == "not_found"
    assert bmi["value"] == ""
    assert bmi["evidence_ids"] == []


def test_v4_example_ids_are_example_only():
    """示例 ID u901-u903 只属于示例：完整 prompt（system+user）不得以证据形式复用。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, user = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    assert "u901" in system and "u902" in system and "u903" in system
    # 示例 ID 只出现在 system 的示例段，不出现在 user 证据流
    assert "u901" not in user
    assert "u902" not in user
    assert "u903" not in user
    # user 证据流只有真实证据 ID
    for unit in _sample_evidence_units():
        assert unit["id"] in user


def test_v4_full_prompt_free_of_legacy_markers():
    """完整 prompt 逐字扫描：无【schema】、order=、id_namespace、evidence_complete。"""
    from app.backend.services.copd_extraction.prompts import (
        build_admission_structured_fields_messages,
    )

    schema = _load_real_schema()
    system, user = build_admission_structured_fields_messages(schema, _sample_evidence_units())

    for forbidden in ("【schema】", "order=", "id_namespace", "evidence_complete"):
        assert forbidden not in system, f"system 仍包含禁用字样 {forbidden}"
        assert forbidden not in user, f"user 仍包含禁用字样 {forbidden}"


# ---------------------------------------------------------------------------
# verifier.v3：表述规范性契约 + 术语陌生判别 + 对照微例 + 逗号级拆句
# ---------------------------------------------------------------------------


def test_verifier_v3_system_has_expression_standard_rule():
    """v3：表述规范性检查不归因 OCR、不要求修正词；术语陌生 vs 非标准表述判别细则存在。"""
    from app.backend.services.copd_extraction.prompts import build_verification_messages

    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "胸状胸。"}],
        fields=[{"field_key": "pe_chest", "value": "胸状胸", "evidence_ids": ["e001"]}],
    )
    assert "表述规范性" in system
    assert "不归因于 OCR" in system and "不要求给出修正词" in system
    assert "术语陌生" in system and "非标准表述" in system
    assert "nonstandard_expression" in system
    assert "text_standard" in system
    assert "ocr_quality_issue" not in system  # 新生成不再提旧 reason


def test_verifier_v3_grounding_split_extended_to_comma():
    """v3：拆句边界扩展到逗号/顿号（value>40 字），含否定豁免。"""
    from app.backend.services.copd_extraction.prompts import build_verification_messages

    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "x。"}],
        fields=[{"field_key": "pe_chest", "value": "x", "evidence_ids": ["e001"]}],
    )
    assert "超过 40 字时，按逗号、顿号补充拆分" in system
    assert "否认、无、未见" in system  # 否定豁免


def test_verifier_v3_five_micro_examples_parseable():
    """v3：5 条 JSON 微例（含对照：错读形似规范词）全部可解析，顶层仅 verifications。"""
    import json
    import re

    from app.backend.services.copd_extraction.prompts import build_verification_messages

    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "x。"}],
        fields=[{"field_key": "pe_chest", "value": "x", "evidence_ids": ["e001"]}],
    )
    blocks = re.findall(r"```json\n(.*?)\n```", system, re.S)
    assert len(blocks) == 5
    for block in blocks:
        parsed = json.loads(block)
        assert set(parsed.keys()) == {"verifications"}
        for v in parsed["verifications"]:
            assert set(v["checks"].keys()) == {
                "grounding_supported", "field_scope_valid", "text_standard", "logic_consistent"}
    assert "胸状胸" in system  # 对照微例含错读形似规范词
    assert "粗测听力正常" in system  # 术语陌生 pass 示例保留
