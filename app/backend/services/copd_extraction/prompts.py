import json
import re

ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION = "admission_record_structured_fields_prompt.v1"

_LONG_FIELD_CHARS = 150
_SENTENCE_MAX_CHARS = 60


def _split_sentences(text: str, max_len: int = _SENTENCE_MAX_CHARS) -> list[str]:
    """长文本按句末标点拆句；单句仍超长时按逗号续拆（逐句核验用，不留空句）。"""
    chunks = [c for c in re.split(r"(?<=[。；;！？])", text) if c.strip()]
    sents: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_len:
            sents.append(chunk)
            continue
        for sub in re.split(r"(?<=[,，、])", chunk):
            if sub.strip():
                sents.append(sub)
    return sents or [text]

def build_verification_messages(
    evidence_units: list[dict], fields: list[dict], append_reminder: bool = False,
) -> tuple[str, str]:
    """复核器 prompt：(system, user)。evidence 在前、字段在后（防锚定）。

    system 完全固定（前缀缓存友好）：角色任务 2 句、通用原则 7 条、输出契约、few-shot。
    user 为变量：编号证据块 + 字段块。append_reminder=True（变体 B）时在 user
    末尾追加结构提醒句，位于前缀之后不影响前缀缓存；默认 False（变体 A）。
    """
    system = """你是字段级复核器。任务：对照编号证据（eXXX）核验已抽取字段值是否被 OCR 原文事实支持，输出 JSON verdict 意见。

先独立读证据再对照声称值，不顺着字段值找支撑。

【通用原则】
- 值与证据一致（语义等价即可）→ pass；证据可逐字定位的实质矛盾或文本确系 OCR 错读 → 标记。不编造理由标记（误报损害医生信任）；确凿问题不得以"证据与值一致"为由放行——证据与值同源，一致不能证明文本没错。
- 只标记可逐字定位的问题：每条 suspicious/fail 必须可逐字定位到证据单元文本中的原文依据；禁止编造原文、医学推断或补全、把否定或不确定表述改成确定阳性；不得标记值中已存在的内容（如值里已有"偏"字，不得说"删掉了'偏'字"）。
- OCR 识别错误：项目名/药名/单位近形错读（P62/P02、嗜托溴铵/噻托溴铵、+10^9/L/×10^9/L）及错读导致的病句、残缺用字均须标记为 ocr_quality_issue，提示原文片段即可，不要求给出修正值（纠偏由抽取环节负责）。对照医学规范用词逐字检查，常见模式而非全部：叠字如"舌舌居中"、近形替换如"回流证/回流征"、残缺如"古手/左手"。长文本字段按句拆分编号，必须逐句扫读全值，不得因整体语义通顺而放行。错读/病句/叠字等表达瑕疵：影响理解或产生歧义 → 必须标记；不影响语义理解的轻微重复可不标。值忠实摘录原文不豁免错读检查——值一致只证明抄得对，不证明文本本身没问题。
- 数值矛盾或逻辑不一致：同段存在与字段值不一致的数值、数值超出合理范围疑似 OCR 截断（99→9）、反直觉数值（体重下降 0g）；值内部自相矛盾、值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥）、数值关系不合理（如氧合指数与 PO2/FiO2 明显不符）→ 均应标记。
- 证据缺失/幻觉：字段值在证据单元中找不到对应文本，或引入 OCR 原文没有的信息、做医学推断，应标记。
- OCR 纠偏依据不充分：原始 OCR 文本与修正后值关系不合理、纠偏理由站不住，应标记。
- 字段越界：值的内容域与字段对应部位明显不符（如眼部字段出现一般情况内容）→ 标记为 extraction_mistake，引用原文片段即可。字段越界不因值有证据支持而豁免——证据同源只证明原文有这段话，不证明它属于该字段。

【输出契约】
输出 JSON 对象，顶层键 `verifications` 为数组，与字段一一对应（每个字段恰好一条，不重复、不遗漏）。每项包含：
- field_key：被审查字段的 key
- verdict：只能是 pass / suspicious / fail
- reason_code：只能是 ocr_quality_issue / extraction_mistake / evidence_insufficient / none（pass 固定为 none）
- checks：对象，包含 value_semantically_supported（值是否被证据语义支持）、no_hallucination_or_inference（是否引入原文外信息或医学推断）、ocr_correction_justified（纠偏理由是否充分）
- comment：不超过 40 个汉字；通过项写"一致"；suspicious/fail 必须引用具体证据编号（eXXX）和疑点描述

输出示例：
```json
{"verifications": [{"field_key": "pe_ear", "verdict": "pass", "reason_code": "none", "checks": {"value_semantically_supported": true, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "一致"}, {"field_key": "pe_pulse", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e002附近另有心率99次/分，疑与脉搏9次/分冲突"}]}
```
示例仅示范结构，字段内容为占位，不得照抄。

```json
{"verifications": [{"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e005 值忠实摘录原文，但'双眼粗侧视力正常'中'粗侧'为 OCR 错读（应为'粗测'）"}]}
```
示例仅示范结构，字段内容为占位，不得照抄。

```json
{"verifications": [{"field_key": "pe_abdomen", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e012 同段既有'腹部正常，肝脾肋缘下未扪及'，值却写'腹部移动性浊音阳性'，两处矛盾，疑否定翻转"}]}
```
示例仅示范结构，字段内容为占位，不得照抄。

反例（值正确，不得标记）：值完整摘录证据内容（即使顺序略有不同），复核员错误找茬 → 应为 pass：
```json
{"verifications": [{"field_key": "pe_lung", "verdict": "pass", "reason_code": "none", "checks": {"value_semantically_supported": true, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "一致"}]}
```"""

    evidence_blocks = [
        f"- {unit.get('id', '')}：{unit.get('text', '')}"
        for unit in evidence_units or []
    ]
    evidence_section = "\n".join(evidence_blocks) if evidence_blocks else "（未提供证据）"

    field_blocks = []
    for field in fields or []:
        fk = field.get("field_key", "")
        value = field.get("value", "")
        ids = ", ".join(str(i) for i in (field.get("evidence_ids") or []))
        if len(value) > _LONG_FIELD_CHARS:
            sents = _split_sentences(value)
            value_part = "（长文本已按句拆分，逐句检查）" + "".join(
                f"{i}「{s}」" for i, s in enumerate(sents, 1)
            )
        else:
            value_part = f"声称值 {value or '（空）'}"
        field_blocks.append(f"- {fk}：{value_part}；引用证据 {ids or '（无）'}")
    fields_section = "\n".join(field_blocks) if field_blocks else "（无字段）"

    user = f"""【OCR 原文证据（先读，编号引用）】
{evidence_section}

【字段声称值（后看，逐字段审查）】
{fields_section}"""
    if append_reminder:
        user += "\n\n请严格遵守 system prompt 中的【输出契约】【通用原则】【领域规则】。"
    return system, user


def build_adversarial_verification_prompt(source_groups: list[dict], document_context: str = "") -> str:
    """对抗性复核 prompt：要求 LLM 主动挑刺，直接输出问题列表。

    与常规复核不同，对抗性复核不要求 LLM 判断「是否正确」，
    而是要求 LLM 站在批评者角度**主动寻找可能存在的抽取问题**。
    输出直接作为 quality_flags 附加到字段，不经规则层过滤。
    """
    return f"""
你是字段抽取的对抗性复核器。你的任务是**主动发现抽取结果中可能存在的问题**，而非判断抽取是否正确。

对每个字段，逐一审视以下风险：

1. **数值截断/错读**：OCR 可能把多位数读成单数字（如 99→9、36.7→3.7），导致字段值异常。单数字脉搏/呼吸、极低体温等应特别关注。
2. **OCR 标签混淆**：检验项目名可能被 OCR 错读（P62→PaO2、BHI→BMI、P02→PO2、嗜托溴铵→噻托溴铵）；单位符号可能错读（+10^9/L→×10^9/L）。
3. **否定翻转风险**：evidence 中存在"无、否认、未见、可能、考虑、建议复查"等表述，但字段值被当作确定阳性抽取。
4. **证据缺失/幻觉**：字段值是否在 evidence 中找不到对应文本？是否引入了 OCR 原文没有的信息？
5. **数值矛盾**：同一字段的 evidence 中是否存在另一个与字段值不一致的数值（如脉搏 9 次/分但同段有心率 99 次/分）？
6. **医学推断过度**：字段值是否更像是 LLM 根据医学常识推断出来的，而非直接从 OCR 原文中提取？
7. **体重下降零值矛盾**：体重下降/减轻字段出现 0g、0kg、0 斤等反直觉数值。

输出 JSON 对象，顶层键为 `issues`，`issues` 是数组。每项必须包含：
- field_key：存在问题的字段 key
- problem_type：ocr_error / value_not_found / negation_risk / numeric_conflict / hallucination / medical_inference / zero_weight_loss
- description：不超过 60 个汉字的问题描述，须指明具体疑点
- severity：high / medium / low

**关键约束**：
- 只输出你**有明确疑点**的字段。如果字段抽取看起来合理，不要强行编造问题。
- 每个 issue 的 description 必须包含**具体的证据位置或数值**，不能泛泛而谈。
- 如果没有发现任何问题，输出空的 issues 数组。

原始 OCR 上下文：{document_context or "未提供"}

来源分组：
{json.dumps(source_groups, ensure_ascii=False)}
""".strip()


# ---------------------------------------------------------------------------
# 新固定字段 Qwen 提示词契约（Task 3+）
# ---------------------------------------------------------------------------
#
# 该 builder 是活动入院记录结构化抽取路径的唯一公开入口。
# 新契约核心：
# - 按 schema 固定字段表全量输出，不得自由生成 schema 外字段或二级 key。
# - Qwen 字段项只输出 field_key / status / value / evidence_ids；
#   章节、标签、审核状态和 evidence 详情由后端按 schema 与 evidence_units 回填。
# - evidence 用 evidence_ids（编号列表），不允许模型自行撰写 evidence 文本。
# - 严禁 OCR 文本修正、标题纠正（如把"品后诊断"改成"最后诊断"）和页序重排。
# - 诊断字段仅摘录原文记录，禁止主观医学判断、推断、补充或改写。
# - 允许多个字段共用同一条 evidence unit（特别是血气 6 项）。
# - 未找到字段返回 status="not_found", value="", evidence_ids=[]，不得省略。
#
# Task 1（ChatML 消息结构改造）：prompt 拆成 (system, user) 两段返回，
# system 只含身份/输出契约/通用原则/领域规则/固定字段表等固定文本
# （不含任何 evidence_units 或 document_text 变量数据），便于 vLLM 前缀
# 缓存命中；变量数据全部进 user。append_reminder 控制 user 尾部结构提醒句
# （变体 B），默认 False（变体 A）。


def build_admission_structured_fields_messages(
    schema: dict,
    evidence_units: list[dict],
    document_text: str = "",
    append_reminder: bool = False,
) -> tuple[str, str]:
    """返回 (system, user) 两段消息。

    system 固定承载身份/输出契约/通用原则/领域规则/固定字段表，完全不含
    evidence_units 与 document_text 变量数据（前缀缓存命中前提）；user
    承载证据单元与 OCR 原文。append_reminder=True（变体 B）时在 user 末尾
    追加结构提醒句，位于前缀之后不影响前缀缓存；默认 False（变体 A）。
    旧函数 build_admission_structured_fields_prompt 保留为兼容包装
    （两段拼接）。
    """
    schema_version = schema.get("version", "")
    document_type = schema.get("document_type", "")

    # ---- 1. 固定字段表 ----
    table_lines = []
    for group in schema.get("field_groups", []):
        group_key = group.get("group_key", "")
        group_label = group.get("group_label", "")
        for field in group.get("fields", []):
            field_key = field.get("field_key", "")
            field_label = field.get("label", "")
            description = field.get("description", "")
            if description:
                table_lines.append(
                    f"- [{group_key}/{group_label}] {field_key}（{field_label}）；仅：{description}"
                )
            else:
                table_lines.append(
                    f"- [{group_key}/{group_label}] {field_key}（{field_label}）"
                )
    fixed_field_table = "\n".join(table_lines)

    # ---- 2. 编号证据单元 ----
    unit_blocks = []
    for unit in evidence_units or []:
        unit_id = unit.get("id", "")
        unit_text = unit.get("text", "")
        unit_blocks.append(f"- {unit_id}：{unit_text}")
    evidence_units_section = "\n".join(unit_blocks) if unit_blocks else "（未提供 evidence_units）"

    if document_text:
        document_text_section = document_text
    elif evidence_units:
        document_text_section = "已由上方 evidence_units 按 OCR 原始顺序覆盖，本次不重复粘贴完整 OCR。"
    else:
        document_text_section = "（未提供 document_text）"

    system = f"""你是慢阻肺/呼吸系统入院记录结构化抽取助手。任务：读取编号证据单元与合并 OCR 原文，按固定字段表输出结构化抽取结果。

schema_version：{schema_version}
document_type：{document_type}

【输出契约】
- 输出必须是单个 JSON 对象，顶层键固定为 `schema_version`、`document_type`、`fields`，不得新增顶层键；`fields` 是数组，每个 schema 字段对应一项，不得增删。
- 字段状态枚举仅允许：`found` / `not_found` / `uncertain`。found：原文中明确出现该字段语义，`value` 非空、`evidence_ids` 应非空；not_found：原文未提及该字段，必须输出 `status="not_found"`、`value=""`、`evidence_ids=[]`，不得省略字段；uncertain：疑似找到但 OCR 或上下文不确定，`value` 可空、`evidence_ids` 可空。
- 每项字段固定输出四键：field_key、status、value、evidence_ids。field_key 只允许使用"固定字段表"中的 key，禁止自由生成 schema 外字段或二级 key；字段顺序按固定字段表顺序输出，便于后端对齐；章节、字段标签、审核状态由后端按 schema 回填，模型不得重复输出。
- `evidence_ids` 必须是字符串列表（list[str]），只允许从"证据单元编号"中选择现有 ID，禁止编造 ID 或自填 evidence 文本。

输出示例：
```json
{{
  "schema_version": "{schema_version}",
  "document_type": "{document_type}",
  "fields": [
    {{
      "field_key": "chief_complaint",
      "status": "found",
      "value": "反复咳嗽、咳痰15年，喘息6年，加重1月。",
      "evidence_ids": ["u009"]
    }},
    {{
      "field_key": "hpi_initial_onset",
      "status": "not_found",
      "value": "",
      "evidence_ids": []
    }}
  ]
}}
```

【通用原则】
- 只摘录 OCR 原文可定位的语义片段，禁止医学推断、补全、合并、重写。
- 不得静默修正 OCR 文本（数值、单位、标签疑似错读如 P62/P02、10^9/L 与 ×10^9/L 保持原文），不得重排页序。
- 保留否定词（否认/无/未见），禁止翻转；字段被明确否定时 `value` 保留否定表述。
- 诊断字段只摘录原文已写出的诊断，禁止主观判断、推断、合并、添加；诊断编号列表项按编号分行保留，不得合并成一句或丢失编号。
- 允许多个字段共用同一条证据单元（血气 6 项通常共享）。

【领域规则】
- 字段边界：每个字段只抽取字段表对应部位/项目的内容；字段表未收录的内容（如一般情况：发育/营养/体型/神志/表情/体位）不写入任何字段、不引用为证据。
- J 型判定：qwen_type 为 J 或 review_control 为 judgement 的字段（体格检查部位/项目）：原文明确正常或阴性（正常、未见异常、无压痛等）时输出 `status="found"`、`value="正常"`，不得因阴性描述输出 not_found；异常时输出 `status="found"`，`value` 摘录原文的具体异常描述；原文完全未提及时输出 `status="not_found"`、`value=""`；不确定时输出 `status="uncertain"`。

【固定字段表】
{fixed_field_table}"""

    user = f"""【证据单元编号（每条对应 OCR 原文片段，仅按 ID 引用）】
{evidence_units_section}

【合并 OCR 原文（仅供上下文理解，不作为 evidence_ids 选择依据）】
{document_text_section}"""
    if append_reminder:
        user += "\n\n请严格遵守 system prompt 中的【输出契约】【通用原则】【领域规则】。"
    return system, user


def build_admission_structured_fields_prompt(
    schema: dict,
    evidence_units: list[dict],
    document_text: str = "",
) -> str:
    """兼容包装：返回 system 与 user 两段拼接后的整体字符串，旧调用方继续可用。"""
    system, user = build_admission_structured_fields_messages(
        schema, evidence_units, document_text
    )
    return f"{system}\n\n{user}"
