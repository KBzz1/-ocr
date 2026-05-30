import json

COPD_EXTRACTION_PROMPT_VERSION = "copd_extraction_prompt.v1"


def build_extraction_prompt(sections: dict[str, str], field_keys: list[str]) -> str:
    return f"""
你是慢阻肺/呼吸系统入院记录结构化抽取引擎。
只从 OCR 原文中抽取字段，不得推断原文未写的信息。
字段 key 必须完整覆盖：{json.dumps(field_keys, ensure_ascii=False)}

OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、药名和医学词近形/同音/缺字错读、单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason。
如果把 P62、P02、PC02 等疑似错读标签理解为 PO2/PaO2/PCO2/PaCO2，必须保留原始 evidence，并在 ocr_correction 中记录原始标签和标准标签；没有把握时将 verification_status 置为 "suspicious" 并添加 quality_flags。
如果把嗜托溴铵理解为噻托溴铵、二程丙苯碱理解为二羟丙茶碱等药名纠偏，必须记录 ocr_correction；没有把握时标记 suspicious。
如果同一字段在 evidence 中出现前后矛盾数值，例如脉搏：9次/分但后文心率99次/分，不得自行选择一个确定值，应标记 suspicious。

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

OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、药名和医学词近形/同音/缺字错读（例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱）、单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把"无、否认、未见、可能、考虑、建议复查"等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason；没有纠偏时 applied=false。
如果同一字段在证据中出现前后矛盾数值，例如脉搏：9次/分但后文心率99次/分，属于前后矛盾数值，不得静默选值，应降低 confidence 并保留原始 evidence_phrase。

输出必须是 JSON 对象，顶层键为 `fields`，`fields` 是数组。
每个字段输出：field_key, original_value, source_hint, evidence_phrase, confidence, ocr_correction。

规则：
- 找不到的字段可以省略；后端会补成 not_found。
- original_value 必须简短，只保留字段值本身。
- source_hint 必须是字段值所在的 OCR 章节标题，例如 主诉、现病史、既往史、体格检查、辅助检查；不能输出 history_profile、physical_exam、auxiliary_exam 这类内部分组名。
- 如果字段值看似可抽取但无法确定 OCR 原文来源，source_hint 输出 "未找到证据"，不要编造章节。
- evidence_phrase 必须是支撑字段值的 OCR 原文短片段，不超过50字；必须保留原文写法，不要输出整段章节。
- 药物、合并症、体征等多项内容用顿号或分号压缩，不要输出长段原文。
- 不要输出 source_section、quality_flags 等其他元数据。

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


def build_verification_prompt(source_groups: list[dict], document_context: str = "") -> str:
    return f"""
你是字段级复核器。
问题：逐字段判断字段值是否能被提供的 OCR 事实支持。
事实：
- 原始 OCR 上下文：{document_context or "未提供"}
- 来源分组中的 source_text 是主要证据；原始 OCR 上下文只用于理解同一病历的局部语境。

只能根据 OCR 事实判断，不得使用医学常识补全、不得修改字段值、不得把否定或不确定表述改成确定阳性。
必须检查 OCR 纠偏是否合理；血气项目名前缀出现 P62、P02、PC02 等疑似错读但字段被归入 PO2/PaO2/PCO2/PaCO2 时，若缺少合理 ocr_correction 或 evidence 仍不清晰，verdict 输出 suspicious，reason_code 输出 low_ocr_quality。
药名、医学词和单位符号也必须检查 OCR 纠偏合理性，例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱、+10^9/L/×10^9/L。若字段值看起来依赖错读纠偏但未说明，输出 suspicious。
同一字段附近出现前后矛盾数值时，例如脉搏：9次/分但同段另有心率99次/分，输出 suspicious，不得静默选值。
体重下降/体重减轻字段若输出 0g、0kg、0克等数值，与字段含义明显矛盾；例如体重减轻0g 应输出 suspicious，并提示核对原文，不得主动改成其他数值。
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含 field_key, verdict, reason_code, checks, comment。
comment 不超过 20 个汉字，只写必要原因；通过项可以写 "一致"。
verdict 只能是 pass、suspicious、fail。
reason_code 只能是 original_text_ambiguous、low_ocr_quality、extraction_error、unreliable_result、source_section_not_found、none。
checks 必须是对象，且包含 source_text_supported、ocr_correction_reasonable、numeric_value_preserved、negation_preserved、section_assignment_reasonable。

来源分组：
{json.dumps(source_groups, ensure_ascii=False)}
""".strip()
