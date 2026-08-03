"""Stable prompts for fixed-field extraction and field-level verification.

The prompts deliberately keep the long OCR stream as text with stable evidence
IDs.  JSON is used only for the small verifier claim manifest; response shape
is constrained separately through ``response_format=json_schema``.
"""
from __future__ import annotations

import json

from .field_policies import (
    NORMAL_JUDGEMENT_FIELD_KEYS,
    POLICY_DEFINITIONS,
    POLICY_D,
    POLICY_J,
    POLICY_T,
    field_policy,
)

ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION = "extractor.v4"
# 复核器 prompt 版本（2026-08-04 verifier.v3 定稿：表述规范性契约 + 术语陌生判别 + 对照微例 + 逗号级拆句；仅作追踪标识，不渲染进 prompt）。
VERIFIER_PROMPT_VERSION = "verifier.v3"

# 兼容别名：J 集合真源已迁移到 field_policies，保留历史符号避免外部引用漂移。
_NORMAL_JUDGEMENT_FIELD_KEYS = NORMAL_JUDGEMENT_FIELD_KEYS

_HPI_TIME_SCOPES = {
    "hpi_initial_onset": "首次/最初发病；不吸收后续加重或近期表现",
    "hpi_subsequent_course": "首次发病后的反复、进展和就诊过程；不吸收首次或近期表现",
    "hpi_hospital_diagnosis": "住院期间原文已写出的诊断或检查结论",
    "hpi_treatment_medications": "现病史中实际记录的药物和治疗措施",
    "hpi_recent_symptoms": "本次或近期加重、近期症状和伴随表现",
}

_GROUP_RULES = {
    "chief_complaint": "只取主诉中直接记录的症状、持续时间和加重时间。",
    "history_of_present_illness": "只取现病史；按字段特有时间范围归属，不用常识补齐。",
    "past_medical_history": "只取既往疾病、治疗、手术、输血、过敏等原文；保留否认作用域。",
    "personal_history": "只取个人史、职业、吸烟和饮酒等原文。",
    "family_history": "只取家族史原文，不由疾病常识推断。",
    "physical_examination": "只取对应查体部位或生命体征；不吸收一般情况和邻近部位。",
    "ancillary_tests": "只取对应检查项目及其原文数值、单位和结论；明确带检查标签和值的结果可以出现在辅助检查章节或现病史中；仍禁止从诊断、症状或医学常识反推数值。",
    "diagnosis": "只取原文诊断；保留编号和顺序，不推断、合并或改写。",
}

# Compact definitions used by the verifier claim manifest when a candidate does
# not carry a richer schema description.  These are prompt context, not a
# second medical rule engine.
_VERIFIER_SCOPE_HINTS = {
    "hpi_initial_onset": "现病史/首次发病",
    "hpi_subsequent_course": "现病史/后续反复、进展和就诊",
    "hpi_recent_symptoms": "现病史/近期症状和加重",
    "hpi_hospital_diagnosis": "现病史/住院诊断或检查结论",
    "hpi_treatment_medications": "现病史/治疗药物和措施",
    "pe_skin": "体格检查/皮肤：颜色、皮疹、弹性、毛发、淋巴结；排除一般情况",
    "pe_eyes": "体格检查/眼部：结膜、巩膜、角膜、瞳孔、视力；排除颜面、耳鼻口颈",
    "pe_ears": "体格检查/耳部：外耳道、鼓膜、听力、乳突；排除眼、鼻、口咽",
    "pe_nose": "体格检查/鼻部：鼻腔、鼻窦、鼻翼、鼻通气；排除耳、口腔",
    "pe_oral_cavity": "体格检查/口腔：唇、齿、龈、舌、黏膜、咽、扁桃体；排除耳鼻和颈部",
    "pe_neck": "体格检查/颈部：颈静脉、颈动脉、甲状腺、气管、颈软；排除口腔和胸部",
    "pe_chest": "体格检查/胸廓：胸廓形态、肋间隙、胸骨、挤压试验；排除双肺和乳房",
    "pe_breast": "体格检查/乳房：对称、发育、乳头、皮肤、包块；排除胸廓和双肺",
    "pe_respiratory_exam": "体格检查/呼吸系统：呼吸动度、语颤、叩诊音、呼吸音、啰音；排除胸廓形态",
    "pe_cardiac_exam": "体格检查/心脏：心前区、心尖搏动、心界、心率、心律、心音、杂音",
    "pe_abdomen": "体格检查/腹部：腹壁、压痛、肝脾、移动性浊音、Murphy征",
    "pe_limbs": "体格检查/四肢：脊柱、关节、肌力、水肿、静脉曲张、病理征",
    "pe_neurological_exam": "体格检查/神经：神志、精神、对答、反射、病理征；排除一般情况",
}


def _render_evidence_unit(unit: dict, index: int = 0) -> str:
    """Render one unit with its original ID and no second order namespace."""
    unit_id = unit.get("id") or "<missing-id>"
    return f"[{unit_id}] {unit.get('text', '')}"


def _render_evidence_stream(evidence_units: list[dict] | None) -> str:
    """Render the original evidence stream once, grouped without renumbering."""
    units = [unit for unit in evidence_units or [] if isinstance(unit, dict)]
    if not units:
        return "（未提供证据；不得凭空生成字段）"

    page_values = {unit.get("page_no") for unit in units if unit.get("page_no") is not None}
    show_page_markers = len(page_values) > 1
    lines: list[str] = ["<document>"]
    current_section = None
    current_page = object()
    for index, unit in enumerate(units, 1):
        section = unit.get("section_hint") or unit.get("section_key") or ""
        if section != current_section:
            if current_section:
                lines.append("</section>")
            if section:
                lines.append(f'<section key="{section}">')
            current_section = section
        page = unit.get("page_no")
        if show_page_markers and page != current_page:
            lines.append(f'<page no="{page if page is not None else "unknown"}"/>')
            current_page = page
        lines.append(_render_evidence_unit(unit, index))
    if current_section:
        lines.append("</section>")
    lines.append("</document>")
    return "\n".join(lines)


def verifier_field_definition(field_key: str, field_label: str = "") -> str:
    """Return a compact, non-persisted definition for a verifier claim."""
    return _VERIFIER_SCOPE_HINTS.get(field_key) or field_label or field_key


# verifier.v3 五例 JSON 微例：三类核心 + 术语陌生 pass + 错读形似规范词对照；示例
# ID u911-u913 为虚拟证据 ID，不属于正式输入；每个示例只展示一条 verification，
# 不提供 61 字段完整输出。示例表达错误形态，不构成"见到某字就标"的词表规则。
_VERIFIER_EXAMPLES = """1. 正确且有据 → pass
```json
{"verifications":[{"field_key":"pe_respiratory_exam","verdict":"pass","reason_code":"none","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":true,"logic_consistent":true},"comment":"一致"}]}
```
2. 原文支持但字段越界 → suspicious/extraction_mistake
```json
{"verifications":[{"field_key":"pe_eyes","verdict":"suspicious","reason_code":"extraction_mistake","checks":{"grounding_supported":true,"field_scope_valid":false,"text_standard":true,"logic_consistent":true},"comment":"u911 原文属一般情况，不属眼部"}]}
```
3. 抽取忠实但证据存在可定位非标准表述 → suspicious/nonstandard_expression
```json
{"verifications":[{"field_key":"pe_neurological_exam","verdict":"suspicious","reason_code":"nonstandard_expression","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":false,"logic_consistent":true},"comment":"u912 原文'古手'非标准表述，疑为'左手'错读"}]}
```
4. 术语陌生（如"粗测听力正常"，规范用词但少见）但文本完整明确，不因不熟悉用词误报 → pass
```json
{"verifications":[{"field_key":"pe_ears","verdict":"pass","reason_code":"none","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":true,"logic_consistent":true},"comment":"一致"}]}
```
5. 对照：错读但形似规范词（如"胸状胸"疑为"桶状胸"）→ suspicious/nonstandard_expression
```json
{"verifications":[{"field_key":"pe_chest","verdict":"suspicious","reason_code":"nonstandard_expression","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":false,"logic_consistent":true},"comment":"u913 原文'胸状胸'非标准表述，疑为'桶状胸'错读"}]}
```

示例仅展示结构与裁定边界；示例 ID u911-u913 不属于正式输入，禁止复制到输出。"""


def build_verification_messages(
    evidence_units: list[dict], fields: list[dict], append_reminder: bool = False,
) -> tuple[str, str]:
    """Build the verifier's fixed system prompt and variable evidence packet."""
    system = """你是慢阻肺入院记录的字段级复核器。你只核验给定字段是否被给定 OCR 证据支持，不改写字段值、不补造证据、不提供医学建议。

【固定审核顺序】
1. grounding：先在 cited evidence 中核对声称值；完整值不连续时按句号、分号或换行拆成事实片段，再逐片段核对。value 超过 40 字时，按逗号、顿号补充拆分；含"否认、无、未见"的片段不拆。普通短 value 的逗号、顿号列表不拆开。
2. field scope：检查内容是否属于该字段定义的部位、项目和时间范围；原文支持但字段越界仍应标记。
3. 表述规范性：只检查证据中确实可定位的非标准表述（错读、病句、残缺、标签或单位问题），不归因于 OCR、不要求给出修正词。术语陌生（规范医学/日常用词但少见，如"粗测听力"）不构成问题；非任何标准用词或形近/音近标准词 → 必须标记。正确用字、符合规范的表述不得标记；值忠实摘录原文不豁免表述检查——值一致只证明抄得对，不证明文本本身没问题。
4. logic consistency：检查否定/不确定、时间归属、数值关系和字段内部是否自相矛盾；值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥、数值关系不合理）→ 均应标记；不能从常识补出证据不存在的事实。
5. verdict：四项检查全部通过才 pass；任何一项明确失败才 suspicious。调用方已在请求前检查 cited ID 是否完整，证据装配缺失不归因于字段。

【判定与原因】
- grounding、字段越界、时间归属、否定翻转或逻辑矛盾 → reason_code=extraction_mistake。
- 可定位的非标准表述 → reason_code=nonstandard_expression。
- 术语陌生（规范用词但少见）、写法不常见、轻微格式或正常有序聚合，不构成明确问题 → pass。
- 术语陌生与非标准表述的判别：术语陌生是规范医学/日常用词（如"粗测"），不标；非任何标准用词或形近/音近标准词（如"胸状胸"→"桶状胸"、"古手"→"左手"），是错读 → 必须标，标注时不需要给出正确词。
- pass 的 reason_code 必须为 none；不要把语义等价、多个有序证据片段聚合或正常族归一误报为问题。
- 只生成 pass 或 suspicious。历史数据可能含 fail，解析器会兼容，但本次不要生成 fail。

【输出契约】
输出单个 JSON 对象，顶层只有 verifications。数组与输入字段一一对应，不能重复、遗漏或新增字段。每项固定包含：
- field_key：输入字段 key；verdict：pass 或 suspicious；reason_code：extraction_mistake、nonstandard_expression 或 none。
- checks：只包含 grounding_supported、field_scope_valid、text_standard、logic_consistent 四个布尔值。
- pass 必须四项 checks 全 true 且 reason_code=none；suspicious 必须至少一项 check=false 且 reason_code 不是 none。
- nonstandard_expression 必须对应 text_standard=false；extraction_mistake 必须对应 grounding_supported/field_scope_valid/logic_consistent 至少一项 false。
- comment：不超过 40 个汉字。pass 写"一致"；suspicious 必须引用本请求实际存在的 uXXX 和具体疑点。

【示例】
""" + _VERIFIER_EXAMPLES

    claims: list[dict] = []
    for field in fields or []:
        label = field.get("definition") or field.get("field_label") or ""
        claims.append({
            "field_key": field.get("field_key", ""),
            "definition": verifier_field_definition(field.get("field_key", ""), label),
            "value": field.get("value", "") or "",
            "cited_ids": list(field.get("evidence_ids") or field.get("cited_ids") or []),
        })
    user = (
        "<evidence>\n"
        + _render_evidence_stream(evidence_units)
        + "\n</evidence>\n<claims>\n"
        + json.dumps({"claims": claims}, ensure_ascii=False, separators=(",", ":"))
        + "\n</claims>"
    )
    if append_reminder:
        user += "\n再次检查：每个 verdict 的 field_key 必须来自 claims，引用必须来自上面的 [uXXX]。"
    return system, user


def build_adversarial_verification_prompt(source_groups: list[dict], document_context: str = "") -> str:
    """Compatibility prompt for the legacy adversarial verifier."""
    return f"""
你是字段抽取的对抗性复核器。只报告能够在给定证据中定位的明确疑点，不补造原文或医学事实。
逐字段检查：grounding、字段范围、OCR 清晰度、否定/数值/时间逻辑。
输出 JSON 对象，顶层键为 issues。每项包含 field_key、problem_type、description、severity；description 不超过 60 个汉字。
原始 OCR 上下文：{document_context or "未提供"}
来源分组：
{json.dumps(source_groups, ensure_ascii=False)}
""".strip()


def _field_line(field: dict, group_key: str) -> str:
    """Render one catalog row: field_key｜中文名｜P=T/J/D｜特有边界（如有）。"""
    key = field.get("field_key", "")
    label = field.get("label", key)
    parts = [key, label, f"P={field_policy(field, group_key)}"]
    boundary: list[str] = []
    description = (field.get("description") or "").strip()
    if description:
        boundary.append(description)
    if group_key == "history_of_present_illness" and key in _HPI_TIME_SCOPES:
        boundary.append(_HPI_TIME_SCOPES[key])
    if boundary:
        parts.append("；".join(boundary))
    return "｜".join(parts)


def _render_field_catalog(schema: dict) -> tuple[str, list[str]]:
    blocks: list[str] = []
    field_keys: list[str] = []
    for group in schema.get("field_groups", []) or []:
        group_key = group.get("group_key", "")
        group_label = group.get("group_label", group_key)
        blocks.append(f"【{group_label}】\n共同规则：{_GROUP_RULES.get(group_key, '只取该章节原文。')}")
        for field in group.get("fields", []) or []:
            key = field.get("field_key", "")
            field_keys.append(key)
            blocks.append(_field_line(field, group_key))
    return "\n".join(blocks), field_keys


# Three frozen local JSON micro-examples (PPEMA-V1 §4.3).  They show partial
# ``output_fields`` judgment boundaries only; example IDs u901-u903 belong to
# the examples alone and must never leak into real output.  The strict
# ``json_schema`` response format still constrains the real 61-field payload.
_EXTRACTION_EXAMPLES = """1. 共享否定作用域：同一合成证据同时支持一个 T 字段的否定摘录和一个 J 字段的“正常”，两者均 found 并引用同一 ID。
```json
{"output_fields": [
  {"field_key": "pmh_cardiac_disease", "status": "found", "value": "否认心脏病史", "evidence_ids": ["u901"]},
  {"field_key": "pe_eyes", "status": "found", "value": "正常", "evidence_ids": ["u901"]}
]}
```

2. J 型异常优先：合成心脏查体同时有异常与正常描述，输出只保留异常片段，不因出现“正常”而折叠。
```json
{"output_fields": [
  {"field_key": "pe_cardiac_exam", "status": "found", "value": "心率104次/分，心尖区可闻及2/6级收缩期杂音", "evidence_ids": ["u902"]}
]}
```

3. 禁止推导 BMI：合成证据只有身高和体重，二者 found；BMI 必须 not_found、value 为空、evidence_ids 为空。
```json
{"output_fields": [
  {"field_key": "pe_height", "status": "found", "value": "170cm", "evidence_ids": ["u903"]},
  {"field_key": "pe_weight", "status": "found", "value": "70kg", "evidence_ids": ["u903"]},
  {"field_key": "pe_bmi", "status": "not_found", "value": "", "evidence_ids": []}
]}
```"""


def build_admission_structured_fields_messages(
    schema: dict,
    evidence_units: list[dict],
    document_text: str = "",
    append_reminder: bool = False,
) -> tuple[str, str]:
    """Return ``(system, user)`` for fixed-field extraction.

    Evidence units are the sole document stream.  A legacy caller that supplies
    only ``document_text`` gets one wrapped unit, not a duplicated OCR stream.
    """
    units = list(evidence_units or [])
    if not units and document_text:
        units = [{"id": "u001", "text": document_text, "page_no": 1}]
    field_catalog, field_keys = _render_field_catalog(schema)

    system = f"""你是慢阻肺/呼吸系统入院记录结构化抽取助手。只能根据有序 OCR 证据抽取固定字段；不得诊断、推理、纠正 OCR、补写证据或改变原文顺序。

【任务边界】
从证据头到尾阅读，按原始 [uXXX] 顺序理解上下文，不重排页序。每个字段只读取字段目录规定的章节、部位和时间范围。原文明确的事实可以被多个字段引用，共享同一证据合法；多个证据单元可以按原文顺序聚合。
保留否定词“否认、无、未见”，禁止把否定翻转为阳性。

【状态判定】
- found（status="found"）：原文语义明确出现该字段事实；value 非空，并引用一个或多个真实 [uXXX]。
- not_found（status="not_found"）：证据完全没有该字段事实；value=""，evidence_ids=[]。
- uncertain（status="uncertain"）：存在疑似片段，但 OCR、时间归属或字段归属仍不能确定；不得用医学常识补齐。

【取值策略】
每个字段在字段目录中携带一个取值策略标记（T/J/D），定义如下：
- {POLICY_DEFINITIONS[POLICY_T]}
- {POLICY_DEFINITIONS[POLICY_J]}
- {POLICY_DEFINITIONS[POLICY_D]}

【字段目录】
每个字段一行，格式：field_key｜中文名｜P 标记｜特有边界（如有）。
{field_catalog}

【三个局部判定示例】
示例只展示局部 output_fields 判断边界，不是完整顶层响应；示例 ID u901-u903 只属于示例，正式输出禁止使用。正式输出仍须覆盖字段目录中的全部字段。
{_EXTRACTION_EXAMPLES}"""

    user = (
        _render_evidence_stream(units)
        + "\n\n请依据 system 中的任务边界、状态判定、取值策略和字段目录输出 JSON。"
    )
    if append_reminder:
        user += "\n再次检查：只输出固定字段，evidence_ids 必须来自上面的 [uXXX]。"
    return system, user


def build_admission_structured_fields_prompt(
    schema: dict,
    evidence_units: list[dict],
    document_text: str = "",
) -> str:
    """Compatibility wrapper returning the two messages concatenated."""
    system, user = build_admission_structured_fields_messages(schema, evidence_units, document_text)
    return f"{system}\n\n{user}"
