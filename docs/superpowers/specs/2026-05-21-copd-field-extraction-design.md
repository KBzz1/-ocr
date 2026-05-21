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
- 后端核心代码提供慢阻肺专病规则化抽取模块，负责规则分段、LLM 调用、候选字段归一化、证据校验和复核编排。
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

项目内慢阻肺字段抽取模块最终向后端处理流程返回候选字段列表。每个字段必须满足：

```json
{
  "field_key": "copd_history_years",
  "original_value": "15年",
  "evidence": "反复咳嗽、咳痰15年",
  "confidence": 0.86,
  "source_section": "主诉",
  "extraction_status": "extracted"
}
```

字段说明：

- `field_key`：必须存在于当前 schema。
- `original_value`：抽到的原文值；未抽到时为空字符串。
- `evidence`：支撑该值的原文片段；未抽到时为 `null`。
- `confidence`：0 到 1 的数值；未抽到时可以为 0。
- `source_section`：主诉、现病史、既往史、个人史、体格检查、辅助检查等。
- `extraction_status`：`extracted`、`not_found`、`uncertain`。

## 空值和失败原则

本项目需要全量展示 schema 字段，因此未抽到的字段也进入审核页，但必须明确标记为空值状态。

规则：

- 抽到真实值的字段：`extraction_status=extracted`，必须带 evidence。
- 没抽到的字段：`extraction_status=not_found`，`original_value=""`，`evidence=null`，允许进入审核页。
- 不确定字段：`extraction_status=uncertain`，允许进入审核页，但必须展示为待人工重点核验。
- 如果所有字段都是 `not_found` 或空值，任务失败，不进入审核页。
- 如果任一 `extracted` 字段的 evidence 找不到、不可信、数值不一致、否定关系反转或字段归属明显错误，则任务失败或进入算法复核失败，不放行到审核页。
- 主代码中的规则只允许用于文本规范化、章节分段、字段候选定位、证据匹配和 OCR 噪声归一化；不得在无原文证据时编造医学值。
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
  -> 规则分段和 OCR 噪声轻量归一化
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
- 将嵌套结果转换为扁平候选字段列表。
- 将 evidence 匹配、OCR 噪声归一化和全空失败作为项目内可测试逻辑。

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
```

这些模块属于主代码，但只服务慢阻肺专病结构化，不扩展成通用医疗规则引擎。

## 校验机制

校验分三层。

第一层是项目内抽取模块契约校验：

- 输出必须是合法 JSON。
- 字段 key 必须完整覆盖 schema。
- 每个字段必须包含 `field_key`、`original_value`、`evidence`、`confidence`、`source_section`、`extraction_status`。
- `extraction_status` 必须在枚举内。
- `extracted` 字段必须有非空 `original_value` 和 evidence。

第二层是 evidence 校验：

- `extracted` 字段的 evidence 应能在 OCR 合并文本中直接找到，或通过轻量归一化后找到。
- OCR 噪声归一化允许处理常见误识别，例如 `I/1`、`O/0`、中文冒号和英文冒号、单位空格、大小写 CT/cT。
- 数值字段应保留原单位和原文写法，不做医学换算。
- 否定表达不能被转成阳性字段。
- 复核模型发现错误时，不放行到审核页。

第三层是后端 schema 校验：

- 字段 key 不在 schema 中则失败。
- 结构非法则失败。
- 全字段空值则失败。
- 通过后写入算法结果，再进入审核页。

## 样本和泛化验证

实施计划必须包含一个独立验证步骤：手动制造测试样本，覆盖真实病历风格和 OCR 易错场景，先验证规则、prompt 和模型输出，再接入完整任务流程。

样本来源和类型：

- 以 `data/temp/Medical_Text3/sample_record.txt` 的真实慢阻肺入院记录风格仿写不少于 5 份样本。
- 构造不同病程、吸烟史、戒烟史、急性加重、长期吸入治疗、血气、CRP/WBC、CT 表述。
- 构造字段缺失样本，验证 `not_found` 空值展示。
- 构造全字段不可抽取样本，验证任务失败。
- 构造否定表达样本，例如“无发热”“否认咯血”“未见明显异常”，验证不被转成阳性。
- 构造数值和单位样本，例如 `pH 7.40`、`PCO2 36.00mmHg`、`WBC 6.63*10^9/L`、`CRP 3.3mg/L`。

OCR 噪声样本至少覆盖：

- `I` 和 `1` 混淆，例如 `FI02`、`1/日`、`10^9/L`。
- `O` 和 `0` 混淆，例如 `PCO2`、`PO2`、`SpO2`。
- `l`、`I`、`1` 混淆，例如 `mg/L`、`mmol/L`。
- `m`、`rn`、`n` 类似形混淆。
- `BHI` 误识别为 `BMI` 或反向。
- `cT`、`CT`、`Ct` 大小写混乱。
- 表格错位或断行，例如检验项目和值换行、项目和值跨列粘连。
- 冒号、分号、顿号和空格丢失，例如 `体温36.7°脉搏99次/分`。
- 小数点、逗号、单位间距异常，例如 `3 .3mg/L`、`130. 00mmol/L`。
- OCR 错别字不影响字段定位的场景，例如“林巴结/淋巴结”“芷常/正常”。

验收方式：

- 每份样本有期望字段快照。
- 规则化分段、候选构建、evidence 匹配和全流程抽取分别有测试。
- 模型输出不要求字字相同，但关键字段、数值、否定关系和 evidence 必须正确。
- 记录失败样本，区分是 OCR 噪声归一化、prompt、模型能力还是 schema 设计问题。

## 后端职责

后端负责：

- 承载慢阻肺专病规则化抽取模块。
- 调用本地 LLM。
- 校验输出契约。
- 保存候选字段。
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
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`：更新字段候选契约。
- `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`：更新全空和 evidence 失败契约。
- `docs/Backend/Backend_TDD/08-schema-management.md`：说明 schema 可全量展示空字段，但不得生成字段值。
- `docs/Backend/AGENTS.md` / `docs/Backend/CLAUDE.md`：同步后端职责，允许专病规则化抽取模块存在。
- `app/config/schemas/`：新增或替换为 `copd_admission_record.v1.yaml`。

## 验收标准

- 模型文件位于 `models/llm/qwen2.5-7b-instruct-gguf/`。
- 系统使用慢阻肺专病 schema 创建新任务。
- 项目内慢阻肺字段抽取模块返回全量 schema 字段。
- 抽到的字段带原文 evidence。
- 未抽到的字段在审核页显示为空，且状态为未抽取。
- 全字段未抽到时任务进入 `failed`。
- evidence 不可信或复核失败时任务不进入审核页。
- 手工制造的真实风格和 OCR 噪声样本通过规则分段、evidence 校验和全流程抽取测试。
- 后端测试覆盖 schema 外字段、非法结构、全空字段、evidence 失败和正常字段展示。
- PRD、BDD、TDD 与实现契约一致。
