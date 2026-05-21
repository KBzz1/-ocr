# 慢阻肺专病字段抽取集成设计

## 背景

当前仓库的 `app/config/schemas/medical_record.v1.yaml` 是早期通用病历字段假设，不符合真实报告。外包目录 `data/temp/Medical_Text3` 中的字段来自真实慢阻肺/呼吸系统入院记录，应作为本次字段体系的权威来源。

本次集成目标是把 `Medical_Text3` 中已经验证过的专病字段、规则分段/抽取辅助逻辑、LLM 抽取和复核能力吸收到主代码中，形成项目内可测试、可维护的慢阻肺专病字段抽取能力。既有文档中“本仓库不得实现规则抽取”的边界需要随本次决策同步修订。

## 范围

第一版只支持慢阻肺/呼吸系统入院记录专病字段，不追求通用病历兼容。

包含：

- 建立慢阻肺专病 schema。
- 以 `Medical_Text3` 字段为源头重写字段契约。
- 将 `Medical_Text3` 的规则分段、字段默认结构、抽取提示词和复核提示词整理后纳入主代码。
- 使用单个本地 Qwen2.5-7B-Instruct GGUF 模型串行执行抽取和复核。
- 后端核心代码提供慢阻肺专病规则化抽取模块，负责规则分段、LLM 调用、字段结果归一化、证据校验和复核编排。
- 审核页全量展示 schema 字段，未抽到的字段也显示为空，便于人工补录和核验。
- 同步 PRD、BDD、TDD 中关于字段、空值、失败和校验的描述。

不包含：

- OCR、图像预处理、裁剪、透视矫正。
- HIS/EMR 接入。
- 医学诊断建议生成。
- 多病种通用字段体系。
- 云模型或运行时联网下载模型。

## 字段体系

新 schema 使用 `copd_admission_record.v1.yaml`。字段来源以 `Medical_Text3.TextExtractor._default_result()` 为基础，但后端和前端使用稳定扁平字段 key。

建议第一版字段：

| field_key | label | 来源 |
| --- | --- | --- |
| occupation | 职业 | 个人史 |
| smoking_history_raw_text | 吸烟史原文 | 个人史 |
| smoking_history_status | 吸烟状态 | 个人史 |
| copd_history_years | 慢阻肺/慢性咳喘病程 | 主诉、现病史、既往史 |
| baseline_lung_function | 基线肺功能 | 现病史、辅助检查 |
| maintenance_therapy | 长期维持治疗 | 现病史 |
| cough_sputum_change | 咳嗽咳痰变化 | 主诉、现病史 |
| dyspnea_grade_mMRC | 呼吸困难程度/mMRC | 现病史 |
| treatment_failure | 既往或本次治疗效果不佳 | 现病史 |
| weight_loss | 体重下降 | 现病史 |
| gi_symptoms | 胃肠道症状 | 现病史 |
| comorbidities | 合并症 | 既往史、现病史 |
| temperature | 体温 | 体格检查 |
| pulse | 脉搏 | 体格检查 |
| respiration | 呼吸 | 体格检查 |
| blood_pressure | 血压 | 体格检查 |
| bmi | BMI | 体格检查 |
| positive_signs | 阳性体征 | 体格检查 |
| blood_gas_ph | 血气 pH | 辅助检查 |
| blood_gas_pao2 | 血气 PaO2/PO2 | 辅助检查 |
| blood_gas_paco2 | 血气 PaCO2/PCO2 | 辅助检查 |
| electrolyte_imbalance | 电解质异常 | 辅助检查 |
| wbc | 白细胞 | 辅助检查 |
| crp | C 反应蛋白 | 辅助检查 |
| ct_features | 胸部 CT 语义 | 辅助检查 |

字段 key 后续可扩展，但第一版不混入通用入院记录字段，避免 schema 再次偏离真实需求。

## 输出契约

项目内慢阻肺字段抽取模块最终向后端处理流程返回全量字段结果列表。每个 schema 字段必须有且只有一条结果。每个字段结果必须满足：

```json
{
  "field_key": "copd_history_years",
  "original_value": "15年",
  "evidence": "反复咳嗽、咳痰15年",
  "confidence": 0.86,
  "source_section": "主诉",
  "extraction_status": "extracted",
  "verification_status": "passed",
  "quality_flags": [],
  "ocr_correction": {
    "applied": false,
    "raw": "反复咳嗽、咳痰15年",
    "normalized": "反复咳嗽、咳痰15年",
    "reason": ""
  }
}
```

字段说明：

- `field_key`：必须存在于当前 schema。
- `original_value`：抽到的原文值；未抽到时为空字符串。
- `evidence`：支撑该值的原文片段；未抽到时为 `null`。
- `confidence`：0 到 1 的数值；未抽到时可以为 0。
- `source_section`：主诉、现病史、既往史、个人史、体格检查、辅助检查等。
- `extraction_status`：`extracted`、`not_found`、`uncertain`。
- `verification_status`：`passed`、`suspicious`、`failed`、`not_checked`。
- `quality_flags`：规则化质量核验输出的风险标记列表。
- `ocr_correction`：模型是否按上下文理解了 OCR 疑似错误；不得静默改写。

## 空值和失败原则

本项目需要全量展示 schema 字段，因此未抽到的字段也进入审核页，但必须明确标记为空值状态。

规则：

- 抽到真实值的字段：`extraction_status=extracted`，必须带 evidence。
- 没抽到的字段：`extraction_status=not_found`，`original_value=""`，`evidence=null`，允许进入审核页。
- 不确定字段：`extraction_status=uncertain`，允许进入审核页，但必须展示为待人工重点核验。
- 如果所有字段都是 `not_found` 或空值，任务失败，不进入审核页。
- 单字段 evidence 不可信、数值疑似不一致、否定关系疑似反转或字段归属可疑时，不默认让整个任务失败；该字段应标记为 `verification_status=suspicious` 或 `failed` 并进入审核页高亮。
- 任务级失败只用于整体不可解析、字段结果结构非法、字段 key 不完整、全字段空值、模型调用失败或复核输出不可解析。
- 主代码中的规则只允许用于文本规范化、章节分段、字段候选定位和证据匹配；不得在无原文证据时编造医学值。
- 空字段由项目内抽取模块按 schema 回填为 `not_found`，用于审核页全量展示。

## 模型策略

第一版只使用一个本地模型：

```text
models/llm/qwen2.5-7b-instruct-gguf/
  qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
  qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf
```

推理流程：

```text
OCR 合并文本
  -> 规则分段
  -> 7B 抽取慢阻肺专病字段
  -> 项目内契约和 evidence 校验
  -> 7B 复核 value/evidence 一致性
  -> 后端 schema 校验
  -> 审核页全量字段展示
```

执行约束：

- 不再使用 3B 主抽取模型。
- 不同时加载多个 LLM。
- 7B 抽取和 7B 复核串行执行，适配 8G 显存。
- 默认使用确定性参数，优先稳定 JSON 输出。
- 如果 Qwen2.5-7B baseline 的主要错误来自模型能力，而不是 schema、prompt 或校验，再评估 Qwen3-8B 或医疗微调模型。

## 主代码吸收策略

`data/temp/Medical_Text3` 不能原样复制进应用代码。需要拆分、清理并纳入后端模块：

- 删除 `.idea`、`__pycache__`、虚拟环境、wheel 和临时模型缓存。
- 将字段定义迁移为 `copd_admission_record.v1.yaml`。
- 将规则分段和文本规范化整理为纯函数，覆盖主诉、现病史、既往史、个人史、婚育史、家族史、体格检查、辅助检查。
- 将 LLM 抽取封装为可注入模型路径的服务，默认读取 `models/llm/qwen2.5-7b-instruct-gguf/`。
- 将 LLM 复核封装为同一模型的第二次串行调用。
- 将嵌套结果转换为扁平全量字段结果列表。
- 将 evidence 匹配和全空失败作为项目内可测试逻辑。
- 增加薄规则质量核验框架，只输出字段级风险标记。

建议代码边界：

```text
app/backend/services/copd_extraction/
  schema_mapping.py
  text_normalizer.py
  section_splitter.py
  llm_extractor.py
  verifier.py
  candidate_builder.py
  evidence_validator.py
  quality_checks.py
```

这些模块属于主代码，但只服务慢阻肺专病结构化，不扩展成通用医疗规则引擎。

## Prompt Harness 设计

第一版不实现 OCR 噪声候选生成，也不由规则层预先修正 OCR 文本。OCR 可能误识别的信息只作为 prompt 中的风险提示，由模型在抽取和复核时结合上下文判断。

抽取 prompt 输入应包含：

- 当前字段 schema 和字段解释。
- 规则分段后的原始 OCR 文本。
- OCR 风险提示：`1/I/l`、`0/O/o`、`BHI/BMI`、`cT/CT/Ct`、单位断裂、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
- 硬约束：不得静默修正 OCR，不得改写数值，不得医学换算，不得推断原文未写的信息，不得把否定表达转成阳性。

抽取 prompt 输出必须是全量字段列表。每个字段除基础契约外，还必须包含 OCR 纠偏审计信息：

```json
{
  "field_key": "bmi",
  "original_value": "24.2kg/m2",
  "evidence": "BHI:24.2kg/m2",
  "confidence": 0.78,
  "source_section": "体格检查",
  "extraction_status": "extracted",
  "verification_status": "not_checked",
  "quality_flags": [],
  "ocr_correction": {
    "applied": true,
    "raw": "BHI",
    "normalized": "BMI",
    "reason": "该片段位于身高、体重之后，且数值单位为 kg/m2，更符合 BMI 字段"
  }
}
```

OCR 纠偏规则：

- 如果模型按 OCR 原文直接抽取，`ocr_correction.applied=false`，`raw` 和 `normalized` 可相同，`reason` 为空字符串。
- 如果模型将 OCR 片段按医学上下文理解为另一个标签或单位，必须设置 `applied=true`，并输出 `raw`、`normalized` 和具体理由。
- 没有上下文依据时不得纠偏；宁可输出 `uncertain`，由人工审核。
- 允许纠偏字段标签或单位写法，例如 `BHI` 理解为 `BMI`、`PC02` 理解为 `PCO2`。
- 不允许纠偏数值本身，例如不得把 `36.00` 改成 `38.00`。
- evidence 必须保留 OCR 原文片段，不能只输出模型纠偏后的文本。

复核 prompt 不再只输出 `PASS` 或自由文本，应逐字段输出结构化审计结果：

```json
{
  "field_key": "blood_gas_paco2",
  "verdict": "pass",
  "checks": {
    "evidence_supported": true,
    "ocr_correction_reasonable": true,
    "numeric_value_preserved": true,
    "negation_preserved": true,
    "section_assignment_reasonable": true
  },
  "comment": ""
}
```

复核失败示例：

```json
{
  "field_key": "blood_gas_paco2",
  "verdict": "fail",
  "checks": {
    "evidence_supported": true,
    "ocr_correction_reasonable": false,
    "numeric_value_preserved": false,
    "negation_preserved": true,
    "section_assignment_reasonable": true
  },
  "comment": "原文 evidence 为 PCO2 36.00mmHg，候选值改变了数值或缺少合理 OCR 纠偏理由"
}
```

复核失败或可疑字段进入审核页，但必须突出显示为需要人工重点核验。只有复核输出整体不可解析、结构非法或全字段不可用时，任务才进入 `failed`。

## 薄规则质量核验

第一版增加一层薄的规则化质量核验，目标是快速搭起框架，发现高风险 OCR/结构问题并给审核页提供风险标记。规则层只做风险提示，不自动纠错、不生成字段值、不删除重复文本、不替代 LLM 抽取。

执行位置：

```text
LLM 抽取
  -> 契约校验
  -> 薄规则质量核验
  -> LLM 复核
  -> 字段级状态合并
  -> 审核页
```

第一版只做四类轻量检查：

- **数值/evidence 一致性**：抽取值中的数字应能在 evidence 中找到；找不到则标记 `value_not_in_evidence`。
- **重复/拼接风险**：OCR 合并文本或字段 evidence 中出现高相似重复片段、短窗口重复检验项或重复医嘱时，标记 `possible_duplicate_or_stitching`。
- **日期范围风险**：字段或 evidence 中日期明显晚于当前日期、年份与同一病历上下文冲突时，标记 `suspicious_date`。
- **否定/不确定语气风险**：evidence 附近出现“无、否认、未见、可能、考虑、建议复查”等词，而字段值表达为确定阳性时，标记 `negation_or_uncertainty_risk`。

规则输出只追加到字段级 `quality_flags`：

```json
{
  "field_key": "blood_gas_pao2",
  "flag": "value_not_in_evidence",
  "severity": "warning",
  "message": "字段值中的数字未能在 evidence 中直接找到"
}
```

质量标记合并规则：

- 有 `quality_flags` 的字段默认 `verification_status=suspicious`，除非 LLM 复核给出更严重的 `failed`。
- `quality_flags` 不直接导致任务失败。
- 只有规则执行异常、字段结果结构非法、全字段空值或模型输出不可解析时，任务才失败。
- 规则层后续可以扩展药名、医学短语和机构名小词表，但第一版不做。

## 校验机制

校验分三层。

第一层是项目内抽取模块契约校验：

- 输出必须是合法 JSON。
- 字段 key 必须完整覆盖 schema，且不得重复。
- 每个字段必须包含 `field_key`、`original_value`、`evidence`、`confidence`、`source_section`、`extraction_status`。
- 每个字段必须包含 `verification_status`。
- 每个字段必须包含 `quality_flags`，且必须是列表。
- `extraction_status` 必须在枚举内。
- `verification_status` 必须在枚举内。
- `extracted` 字段必须有非空 `original_value` 和 evidence。
- 每个字段必须包含 `ocr_correction`，且结构包含 `applied`、`raw`、`normalized`、`reason`。

第二层是 evidence 和薄规则质量核验：

- `extracted` 字段的 evidence 应能在 OCR 合并文本中直接找到。
- 数值字段应保留原单位和原文写法，不做医学换算。
- 薄规则质量核验只追加 `quality_flags`，不修改字段值。
- 存在 OCR 纠偏时，复核结果必须判断纠偏理由是否合理。
- 否定表达不能被转成阳性字段；无法确认时标记为 `suspicious`。
- 复核模型发现字段级错误时，字段标记为 `failed` 或 `suspicious`，进入审核页高亮。

第三层是后端 schema 校验：

- 字段 key 不在 schema 中则任务失败。
- 字段 key 缺失、重复或未完整覆盖 schema 则任务失败。
- 结构非法则失败。
- 全字段空值则失败。
- 通过后写入算法结果，再进入审核页。

## 样本和泛化验证

实施计划必须包含一个独立验证步骤：手动制造测试样本，覆盖真实病历风格和 OCR 易错场景，先验证规则分段、prompt harness、模型输出和复核输出，再接入完整任务流程。第一版暂不要求收集真实 OCR 文本；由人工按真实报告风格和已观察到的 OCR 错误类型构造回归样本。

样本来源和类型：

- 以 `data/temp/Medical_Text3/sample_record.txt` 的真实慢阻肺入院记录风格仿写不少于 5 份样本。
- 构造不同病程、吸烟史、戒烟史、急性加重、长期吸入治疗、血气、CRP/WBC、CT 表述。
- 构造字段缺失样本，验证 `not_found` 空值展示。
- 构造全字段不可抽取样本，验证任务失败。
- 构造否定表达样本，例如“无发热”“否认咯血”“未见明显异常”，验证不被转成阳性。
- 构造数值和单位样本，例如 `pH 7.40`、`PCO2 36.00mmHg`、`WBC 6.63*10^9/L`、`CRP 3.3mg/L`。

OCR 误差族群至少覆盖：

- 医学指标标签误识别：数字、英文字母和上下标混淆导致检验指标标签异常，模型可结合医学上下文理解标签，但不得改写数值。
- 药名和医学词错字：常见药名、医学术语被识别成近形字、同音字或缺字，模型可以标记疑似纠偏，但必须保留原文 evidence。
- 单位、数值和范围异常：单位断裂、小数点异常、范围值前后矛盾、后文出现更合理版本时，模型应优先标记为 `suspicious`，不得自动选一个确定值。
- 机构名、地名和日期误识别：医院名称、页码、日期年份出现明显不合语境的识别错误时，只能作为低置信度信息或 OCR 纠偏审计输出。
- 跨页、跨栏、表格错位和拼接错误：项目和值错位、段落跨页粘连、内容重复拼接时，模型不得把重复内容当成多个独立事实。
- 重复段落和重复医嘱：明显由页面重叠或 OCR 合并导致的重复，应被压缩为一个字段事实或标记可疑。
- 否定和程度词误识别：否认、无、未见、考虑、可能、建议复查等语气词不得被忽略或改写为确定阳性结论。

验收方式：

- 每份样本有期望字段快照。
- 规则化分段、prompt 输出结构、OCR 纠偏审计、evidence 匹配、薄规则质量核验和全流程抽取分别有测试。
- 模型输出不要求字字相同，但关键字段、数值、否定关系和 evidence 必须正确。
- 记录失败样本，区分是 prompt harness、模型能力、evidence 校验还是 schema 设计问题。
- 5 份手工构造样本只作为第一版回归集和冒烟基线，不宣称已经覆盖真实世界泛化；后续拿到脱敏 OCR 文本后再扩展字段级评估集。

## 后端职责

后端负责：

- 承载慢阻肺专病规则化抽取模块。
- 调用本地 LLM。
- 校验输出契约。
- 保存字段结果。
- 维护任务状态。
- 展示失败原因。
- 支持人工审核、保存和导出。

后端不负责：

- OCR、图像预处理或版面还原。
- 在无原文证据时补造字段值。
- 对患者生成诊断结论或医学建议。

## 文档同步

需要同步更新：

- `docs/产品PRD.md`：字段体系从通用病历改为慢阻肺/呼吸系统专病 MVP。
- 根级 `AGENTS.md` / `CLAUDE.md`：删除或修订“本仓库不得实现规则抽取”的旧边界，改为允许慢阻肺专病字段规则化抽取。
- `docs/PRD任务清单.md`：新增专病字段抽取集成任务。
- `docs/Backend/Backend_BDD/algorithm-integration.md`：更新字段抽取成功、空值展示、全空失败、证据失败场景。
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`：更新字段结果契约。
- `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`：更新全空和 evidence 失败契约。
- `docs/Backend/Backend_TDD/08-schema-management.md`：说明 schema 可全量展示空字段，但不得生成字段值。
- `docs/Shared/state-enums.md`：扩展字段级抽取/验证元数据，支持未抽取、可疑、验证失败和 OCR 纠偏审计展示。
- `docs/Backend/AGENTS.md` / `docs/Backend/CLAUDE.md`：同步后端职责，允许专病规则化抽取模块存在。
- `app/config/schemas/`：新增或替换为 `copd_admission_record.v1.yaml`。

## 验收标准

- 模型文件位于 `models/llm/qwen2.5-7b-instruct-gguf/`。
- 系统使用慢阻肺专病 schema 创建新任务。
- 项目内慢阻肺字段抽取模块返回全量 schema 字段。
- 抽到的字段带原文 evidence。
- 未抽到的字段在审核页显示为空，且状态为未抽取。
- 全字段未抽到时任务进入 `failed`。
- 单字段 evidence 不可信或复核失败时进入审核页高亮；整体结构非法、全字段空值或复核输出不可解析时任务进入 `failed`。
- 手工制造的真实风格和 OCR 噪声样本通过规则分段、prompt harness、OCR 纠偏审计、evidence 校验、薄规则质量核验和全流程抽取测试。
- 模型发生 OCR 纠偏时必须输出 `ocr_correction`，不得静默修改标签、单位或数值。
- 薄规则质量核验只输出 `quality_flags`，不自动纠错、不抽取字段、不导致任务失败。
- 手工样本作为第一版回归集，不作为泛化充分性的证明。
- 后端测试覆盖 schema 外字段、非法结构、全空字段、evidence 失败和正常字段展示。
- PRD、BDD、TDD 与实现契约一致。
