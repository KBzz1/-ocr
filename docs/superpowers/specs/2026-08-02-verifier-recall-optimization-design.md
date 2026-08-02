# 复核器召回优化设计（Verifier Recall Optimization）

> 日期：2026-08-02
> 状态：草案（待审阅）
> 关联：`2026-08-02-prompt-refactor-field-boundary-design.md`（上轮四步消融，本设计为其后续）；复核器设计权威 `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`
> 分支：worktree-prompt-refactor-field-boundary

## 1. 背景与动机

2026-08-02 四步消融实验（step4 最终版 = 重构 + 字段边界句，形态 A）后，用 6 个 AI judge 子 agent 对 281 条 verdicts 全量独立裁定：

- **kappa = 0.0834**（n=281，表 [[261,18],[1,1]]），远低于 0.7 上岗线；
- **漏检 18 条**：复核器标 pass 但独立裁定确认有实质问题；
- **误报 1 条**：case_002 pe_pulse（房颤患者脉率少于心率可解释，复核器标 suspicious 属误报）。

24 条重点（AI 应标 19 + 拿不准 5）按问题形态抽象为四类（用户确认）：

| 类别 | 问题 | 条数 | 职责归属（用户裁决） |
|---|---|---|---|
| A | OCR 错读病句噪声（粗侧→粗测、证→征、语音额→语颤、胸状胸→桶状胸、古手、吸支性、克格征征等）| 11 | **复核器**（语义表达噪声）|
| B | 字段越界（pe_eyes 混入头颅/耳鼻口、CT 所见进既往史字段等）| 8（5 应标 + 3 拿不准）| **抽取器**（根因）+ **复核器**负责标记可疑 |
| C | 数值/语义矛盾（氧合指数 961 vs PO2/FiO2、腹部移动性浊音阳性 vs 腹部正常、11 年前"无发热" vs 本次 39.5℃）| 3 | **复核器**（逻辑检查，与抽取器无关）|
| D | 叠字等轻微瑕疵（膜膜、肝肝）| 2（拿不准）| **复核器**（阈值问题）|

**根因诊断（数据证伪了坐标粒度假设）**：case_001 原文句段[18]为"全身浅淋巴结未触及肿大,头颅无畸形,无压痛,头发色泽正常,颜面眼睑无浮肿…双眼粗侧视力正常。"（一个句号段），但 pe_eyes 的 value 从"头颅无畸形"开始、**不含**句首"全身浅淋巴结"——模型做了选择性摘录，把"头颅/头发/颜面眼睑…"整串五官连写描述归入"眼部"字段。**不是切分粒度问题**（evidence_units 切分逻辑不动），而是模型对字段边界的理解过宽 + 字段边界句约束力不足（字段表无"头部"字段，"头颅无畸形"属字段表未收录内容，但边界句的"一般情况"例子未覆盖头部五官连写场景）。

**A/C 类漏检的共性根因**：原则 1"证据与值同源，一致不能证明文本没错"与原则 3"错读导致的病句均须标记"**已存在但未被执行**——模型看到值与证据逐字一致即放行（同源放行）。措辞存在 ≠ 模型执行，需要 few-shot 行为示范。

## 2. 目标与边界

### 目标

1. 四类问题落到对应职责的 prompt 修改（各一句话 + 2 个 few-shot 行为示例 + 字段表描述精确化）；
2. step5 实验验证：漏检 18 → 显著下降（如 <5），误报不显著增加，kappa 提升；
3. **先修召回，不设 0.7 硬线**（用户裁决：kappa 0.0834 → 0.7 是大跃升，一步到位不现实，达标与否下轮迭代）。

### 边界（明确不做）

- **不改 evidence_units 切分逻辑**（根因已证伪坐标粒度假设）；
- **不改 reason_code 枚举**（示例 2 复用现有 extraction_mistake）；
- **不动 v1 schema 字段体系**——只加 `description` 元数据，字段增删零变更；
- 不新增字段（一般情况等仍为未来工作项）；
- 不改输出契约（JSON 形状、verdict 枚举、checks 结构保持稳定）；
- 温度恒为 0.0；system 文本完全固定（不含 evidence/document_text 变量数据）；
- 本次不做 kappa 重校准的人工全量评定——人工基准采用"AI judge 全量裁定 + 用户重点确认"的混合口径（用户裁决：281 条太多，AI 做主体、用户看重点）。

## 3. 修改点（逐字定稿）

### 3.1 复核器 prompt（4 处）

**修改 1 — 原则 3 尾部加"表达瑕疵阈值"句（A/D 类）**

现状结尾：`长文本字段按句拆分编号，必须逐句扫读全值，不得因整体语义通顺而放行。`

追加：
> 错读/病句/叠字等表达瑕疵：影响理解或产生歧义 → 必须标记；不影响语义理解的轻微重复可不标。值忠实摘录原文不豁免错读检查——值一致只证明抄得对，不证明文本本身没问题。

**修改 2 — 原则 4 从"数值矛盾"扩为"逻辑一致性"（C 类）**

现状：`数值矛盾或异常：同段存在与字段值不一致的数值（如脉搏 9 次/分但另有心率 99 次/分）、数值超出合理范围疑似 OCR 截断（99→9、36.7→3.7）、体重下降/减轻字段输出 0g、0kg、0克 等反直觉数值，均应标记。`

改为：
> 数值矛盾或逻辑不一致：同段存在与字段值不一致的数值、数值超出合理范围疑似 OCR 截断（99→9）、反直觉数值（体重下降 0g）；值内部自相矛盾、值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥）、数值关系不合理（如氧合指数与 PO2/FiO2 明显不符）→ 均应标记。

**修改 3 — 原则 7 尾部加"有证据不豁免"句（B 类复核器侧）**

现状：`字段越界：值的内容域与字段对应部位明显不符（如眼部字段出现一般情况内容）→ 标记为 extraction_mistake，引用原文片段即可。`

追加：
> 字段越界不因值有证据支持而豁免——证据同源只证明原文有这段话，不证明它属于该字段。

**修改 4 — few-shot 新增 2 个行为示例（A/C 类执行纠偏）**

在现有输出示例后追加（标注"示例仅示范结构，字段内容为占位，不得照抄"沿用现有约定）：

示例 1（值忠实摘录但含错读 → 标记）：
```json
{"verifications": [{"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e005 值忠实摘录原文，但'双眼粗侧视力正常'中'粗侧'为 OCR 错读（应为'粗测'）"}]}
```

示例 2（值与他句矛盾 → 标记）：
```json
{"verifications": [{"field_key": "pe_abdomen", "verdict": "suspicious", "reason_code": "extraction_mistake", "checks": {"value_semantically_supported": false, "no_hallucination_or_inference": true, "ocr_correction_justified": true}, "comment": "e012 同段既有'腹部正常，肝脾肋缘下未扪及'，值却写'腹部移动性浊音阳性'，两处矛盾，疑否定翻转"}]}
```

设计依据：形态识别靠原则（叠字/近形/残缺模式类别 + "常见模式而非全部"），行为示范靠示例；历史证据（v3 的 8 个错读例子收益递减）表明 case 级堆叠无效，示例不必覆盖全部形态。

### 3.2 抽取 prompt（1 处 + 渲染）

**修改 5 — schema 加 pe_* 字段 description + 字段表渲染追加**

- `app/config/schemas/admission_record_structured_fields.v1.yaml`：内容型 pe_* 字段加 `description` 元数据（只加元数据，不动字段体系/枚举）；
- `prompts.py` 字段表生成（`build_admission_structured_fields_messages` 第 1 节）：有 description 时渲染为 `- [组] field_key（label）；仅：<description>`，无 description 的字段不变；
- 数值型字段（pe_temperature/pe_pulse/pe_respiration_rate/pe_blood_pressure/pe_height/pe_weight/pe_bmi）**不加**描述（越界风险低，控长度）。

描述定稿（13 条，实施时逐字用）：

| 字段 | description |
|---|---|
| pe_skin | 皮肤项目：颜色、皮疹、弹性、毛发、淋巴结；不含一般情况内容 |
| pe_eyes | 眼部项目：睑结膜、球结膜、巩膜、角膜、瞳孔、对光反射、视力；不含头颅、头发、颜面、耳鼻口颈内容 |
| pe_ears | 耳部项目：外耳道、鼓膜、听力、乳突；不含眼、鼻、口咽内容 |
| pe_nose | 鼻部项目：鼻腔、鼻窦、鼻翼、鼻通气；不含耳、口腔内容 |
| pe_oral_cavity | 口腔咽喉项目：唇、齿、龈、舌、口腔黏膜、咽、扁桃体；不含颈部、耳鼻内容 |
| pe_neck | 颈部项目：颈静脉、颈动脉、甲状腺、气管、颈软、淋巴结；不含口腔、胸部内容 |
| pe_chest | 胸廓项目：胸廓形态、肋间隙、胸骨、挤压试验；双肺内容归呼吸系统检查，乳房内容归乳房字段 |
| pe_breast | 乳房项目：对称、发育、乳头、皮肤、包块；不含胸廓、双肺内容 |
| pe_respiratory_exam | 呼吸系统项目：呼吸动度、语颤、叩诊音、呼吸音、啰音；不含胸廓形态、乳房内容 |
| pe_cardiac_exam | 心脏项目：心前区、心尖搏动、心界、心率、心律、心音、杂音 |
| pe_abdomen | 腹部项目：腹壁、压痛、肝脾、移动性浊音、Murphy 征 |
| pe_limbs | 四肢脊柱项目：脊柱、关节、肌力、水肿、静脉曲张、病理征 |
| pe_neurological_exam | 神经系统项目：神志、精神、对答、反射、病理征；一般情况（发育/营养/体型/体位/表情）不属本字段 |

## 4. 验证方案

### 4.1 单测（实施时同步）

- `test_copd_verifier.py`：新措辞断言（表达瑕疵阈值句、逻辑一致性句、有证据不豁免句、2 个新示例存在且占位标注沿用）；
- `test_copd_prompts.py`：字段表 description 渲染断言（有 description 的字段渲染含"；仅："，数值型字段不含）；
- 跑通 `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_verifier.py -v`。

### 4.2 step5 实验（协调者执行）

1. `run_eval` 全量（对比 step4：status/value/幻觉不回退）；
2. `calibrate export` 生成新 verdicts；
3. 同一批 6 个 AI judge 包 → 新 AI 裁定 → 对比 step4：
   - 漏检 18 → 目标显著下降（如 <5）；
   - 误报 1 → 不显著增加；
   - kappa 0.0834 → 提升（不设硬线）；
4. 用户重点确认：优化后重新生成 focus 页（AI 应标 + 拿不准），用户审剩余条目；
5. 报告（markdown + HTML，数据留 `data/evaluation/`，不进 git）。

### 4.3 数据与隐私

- 评估产物（verdicts、judge 包、报告）留在 `data/evaluation/`，不进 git；
- spec 与 prompt 只含短语级示例，不含真实病历数据。

## 5. 代价记录（如实）

- 抽取 system：+520 字符（13 条描述），4788 → 约 5300（+11%）；
- 复核器 system：+250 字符（3 句 + 2 示例），2027 → 约 2280（+12%）；
- 均为有效载荷（非冗余复读）；前缀缓存前提（system 固定）不变。

## 6. 文档同步

- 更新 `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md` 3.2 节（缺陷清单/通用原则措辞随本轮变更）；
- 本轮 spec 记录 schema `description` 元数据变更与字段表渲染变化（copd_extraction/CLAUDE.md 的 schema 契约要求：字段增删须同步 spec 与 PRD 引用——本变更非字段增删，仍记录在案）。

## 7. 未来工作项（本次不做）

- 抽取侧"字段边界理解过宽"的根治（切分粒度优化、或字段表描述效果不足时考虑字段级 few-shot）；
- 人工全量评定 → 官方 kappa（医生逐条评 281 条，工作量决策在用户）；
- 一般情况字段（需 PRD、spec、前端展示、导出联动）。
