import json


def build_extraction_prompt(sections: dict[str, str], field_keys: list[str]) -> str:
    return f"""
你是慢阻肺/呼吸系统入院记录结构化抽取引擎。
只从 OCR 原文中抽取字段，不得推断原文未写的信息。
字段 key 必须完整覆盖：{json.dumps(field_keys, ensure_ascii=False)}

OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、单位断裂、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason。

输出必须是 JSON 对象，顶层键为 `fields`，`fields` 是数组。每个字段包含：
field_key, original_value, evidence, confidence, source_section, extraction_status, verification_status, quality_flags, ocr_correction。

规则：
- 未抽到字段 original_value=""、evidence=null、extraction_status="not_found"。
- 抽到字段必须保留 OCR 原文 evidence。
- verification_status 初始为 "not_checked"。

OCR 分段文本：
{json.dumps(sections, ensure_ascii=False)}
""".strip()


def build_verification_prompt(original_text: str, field_results: list[dict]) -> str:
    return f"""
你是字段级复核器。逐字段检查 value/evidence/OCR 纠偏是否可靠。
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含 field_key, verdict, checks, comment。
verdict 只能是 pass、suspicious、fail。
checks 必须包含 evidence_supported、ocr_correction_reasonable、numeric_value_preserved、negation_preserved、section_assignment_reasonable。

原始 OCR 文本：
{original_text}

字段结果：
{json.dumps(field_results, ensure_ascii=False)}
""".strip()
