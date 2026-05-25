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
field_key, original_value, source_hint, evidence, confidence, source_section, extraction_status, verification_status, quality_flags, ocr_correction。

规则：
- 未抽到字段 original_value=""、evidence=null、extraction_status="not_found"。
- 抽到字段必须输出 source_hint，source_hint 使用 OCR 分段标题，例如 主诉、现病史、既往史、体格检查、辅助检查。
- evidence 可以保留 OCR 原文片段；如果不确定，不要编造 evidence。
- verification_status 初始为 "not_checked"。

OCR 分段文本：
{json.dumps(sections, ensure_ascii=False)}
""".strip()


def build_section_group_extraction_prompt(group_name: str, text: str, field_keys: list[str]) -> str:
    return f"""
你是一个严谨的慢阻肺/呼吸系统入院记录结构化抽取引擎，只处理 `{group_name}` 相关内容。
只从提供的 OCR 原文中抽取字段，不得推断、补全或改写原文未写的信息。
字段 key 只允许使用：{json.dumps(field_keys, ensure_ascii=False)}

输出必须是 JSON 对象，顶层键为 `fields`，`fields` 是数组。
每个字段只输出：field_key, original_value, source_hint。

规则：
- 找不到的字段可以省略；后端会补成 not_found。
- original_value 必须简短，只保留字段值本身。
- source_hint 必须是字段值所在的 OCR 章节标题，例如 主诉、现病史、既往史、体格检查、辅助检查；不能输出 history_profile、physical_exam、auxiliary_exam 这类内部分组名。
- 如果字段值看似可抽取但无法确定 OCR 原文来源，source_hint 输出 "未找到证据"，不要编造章节。
- 药物、合并症、体征等多项内容用顿号或分号压缩，不要输出长段原文。
- 不要输出 evidence、confidence、source_section、quality_flags、ocr_correction 等元数据。

OCR 原文：
{text}
""".strip()


def build_source_hint_regeneration_prompt(
    text: str,
    field_keys: list[str],
    allowed_source_hints: list[str],
    fields: list[dict],
) -> str:
    return f"""
你需要重新生成字段来源指向。下面的上一轮字段 JSON 是后端显式传入的输入，不依赖对话历史。
只允许输出 JSON 对象，顶层键为 `fields`，`fields` 是数组。
每个字段只输出：field_key, original_value, source_hint。

硬约束：
- field_key 只允许使用：{json.dumps(field_keys, ensure_ascii=False)}
- source_hint 只能从这个列表中选择：{json.dumps(allowed_source_hints + ["未找到证据"], ensure_ascii=False)}
- 不能输出 history_profile、physical_exam、auxiliary_exam 这类内部分组名。
- 如果 OCR 原文中找不到能支撑字段值的章节，source_hint 必须输出 "未找到证据"，不能编造。
- 不要输出 evidence、confidence、source_section、quality_flags、ocr_correction 等元数据。

OCR 原文：
{text}

上一轮字段：
{json.dumps(fields, ensure_ascii=False)}
""".strip()


def build_verification_prompt(source_groups: list[dict]) -> str:
    return f"""
你是字段级复核器。逐字段检查字段值是否能被同组 OCR 来源段落支持。
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含 field_key, verdict, reason_code, checks, comment。
verdict 只能是 pass、suspicious、fail。
reason_code 只能是 original_text_ambiguous、low_ocr_quality、extraction_error、unreliable_result、source_section_not_found、none。
checks 必须包含 source_text_supported、numeric_value_preserved、negation_preserved、section_assignment_reasonable。

来源分组：
{json.dumps(source_groups, ensure_ascii=False)}
""".strip()
