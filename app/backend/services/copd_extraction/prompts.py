import json

ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION = "admission_record_structured_fields_prompt.v1"

_OCR_RISK_WARNINGS = (
    "OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、"
    "血气项目名 P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 混淆、"
    "药名和医学词近形/同音/缺字错读（例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱）、"
    "单位断裂、单位符号错读（例如 +10^9/L 可能是 ×10^9/L）、"
    "表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。"
    "硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；"
    "不得把“无、否认、未见、可能、考虑、建议复查”等表达改成确定阳性。"
)


def build_verification_prompt(source_groups: list[dict], document_context: str = "") -> str:
    return f"""
你是字段级复核器。
任务：逐字段判断字段值是否能被提供的 OCR 事实支持。
事实：
- 原始 OCR 上下文：{document_context or "未提供"}
- 来源分组中的 source_text 是主要证据；原始 OCR 上下文只用于理解同一病历的局部语境。

只能根据 OCR 事实判断，不得使用医学常识补全、不得修改字段值、不得把否定或不确定表述改成确定阳性。
必须检查 OCR 纠偏是否合理；血气项目名前缀出现 P62、P02、PC02 等疑似错读但字段被归入 PO2/PaO2/PCO2/PaCO2 时，若缺少合理 ocr_correction 或 evidence 仍不清晰，verdict 输出 suspicious，reason_code 输出 ocr_quality_issue。
药名、医学词和单位符号也必须检查 OCR 纠偏合理性，例如嗜托溴铵/噻托溴铵、二程丙苯碱/二羟丙茶碱、+10^9/L/×10^9/L。若字段值看起来依赖错读纠偏但未说明，输出 suspicious。
同一字段附近出现前后矛盾数值时，例如脉搏：9次/分但同段另有心率99次/分，输出 suspicious，不得静默选值。
体重下降/体重减轻字段若输出 0g、0kg、0克等数值，与字段含义明显矛盾；例如体重减轻0g 应输出 suspicious，并提示核对原文，不得主动改成其他数值。
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含 field_key, verdict, reason_code, checks, comment。
comment 不超过 40 个汉字，只写必要原因；通过项可以写 "一致"。
verdict 只能是 pass、suspicious、fail。
reason_code 只能是 ocr_quality_issue、extraction_mistake、evidence_insufficient、none。
checks 必须是对象，且包含：
- value_semantically_supported：字段值的语义是否被 OCR 事实支持（而非仅数值是否出现）
- no_hallucination_or_inference：是否引入了 OCR 中没有的信息或做了医学推断
- ocr_correction_justified：如有 OCR 纠偏，理由是否充分、原始 OCR 文本与修正后值的关系是否合理

来源分组：
{json.dumps(source_groups, ensure_ascii=False)}
""".strip()


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


def build_admission_structured_fields_prompt(
    schema: dict,
    evidence_units: list[dict],
    document_text: str = "",
) -> str:
    """按 admission_record_structured_fields.v1 schema 构建 Qwen 结构化抽取 prompt。

    Args:
        schema: schema_loader.load_schema 规范化后的 dict，包含
            version / document_type / field_groups。
        evidence_units: 后端生成的轻量证据单元列表，每项包含 id / text，
            可选 start_offset / end_offset / page_no / section_key。
        document_text: 合并后的 OCR 原文。正常路径同时提供完整 OCR 上下文
            与 evidence_units，便于模型理解跨片段语境但只通过 evidence_ids 定位。

    Returns:
        完整的 Qwen prompt 字符串。
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

    return f"""
你是慢阻肺/呼吸系统入院记录结构化抽取助手，使用固定字段表对 OCR 原文做结构化抽取。

schema_version：{schema_version}
document_type：{document_type}

【硬约束 — 输出 JSON 形状】
输出必须是单个 JSON 对象，顶层键固定为 `schema_version`、`document_type`、`fields`，不得新增顶层键。`fields` 是数组，每个 schema 字段对应一项，不得增删。

字段状态枚举仅允许：`found` / `not_found` / `uncertain`。
- found：原文中明确出现该字段语义，`value` 非空，`evidence_ids` 应非空。
- not_found：原文未提及该字段，必须输出 `status="not_found"`、`value=""`、`evidence_ids=[]`，不得省略字段。
- uncertain：疑似找到但 OCR 或上下文不确定，需要医生重点核验；`value` 可空，`evidence_ids` 可空。

每项字段输出固定包含：field_key、status、value、evidence_ids。后端按 schema 回填章节、字段标签、审核状态和 evidence 详情，模型不要重复输出 section_key、section_label、field_label 或其他字段。`evidence_ids` 必须是字符串列表（list[str]），只允许从下方"证据单元编号"中选择现有 ID，不允许编造或自填 evidence 文本。

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
      "evidence_ids": ["u001"]
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

【硬约束 — 字段与 key】
- field_key 只允许使用下方"固定字段表"中的 key；禁止输出 schema 外字段；禁止自由生成二级 key、二级字典或额外字段。
- 字段章节和字段标签由后端按固定字段表回填；模型输出中禁止重复 section_key、section_label、field_label。
- 字段顺序按固定字段表顺序输出，便于后端对齐。

【硬约束 — evidence 与原文】
- evidence_ids 只允许从下方编号证据单元中选择，禁止编造 ID；找不到支撑证据时使用 `evidence_ids=[]`。
- 不允许在 value 或 evidence_ids 之外再输出 evidence 原文片段、章节标题字符串作为定位依据，也不得输出任何章节定位字符串或历史版本遗留的来源元数据字段。新契约不要求算法直接输出旧版抽取元数据（章节定位字符串、原文短片段字段、置信度、抽取状态、复核状态、原始/修正对比、质控标记等一律不输出）。
- value 必须是 OCR 原文中可定位的语义片段，不得根据医学常识补全、合并或重写。

【硬约束 — 否定表达与既往史】
- 对既往史、个人史、家族史中的疾病字段，必须先判断否定范围；`否认A、B等病史`、`无A、B史`、`未见A、B` 均表示 A、B 是明确否定事实。
- 字段被明确否定时，不得输出阳性值；应输出 `status="found"`，并在 `value` 中保留否定词，例如 `否认糖尿病病史`、`否认冠心病病史`，同时引用对应 evidence_ids。
- 保留否定词是硬要求：不得把 `否认/无/未见` 从 value 中删掉；删掉否定词会把否定事实变成模型幻觉。
- OCR 示例 `否认“糖尿病”、“冠心病”等病史`：`pmh_diabetes` 应输出 `否认糖尿病病史`，`pmh_coronary_heart_disease` 应输出 `否认冠心病病史`；不得输出“有糖尿病病史”，不得输出“有冠心病病史”。
- OCR 示例 `否认肝炎、结核等传染病史`：不得改成有肝炎、乙肝或结核病史；对 `pmh_hepatitis_b` 如无法确认乙肝精确语义，使用 `uncertain` 或保留 OCR 否定短语，绝不能输出阳性。
- 若同一句存在混合事实，例如 `否认糖尿病，既往有冠心病`，只允许把冠心病输出为阳性，糖尿病仍必须保留否定。

【硬约束 — J 型状态字段判定】
- qwen_type 为 J 或 review_control 为 judgement 的字段只表达 `正常`、`异常`、`未提及`、`不确定` 这类状态，不要摘成长文本。
- 原文明确描述该部位/项目正常或阴性时，必须输出 `status="found"`、`value="正常"`，并引用对应 evidence_ids；不得因为是阴性描述而输出 not_found。
- 正常/阴性证据包括但不限于：`正常`、`未见异常`、`无异常`、`无压痛`、`无肿大`、`无充血水肿`、`无黄染`、`未闻及病理性杂音`、`阴性`。
- 例如 `外耳道无异常分泌物，双侧乳突区无压痛，双耳粗测听力正常` 明确表示 `耳部=正常`；`鼻腔通畅，各鼻窦区无压痛` 明确表示 `鼻部=正常`。
- 只有原文完全没有该部位/项目信息时才输出 `status="not_found"`、`value=""`、`evidence_ids=[]`。
- 原文明确描述异常、阳性、肿大、压痛、发绀、皮疹、水肿、杂音等异常事实时，输出 `value="异常"`，并引用对应 evidence_ids；不要把否定词约束范围内的项目误判为异常。

【硬约束 — OCR 原文保持原样】
- 不得静默修正 OCR 文本；不得把 1/I/l、0/O/o、P62/P02/PC02/PCO2/PO2/PaO2/PaCO2 等疑似错读标签自动改成标准标签。
- 不得纠正章节标题错字；例如 `品后诊断` 必须保留原文写法，禁止替换为 `最后诊断`；同样禁止为单个错字写专门规则。
- 不得重排页序或重新组织 OCR 原文；raw OCR 顺序即真相。
- 字段归属不得依赖 OCR 是否正确识别章节标题；按固定字段表从全文/证据单元抽取。

【硬约束 — 诊断字段禁止主观】
- diagnosis_preliminary（初步诊断）和 diagnosis_final（最终诊断）只能摘录 OCR 原文中已经写出的诊断文本。
- 禁止对诊断字段做主观医学判断、推断、改写、合并、添加诊断或医学推理。
- 诊断字段不可结合其他字段或常识推断"应该是"什么诊断；证据缺失时输出 not_found。
- 如果初步诊断或最终诊断在原文中是编号列表，`value` 必须按编号分行保留，例如 `1慢性阻塞性肺疾病急性加重\n2高血压2级中危\n3慢性胃炎`；不得合并成一句，不得丢失编号，便于审核页逐条展示、编辑和导出。
- 诊断编号是原文结构，不是新增诊断；只允许拆分原文已有编号项，禁止补充或重排。

【硬约束 — 共享证据单元】
- 允许多个字段共用同一条 evidence unit；evidence_ids 可以包含 1 个或多个 ID。
- 血气 6 个字段（血气pH、血气pCO2、血气pO2、血气Na+、血气FIO2、血气氧合指数）通常共享同一条血气分析证据单元，应当显式共享 evidence_ids。

【固定字段表】
{fixed_field_table}

【证据单元编号（每条对应 OCR 原文片段，仅按 ID 引用）】
{evidence_units_section}

【合并 OCR 原文（仅供上下文理解，不作为 evidence_ids 选择依据）】
{document_text_section}

【再次强调】
- 字段必须全量输出，未找到返回 status="not_found"、value=""、evidence_ids=[]，不得省略任何字段。
- 禁止 schema 外字段；禁止自由生成二级 key；禁止输出章节/标签重复字段或任何旧版抽取元数据字段（如章节定位字符串、原文短片段、置信度、抽取/复核状态、原文/修正对比、质控标记等）。
- 禁止 OCR 文本修正、标题纠正、页序重排；禁止诊断字段主观推断或医学推理。
- 允许多个字段共用同一条 evidence unit，特别是血气 6 项。
""".strip()
