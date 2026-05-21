# 慢阻肺专病字段抽取集成设计

## 背景

当前仓库的 `app/config/schemas/medical_record.v1.yaml` 是早期通用病历字段假设，不符合真实报告。外包目录 `data/temp/Medical_Text3` 中的字段来自真实慢阻肺/呼吸系统入院记录，应作为本次字段体系的权威来源。

本次集成目标不是在后端实现医学规则抽取，而是把真实专病字段、外部本地 LLM 抽取模块、后端端口契约和审核页展示统一起来。

## 范围

第一版只支持慢阻肺/呼吸系统入院记录专病字段，不追求通用病历兼容。

包含：

- 建立慢阻肺专病 schema。
- 以 `Medical_Text3` 字段为源头重写字段契约。
- 使用单个本地 Qwen2.5-7B-Instruct GGUF 模型串行执行抽取和复核。
- 后端通过外部字段抽取端口接入，不在核心业务代码中实现 LLM 抽取或医学规则抽取。
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

外部字段抽取模块最终向后端返回候选字段列表。每个字段必须满足：

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
- 后端不得用规则或 schema 自行推断字段值；空字段只能来自外部模块按 schema 回填的 `not_found` 结果。

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
  -> 7B 抽取慢阻肺专病字段
  -> 本地契约校验
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

## 校验机制

校验分三层。

第一层是外部模块内部契约校验：

- 输出必须是合法 JSON。
- 字段 key 必须完整覆盖 schema。
- 每个字段必须包含 `field_key`、`original_value`、`evidence`、`confidence`、`source_section`、`extraction_status`。
- `extraction_status` 必须在枚举内。
- `extracted` 字段必须有非空 `original_value` 和 evidence。

第二层是 evidence 校验：

- `extracted` 字段的 evidence 应能在 OCR 合并文本中直接找到，或通过轻量归一化后找到。
- 数值字段应保留原单位和原文写法，不做医学换算。
- 否定表达不能被转成阳性字段。
- 复核模型发现错误时，不放行到审核页。

第三层是后端 schema 校验：

- 字段 key 不在 schema 中则失败。
- 结构非法则失败。
- 全字段空值则失败。
- 通过后写入算法结果，再进入审核页。

## 后端边界

后端继续只负责：

- 调用外部本地字段抽取模块。
- 校验输出契约。
- 保存候选字段。
- 维护任务状态。
- 展示失败原因。
- 支持人工审核、保存和导出。

后端不负责：

- LLM prompt 的医学逻辑。
- 从 OCR 文本中规则抽取字段。
- 在抽取失败时补造字段值。
- 对患者生成诊断结论或医学建议。

## 文档同步

需要同步更新：

- `docs/产品PRD.md`：字段体系从通用病历改为慢阻肺/呼吸系统专病 MVP。
- `docs/PRD任务清单.md`：新增专病字段抽取集成任务。
- `docs/Backend/Backend_BDD/algorithm-integration.md`：更新字段抽取成功、空值展示、全空失败、证据失败场景。
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`：更新字段候选契约。
- `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`：更新全空和 evidence 失败契约。
- `docs/Backend/Backend_TDD/08-schema-management.md`：说明 schema 可全量展示空字段，但不得生成字段值。
- `app/config/schemas/`：新增或替换为 `copd_admission_record.v1.yaml`。

## 验收标准

- 模型文件位于 `models/llm/qwen2.5-7b-instruct-gguf/`。
- 系统使用慢阻肺专病 schema 创建新任务。
- 外部字段抽取模块返回全量 schema 字段。
- 抽到的字段带原文 evidence。
- 未抽到的字段在审核页显示为空，且状态为未抽取。
- 全字段未抽到时任务进入 `failed`。
- evidence 不可信或复核失败时任务不进入审核页。
- 后端测试覆盖 schema 外字段、非法结构、全空字段、evidence 失败和正常字段展示。
- PRD、BDD、TDD 与实现契约一致。

