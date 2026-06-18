# Qwen 入院记录结构化字段与证据定位契约设计

## 背景

当前仓库已落地的 `copd_admission_record.v1.yaml` 是早期慢阻肺专病小字段体系，字段更偏疾病筛查和 MVP 验证，不再符合下一阶段真实入院记录结构化审核目标。

新的目标字段来源为 `data/temp/结构化字段(2).md`。该文件体现的是“按病历章节分组的业务审核字段”：不是纯章节还原，也不是旧版扁平 COPD 小字段。OCR 阶段负责从图片还原病历文本；结构化阶段负责从 OCR 文本中按固定字段表全量抽取审核字段。

`/mnt/c/Users/97949/Desktop/qwen` 目前能把 OCR、合并文本、结构化抽取串成一个批处理算法包，并通过同一套 qwen/vLLM 服务完成 OCR 与字段提取，减少多模型启动和链路切换成本。但 qwen 当前结构化输出仍允许模型自由生成二级 key，且 evidence 采用逗号级切分后的单个 `evidence_id`。下一阶段应吸收 qwen 的“证据编号”思路，但输出字段必须按固定字段表，证据定位不能依赖 OCR 是否识别出章节标题。

## 已确认决策

- qwen 结构化 prompt 必须按固定字段表全量输出，不再自由生成二级字段 key。
- 每个字段都必须返回一项；未找到返回 `not_found`。
- `主诉`、`家族史` 是独立章节。前端展示时可省略重复字段名，即章节标题为“主诉”时直接展示内容。
- `诊断` 独立成为章节，包含 `初步诊断` 和 `最终诊断`。
- 诊断字段必须提取病历记录中的诊断结果；禁止模型主观补充、改写、推理诊断。
- `体格检查.呼吸` 拆成两个字段：`生命体征呼吸` 与 `呼吸系统查体`。
- 原 `心律` 字段改为 `心脏查体`。
- `现病史.小便情况` 固定保留。
- 血气拆为 6 个固定字段：`血气pH`、`血气pCO2`、`血气pO2`、`血气Na+`、`血气FIO2`、`血气氧合指数`。
- 既往史未提及字段全量显示；未找到字段面向医生显示“未提及”或“未找到相关记录”，不得展示工程提示。
- 字段卡片高亮是黄色感叹号，表示该字段需要人工重点核验。
- OCR 高亮是把字段证据与 OCR 文本匹配，并在 OCR 文本框内高亮显示。
- 允许多个字段共用同一条证据。

## 范围

包含：

- 定义新版入院记录结构化字段表。
- 定义算法输出最小契约。
- 定义轻量证据单元 `evidence_units` 与字段 `evidence_ids` 关系。
- 定义字段卡片黄色感叹号与 OCR 文本高亮的触发规则。
- 定义 qwen 子系统接入时的提示词契约方向。
- 说明与当前旧字段契约的冲突和兼容映射。

不包含：

- 具体代码实现计划。
- 前端视觉稿细节。
- OCR 准确率评估指标。
- Docker 镜像 digest、wheelhouse、离线制品完整治理方案。
- 图片 bounding box、版面坐标、复杂文档结构树。
- HIS/EMR 接入或诊断建议生成。

## 字段表

字段按章节组织。`field_key` 为建议稳定 key，后续如需改名应作为契约变更处理。

| section_key | section_label | field_key | field_label |
| --- | --- | --- | --- |
| chief_complaint | 主诉 | chief_complaint | 主诉 |
| history_of_present_illness | 现病史 | hpi_initial_onset | 初次发病情况 |
| history_of_present_illness | 现病史 | hpi_subsequent_course | 后续发病情况 |
| history_of_present_illness | 现病史 | hpi_hospital_diagnosis | 院内诊断情况 |
| history_of_present_illness | 现病史 | hpi_treatment_medications | 治疗药物 |
| history_of_present_illness | 现病史 | hpi_recent_symptoms | 近期症状 |
| history_of_present_illness | 现病史 | hpi_mental_status | 精神 |
| history_of_present_illness | 现病史 | hpi_stool_status | 大便情况 |
| history_of_present_illness | 现病史 | hpi_urine_status | 小便情况 |
| history_of_present_illness | 现病史 | hpi_weight_change | 体重变化 |
| past_medical_history | 既往史 | pmh_cardiac_disease | 心脏病 |
| past_medical_history | 既往史 | pmh_hypertension | 高血压 |
| past_medical_history | 既往史 | pmh_diabetes | 糖尿病 |
| past_medical_history | 既往史 | pmh_hepatitis_b | 乙肝 |
| past_medical_history | 既往史 | pmh_hematochezia | 便血 |
| past_medical_history | 既往史 | pmh_nephritis | 肾炎 |
| past_medical_history | 既往史 | pmh_hematologic_disease | 血液病 |
| past_medical_history | 既往史 | pmh_coronary_heart_disease | 冠心病 |
| past_medical_history | 既往史 | pmh_cerebral_infarction | 脑梗塞 |
| past_medical_history | 既往史 | pmh_surgery_history | 手术史 |
| past_medical_history | 既往史 | pmh_transfusion_history | 输血史 |
| past_medical_history | 既往史 | pmh_blood_product_history | 血制品史 |
| past_medical_history | 既往史 | pmh_allergy_history | 过敏史 |
| personal_history | 个人史 | personal_occupation | 工作 |
| personal_history | 个人史 | personal_smoking_history | 吸烟史 |
| personal_history | 个人史 | personal_drinking_history | 饮酒史 |
| family_history | 家族史 | family_history | 家族史 |
| physical_examination | 体格检查 | pe_temperature | 体温 |
| physical_examination | 体格检查 | pe_pulse | 脉搏 |
| physical_examination | 体格检查 | pe_respiration_rate | 生命体征呼吸 |
| physical_examination | 体格检查 | pe_blood_pressure | 血压 |
| physical_examination | 体格检查 | pe_height | 身高 |
| physical_examination | 体格检查 | pe_weight | 体重 |
| physical_examination | 体格检查 | pe_bmi | BMI |
| physical_examination | 体格检查 | pe_skin | 皮肤 |
| physical_examination | 体格检查 | pe_eyes | 眼部 |
| physical_examination | 体格检查 | pe_ears | 耳部 |
| physical_examination | 体格检查 | pe_nose | 鼻部 |
| physical_examination | 体格检查 | pe_oral_cavity | 口腔 |
| physical_examination | 体格检查 | pe_neck | 颈部 |
| physical_examination | 体格检查 | pe_chest | 胸部 |
| physical_examination | 体格检查 | pe_breast | 乳房 |
| physical_examination | 体格检查 | pe_respiratory_exam | 呼吸系统查体 |
| physical_examination | 体格检查 | pe_cardiac_exam | 心脏查体 |
| physical_examination | 体格检查 | pe_abdomen | 腹部 |
| physical_examination | 体格检查 | pe_limbs | 四肢 |
| physical_examination | 体格检查 | pe_neurological_exam | 神经 |
| ancillary_tests | 辅助检查 | aux_chest_ct | 胸部CT |
| ancillary_tests | 辅助检查 | aux_cardiac_ultrasound | 心脏超声 |
| ancillary_tests | 辅助检查 | aux_blood_gas_ph | 血气pH |
| ancillary_tests | 辅助检查 | aux_blood_gas_pco2 | 血气pCO2 |
| ancillary_tests | 辅助检查 | aux_blood_gas_po2 | 血气pO2 |
| ancillary_tests | 辅助检查 | aux_blood_gas_na | 血气Na+ |
| ancillary_tests | 辅助检查 | aux_blood_gas_fio2 | 血气FIO2 |
| ancillary_tests | 辅助检查 | aux_blood_gas_oxygenation_index | 血气氧合指数 |
| ancillary_tests | 辅助检查 | aux_blood_routine | 血常规 |
| ancillary_tests | 辅助检查 | aux_electrolytes | 电解质 |
| ancillary_tests | 辅助检查 | aux_renal_function | 肾功 |
| ancillary_tests | 辅助检查 | aux_d_dimer | D2聚体 |
| diagnosis | 诊断 | diagnosis_preliminary | 初步诊断 |
| diagnosis | 诊断 | diagnosis_final | 最终诊断 |

## 算法输出契约

算法输出面向后端端口，不直接混入人工审核状态。最小契约：

```json
{
  "schema_version": "admission_record_structured_fields.v1",
  "document_type": "admission_record",
  "fields": [
    {
      "section_key": "history_of_present_illness",
      "section_label": "现病史",
      "field_key": "hpi_initial_onset",
      "field_label": "初次发病情况",
      "status": "found",
      "value": "15年前，患受凉感冒后因出现反复咳嗽、咳痰...",
      "evidence_ids": ["u012"]
    }
  ]
}
```

字段状态：

- `found`：原文中找到明确内容，`value` 非空，`evidence_ids` 应非空。
- `not_found`：原文未提及，`value=""`，`evidence_ids=[]`。
- `uncertain`：疑似找到，但 OCR 或上下文不确定，需要人工重点核验；`value` 可以为空或非空，`evidence_ids` 可为空或非空。

硬约束：

- `fields` 必须覆盖字段表中的每个字段。
- `field_key` 只能使用字段表定义的 key。
- 不允许输出 schema 外字段。
- 未找到字段不得省略。
- 诊断字段只摘录原文记录，不做主观医学判断。
- `value` 必须来自 OCR 原文语义，不得根据医学常识补全。

## 证据定位契约

### 设计原则

证据定位不应依赖 OCR 是否成功识别章节标题。章节用于字段展示和 schema 分组；证据定位使用 OCR 全文中的轻量证据单元。

新版证据链路：

```text
OCR 文本
  -> 后端生成 evidence_units
  -> qwen prompt 输入编号后的 evidence_units
  -> qwen 输出字段 value + evidence_ids
  -> 后端回填 evidence 文本和 offset
  -> 前端根据 offset 或文本在 OCR 框中高亮
```

### evidence_units

后端在 OCR 完成后生成轻量证据单元：

```json
{
  "evidence_units": [
    {
      "id": "u001",
      "text": "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。",
      "start_offset": 0,
      "end_offset": 27,
      "page_no": 1,
      "section_key": "chief_complaint"
    }
  ]
}
```

字段说明：

- `id`：稳定于本次 OCR 文本的证据单元编号。
- `text`：OCR 原文片段。
- `start_offset` / `end_offset`：在合并 OCR 文本中的字符偏移，用于前端高亮。
- `page_no`：可选；有页级文本时提供。
- `section_key`：可选；只作为辅助信息，不作为定位前置条件。

### 切分策略

第一版保持轻量，不做复杂章节恢复：

- 优先按换行、句号、分号切分。
- 生命体征行保持整行，例如 `体温...脉搏...呼吸...血压...`。
- 血气分析保持整组，例如 `pH...pCO2...pO2...Na+...FIO2...氧合指数...`。
- 诊断结果保持每条诊断或整段诊断，避免逗号级碎片造成错位。
- 治疗药物列表可保持为一个较长但可控的证据单元。
- 过长片段再按逗号切分。
- 允许多个字段共用同一个 evidence unit。

不采用 qwen 当前“全部按逗号级切分并只允许单个 evidence_id”的做法。该做法能降低模型编造 evidence 的概率，但容易导致证据不完整、诊断错位和跨片段字段无法表达。

### 轻量边界

第一版证据定位只做文本层轻量索引，不做重型文档理解系统：

- 不做图片 bounding box、版面坐标或像素级高亮。
- 不做复杂章节重建，不要求 OCR 必须正确识别章节标题。
- 不做自动页序修复，不根据内容推断医生上传图片的正确顺序。
- 不要求前端按章节重新排列 OCR 原文。
- 不让前端从 OCR 文本补造字段或重算字段值。
- 不因为 OCR 标题错字本身触发任务失败。

这意味着证据系统只保证“字段值可以回指到 OCR 原文片段”，不保证 OCR 原文自身已经被修正、排序或重排。

## OCR 不准与页面乱序时的展示边界

当前阶段不优化 OCR 准确度。前端必须完整展示后端保存的 OCR 文本，即使 OCR 文本包含错字、标题错识别、段落错位或页序错乱。

典型情况：

```text
## 品后诊断

慢性阻塞性肺疾病急性加重
2 Ⅱ型呼吸衰竭
...

## 初步诊断：

主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。
```

处理原则：

- OCR 面板展示 raw OCR，不静默改写 `品后诊断` 为 `最后诊断`。
- 结构化字段仍按 schema 章节展示，例如 `诊断 -> 最终诊断`、`主诉 -> 主诉`。
- 字段归属不依赖 OCR 原文中的标题字符串完全正确；模型可结合固定字段表和上下文抽取字段。
- 标题 OCR 错字本身不默认触发黄色感叹号；只有字段值不确定、证据缺失、证据无法定位或 OCR 错读影响字段值时才触发重点核验。
- 如果医生上传图片顺序不符合病历自然顺序，OCR 面板仍按系统接收/保存顺序展示；字段区按 schema 顺序展示。
- OCR 高亮跳转到 evidence 在 raw OCR 中的实际位置，即使该位置出现在“不符合自然病历顺序”的地方。
- 自动页序纠正、OCR 标题纠错、OCR 原文重排属于后续能力，不进入本 spec。

整体体验目标不是让 OCR 面板看起来像修正后的病历，而是让医生能同时看到：

- 字段区：按固定章节字段组织出的可审核结构化结果。
- OCR 区：真实 OCR 原文及证据位置，便于核对字段来源。

只要字段值、证据定位和医生可读风险提示稳定，OCR 原文存在错字或页序异常不应阻断进入审核。

## 泛化与反过拟合原则

本 spec 的目标是让系统包容一类 OCR 和上传顺序问题，而不是为当前小样本补若干固定规则。任何后续实现都应遵守：

- 不为单个错字写专门规则，例如不单独把 `品后诊断` 固定替换成 `最后诊断`。
- 不为单个样本的页序错乱写重排规则，例如不因为发现 `主诉` 出现在诊断后就自动调换页面。
- 不把标题识别正确作为结构化抽取的前置条件。
- 不把 evidence 定位建立在章节名字符串完全匹配上。
- 不让前端隐藏、修正或重排 OCR 原文来制造“看起来正确”的文本。
- 不因为局部 OCR 错字或标题缺失让整单失败；只有 OCR 整体不可用、结构化契约非法或全字段无效时才任务失败。

系统应通过通用机制承接异常：

| 异常类型 | 期望系统行为 |
| --- | --- |
| OCR 标题错字 | OCR 区照样展示 raw OCR；字段区按 schema 章节展示；证据用 offset/text 定位 |
| OCR 没识别出章节标题 | 不依赖章节名定位；模型仍按固定字段表从全文/evidence_units 选择证据 |
| 医生上传图片顺序不符合病历自然顺序 | OCR 区按保存顺序展示；字段区按 schema 顺序展示；证据跳到 raw OCR 实际位置 |
| 局部 OCR 字词错误 | 字段能确定则抽取并保留 raw evidence；不确定则 `uncertain` 并黄色感叹号 |
| 证据无法定位 | 字段保留，黄色感叹号提示核对；不伪造高亮 |
| 未提及字段 | 返回 `not_found`，不默认黄色感叹号 |

这套机制刻意牺牲“自动修正文书”的体验，换取泛化性和快速演进能力。后续如果要做 OCR 标题纠错、页序重排或章节恢复，应作为独立能力评估，不应混入第一版字段抽取和高亮契约。

### 字段 evidence 回填

字段输出中的 `evidence_ids` 由模型选择：

```json
{
  "field_key": "aux_blood_gas_ph",
  "status": "found",
  "value": "7.40",
  "evidence_ids": ["u128"]
}
```

后端回填为前端可用的 evidence：

```json
{
  "field_key": "aux_blood_gas_ph",
  "value": "7.40",
  "evidence": [
    {
      "id": "u128",
      "text": "血气分析:pH7.40、pCO236.00mmHg、PO276.00mmHg↓、Na+130.00mmol/L↓、FiO221.00、氧合指数:961",
      "start_offset": 5821,
      "end_offset": 5904,
      "page_no": 2
    }
  ]
}
```

规则：

- `found` 字段建议必须有 `evidence_ids`；缺失时字段进入重点核验。
- `uncertain` 字段可有或没有 `evidence_ids`；均进入重点核验。
- `not_found` 字段 `evidence_ids=[]`，不默认高亮。
- `evidence_ids` 指向不存在的 unit 时，字段进入重点核验。
- 不让模型自由编写 evidence 文本；模型只选择编号。

## 高亮逻辑

### 字段卡片黄色感叹号

字段卡片黄色感叹号表示“需要医生重点核验”，不等同于任务失败。

触发条件：

- `status == "uncertain"`。
- `status == "found"` 但 `evidence_ids` 为空。
- `status == "found"` 但 `evidence_ids` 无法回填到有效 evidence。
- `value` 与 evidence 明显不一致，后端质控或复核标记为可疑。
- OCR 疑似错读影响字段值，例如血气标签、单位、药名或关键数值存在疑点。

不默认触发：

- `status == "not_found"`。未提及是正常抽取状态，不应让既往史等章节满屏黄色感叹号。

面向医生的提示文案：

- `未提及`
- `未找到相关记录`
- `结果不确定，请核对原文`
- `缺少来源证据，请核对原文`
- `来源片段未在 OCR 文本中定位，请核对`
- `OCR 识别可能影响结果，请核对原文`

不得展示：

- `source_hint=未找到证据不作为章节定位依据`
- `evidence_missing_fallback`
- `source_section_not_found`
- 任何内部 flag 原始名称或调试信息。

### OCR 文本高亮

OCR 高亮表示字段证据在 OCR 文本中的位置。

规则：

- 优先用 evidence 的 `start_offset` / `end_offset` 高亮。
- offset 不可用时，用 evidence `text` 在 OCR 文本中匹配。
- 文本匹配仍失败时，不伪造高亮，提示“来源片段未在 OCR 文本中定位”。
- evidence 过长时不整段高亮，提示“来源片段较长，请人工核对”。
- 一个字段多个 evidence 时，可以高亮第一个 evidence，并在后续版本扩展为多片段高亮。

## 与旧契约的关系

旧字段契约包含：

```text
field_key
original_value
evidence
confidence
extraction_status
verification_status
quality_flags
ocr_correction
```

新版算法契约不要求算法直接输出全部旧元数据。建议分层：

- 算法层：`status`、`value`、`evidence_ids`。
- 后端质控层：将 evidence 回填、校验一致性、生成医生可读风险提示。
- 审核层：保存 `auto_value`、`final_value`、人工审核状态、修改历史和导出状态。

兼容映射：

| 新版算法字段 | 旧后端字段 |
| --- | --- |
| `status=found` | `extraction_status=extracted` |
| `status=not_found` | `extraction_status=not_found` |
| `status=uncertain` | `extraction_status=uncertain` |
| `value` | `original_value` / `auto_value` |
| `evidence_ids` 回填结果 | `evidence` |
| 字段重点核验 | `verification_status=suspicious` 或医生可读 risk |

旧版 `quality_flags` 和 `ocr_correction` 中有价值的能力可以保留，但不应要求 qwen 直接输出工程化内部结构。医生界面只展示可读解释。

## qwen 子系统契约方向

qwen 保留的价值：

- 同一套 qwen/vLLM 服务承担 OCR 与字段抽取。
- 减少多模型启动时间和部署复杂度。
- 算法团队可以在算法包内迭代模型、prompt、图像预处理和推理参数。

qwen 必须调整：

- OCR `temperature` 固定为 `0.0`，避免 OCR 漂移和脑补。
- 8GB 显存档位不能默认 `MAX_MODEL_LEN=30000`，需提供保守默认。
- 批处理归档不能移动工作站原图。
- 结构化 prompt 使用固定字段表全量输出。
- 模型输出 `evidence_ids`，不自由生成 evidence 文本。
- 结构化输出的 JSON 解析失败、字段缺失、schema 外字段、全字段空值均视为算法契约失败。

## 失败与降级

任务级失败：

- qwen / vLLM 服务不可达。
- OCR 整体失败或无可用 OCR 文本。
- 结构化 JSON 无法解析。
- `fields` 不是列表。
- 字段缺失、重复字段、schema 外字段。
- 全字段为空或全部 `not_found` 且无有效文本支撑。

字段级重点核验：

- 单字段 `uncertain`。
- `found` 但 evidence 无法定位。
- evidence ID 不存在。
- OCR 疑似错读影响字段值。
- 值与证据存在明显不一致。

正常进入审核：

- 局部字段 `not_found`。
- 既往史等全量字段中未提及项。
- 单字段可疑但整体 OCR 和结构化契约合法。

## 前端展示要求

- 字段按章节展示。
- 单字段章节如 `主诉`、`家族史`，可以只展示章节标题和内容，不重复显示同名字段标签。
- `not_found` 显示为“未提及”或空值轻提示，不加黄色感叹号。
- 黄色感叹号只用于需要重点核验的字段。
- 点击字段时，OCR 框尝试高亮 evidence；不能定位时展示医生可读提示。
- 前端不得从 schema、OCR 文本或页面内容补造结构化字段。

## 验收标准

- qwen 结构化输出全量覆盖字段表。
- qwen 不输出 schema 外字段。
- 未找到字段返回 `not_found`，前端显示医生可读文案。
- 诊断字段能提取原文中的初步诊断和最终诊断，不生成主观诊断建议。
- 生命体征呼吸与呼吸系统查体能分开展示。
- 心脏查体覆盖原 `心律` 相关长段内容。
- 血气 6 项能共享同一 evidence unit。
- OCR 缺失章节标题时，字段 evidence 仍可通过 offset 或文本片段定位。
- OCR 标题错识别、正文错字或页面顺序异常时，前端仍完整展示 raw OCR，字段区仍按 schema 章节展示。
- 字段卡片黄色感叹号与 OCR 文本高亮逻辑分离。
- `not_found` 字段不默认触发黄色感叹号。
- 前端不展示工程 flag 名称或调试提示。

## 待后续评估

- 是否需要在 evidence 中同时保存 `page_no` 和 `page_id`。
- 是否需要从第一版就支持一个字段多个 evidence 同时高亮。
- qwen prompt 是否按章节批次并发抽取，还是一次性全量字段抽取。
- 旧 `quality_flags` 中哪些规则继续保留，哪些改为医生可读 risk 类型。
- 字段 key 是否完全采用本 spec 的英文 snake_case，或改用更接近文档标题的中文 key。
