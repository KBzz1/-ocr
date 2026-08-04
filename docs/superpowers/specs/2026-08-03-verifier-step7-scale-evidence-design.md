# 复核器尺度与证据装配优化设计（Verifier Step7）

> 日期：2026-08-03
> 状态：草案（待审阅）
> 关联：`2026-08-02-verifier-chunked-review-experiment-design.md`（step6，本设计为其后续）；复核器设计权威 `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`
> 分支：worktree-prompt-refactor-field-boundary

## 1. 背景与动机

step6 分块实验（8月2日晚）已出结论（见 `data/evaluation/reports/20260802-verifier-overall-analysis.html`）：

| 形态 | 漏检 | 误报 | kappa |
|---|---|---|---|
| 整篇原文（旧评估口径，step5） | 11 | 3 | 0.53 |
| 上岗形态（生产，基线₂） | 10 | 10 | **0.40** |
| 字段级分块（实验 A） | **6** | 47 | 0.34 |
| 章节分块（实验 B） | 9 | 19 | 0.33（数据受损，234 条口径） |

三个已确认的事实：

1. **评估口径失真已修正**：生产形态（字段证据）真实 kappa 0.40，低于旧口径 0.53；
2. **分块能显著提升发现力**：字段级分块把此前全部漏掉的典型错读（吸支性/回流征性/胸状胸/古手）与字段越界全挑出，漏检 14→6——"看得细"方向正确；
3. **分块误报失控，机制明确可修**：47 条误报 = 证据不完整→"证据不足就乱怀疑"（28）+ 证据编号对不上（13）+ 正确用字当错读（6）。

代码现状（2026-08-03 核实）：

- 工作区 `build_verification_messages` 已是**精简五步式**（用户差量，未提交；HEAD 为"通用原则 7 条"完整版）——checks 键已改为 `grounding_supported/field_scope_valid/ocr_text_clear/logic_consistent`，示例为纯文字（无 JSON）；
- 8月3日下午起草的"更新版"prompt（JSON 结构示例 + 输出契约节 + cited ID 预检声明）**仅存在于 overall-analysis 报告附录，未落地**；
- step5 已验证的措辞（表达瑕疵阈值句、逻辑一致性扩展句、越界不豁免句）在精简版中被压缩丢失。

### 方法论来源（用户裁决，2026-08-03）

本步**继承 PPEMA-V1（prompt-policy-metric-alignment-v1）的验证范式**——用户确认其结果为正向（GPT-5.5 冻结预期 8 项全命中、指标修正是确定性证据、版本化交付），step7 不在 step6 实验路线上继续（该路线 kappa 0.53→0.40 为负向），而是把 PPEMA 四项可迁移原则落到复核器：

| # | PPEMA 原则（已验证） | step7 落点 |
|---|---|---|
| P1 | prompt 策略显式化：字段策略/边界逐字进 prompt | 复核器判定规则/字段范围/输出契约逐字定稿（§3.1） |
| P2 | 指标与策略对齐：修正口径为唯一真值，禁混用旧口径 | 复核器唯一真实口径 = 基线₂（字段证据形态）；整篇口径不再作结论依据 |
| P3 | 冻结预期验证：先定数字，跑完对照命中 | §2.1 冻结预期表；命中=修复有效的确定性证据 |
| P4 | 版本化 + 报告产物 | verifier.v1→v2 登记 `version-registry.md`；报告留 `data/evaluation/` |

归因边界（继承 PPEMA）：prompt 修订与证据装配是两个独立变量，实验矩阵隔离；kappa 依赖 AI judge 裁定（主观指标），只报命中/未命中，不做"复核器能力"结论。

## 2. 目标与边界

### 目标

1. **复核器 prompt 尺度修订（verifier.v2 定稿）**：以工作区精简版为真身，吸收附录草案（输出契约节 / JSON 结构示例 / cited ID 预检声明），恢复 step5 已验证行为句（错读阈值、逻辑一致性细节），新增防"正确用字当错读"措辞；
2. **证据装配修复**：复核器消费的证据 unit id 与字段 `evidence_ids` 引用同源（编号统一）；每组请求携带该组字段的**完整**证据来源（消"证据不足乱怀疑"）；
3. **step7 实验**：两臂——基线₂'（定稿 prompt + 上岗形态）与 A'（定稿 prompt + 字段级分块 + 完整证据）；
4. **版本注册**：定稿发布为 `verifier.v2`，登记 `docs/Shared/version-registry.md`。

### 2.1 冻结预期（P3：先定数字，测后对照命中/未命中）

按 PPEMA 范式，实验前先冻结预期数字（依据：step6 实测基线 + 两类误报机制可消性），测后逐项对照：

| 指标 | step6 基线 | 冻结预期 | 依据 |
|---|---|---|---|
| A' 误报 | 47 | **≤15** | 28（证据不足）+13（编号错位）机制消除后，剩 6 条"正确用字"靠 P1 措辞压 + 存量 |
| A' 漏检 | 6 | **≤6（不回退）** | 分块发现力保持；定稿 prompt 不得削弱 |
| A' kappa | 0.34 | **≥0.5** | 误报大幅下降后 kappa 自然回升（保守值，不设硬线） |
| 基线₂' 误报 | 10 | **≤5** | P1 措辞压"正确用字当错读"+ 尺度问题 |
| 基线₂' 漏检 | 10 | **≤10（不回退）** | 漏检修复不倒退 |
| 基线₂' kappa | 0.40 | **≥0.5** | 同上保守值 |

命中=修复有效的确定性证据；未命中=如实报告并定位（继承 PPEMA 的负结果保留原则，不重跑不调参）。

### 边界（明确不做）

- **B 形态（章节分块）本轮不做**——数据受损且表现垫底（0.33），降级为观察项；
- 不改 verdict / reason_code 枚举、不改输出 JSON 形状（顶层 verifications）、不改 checks 键名（已定稿四布尔）；
- 不改 `evidence_units.py` 切分逻辑；
- 不改抽取器 prompt、不改字段体系；
- 不新增字段级 few-shot（若召回仍不足为下轮手段）；
- 不做人工全量评定（沿用 AI judge 增量裁定 + 用户重点确认混合口径）；
- 温度恒为 0.0；system 定稿后逐字节固定（vLLM 前缀缓存前提）。

## 3. 修改点

### 3.1 复核器 prompt 定稿（`prompts.py::build_verification_messages` system）

逐字定稿（工作区精简版 + 附录草案 + step5 行为句融合）：

```text
你是慢阻肺入院记录的字段级复核器。你只核验给定字段是否被给定 OCR 证据支持，不改写字段值、不补造证据、不提供医学建议。

【固定审核顺序】
1. grounding：先在 cited evidence 中核对声称值；完整值不连续时按句号、分号或换行拆成事实片段，再逐片段核对。普通逗号、顿号列表不拆开。
2. field scope：检查内容是否属于该字段定义的部位、项目和时间范围；原文支持但字段越界仍应标记。
3. OCR quality：只标记证据中确实可定位、且影响理解或造成歧义的 OCR 病句、残缺、标签或单位问题；不要凭医学常识猜测修正词。正确用字、符合规范的表述不得标记；错读/病句/叠字等表达瑕疵：影响理解或产生歧义 → 必须标记，不影响语义理解的轻微重复可不标；值忠实摘录原文不豁免错读检查——值一致只证明抄得对，不证明文本本身没问题。
4. logic consistency：检查否定/不确定、时间归属、数值关系和字段内部是否自相矛盾；值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥、数值关系不合理）→ 均应标记；不能从常识补出证据不存在的事实。
5. verdict：四项检查全部通过才 pass；任何一项明确失败才 suspicious。调用方已在请求前检查 cited ID 是否完整，证据装配缺失不归因于字段。

【判定与原因】
- grounding、字段越界、时间归属、否定翻转或逻辑矛盾 → reason_code=extraction_mistake。
- 可定位且影响理解的确切 OCR 病句 → reason_code=ocr_quality_issue。
- pass 的 reason_code 必须为 none；不要把语义等价、多个有序证据片段聚合或正常族归一误报为问题。
- 只生成 pass 或 suspicious。历史数据可能含 fail，解析器会兼容，但本次不要生成 fail。

【输出契约】
输出单个 JSON 对象，顶层只有 verifications。数组与输入字段一一对应，不能重复、遗漏或新增字段。每项固定包含：
- field_key：输入字段 key；verdict：pass 或 suspicious；reason_code：extraction_mistake、ocr_quality_issue 或 none。
- checks：只包含 grounding_supported、field_scope_valid、ocr_text_clear、logic_consistent 四个布尔值。
- comment：不超过 40 个汉字。pass 写"一致"；suspicious 必须引用真实 uXXX 和具体疑点。

【示例一：原文支持但字段越界】
{"verifications":[{"field_key":"pe_eyes","verdict":"suspicious","reason_code":"extraction_mistake","checks":{"grounding_supported":true,"field_scope_valid":false,"ocr_text_clear":true,"logic_consistent":true},"comment":"u001 原文属一般情况，不属眼部"}]}

【示例二：完整、有据、无问题】
{"verifications":[{"field_key":"pe_respiratory_exam","verdict":"pass","reason_code":"none","checks":{"grounding_supported":true,"field_scope_valid":true,"ocr_text_clear":true,"logic_consistent":true},"comment":"一致"}]}

示例只说明结构和裁定边界，不要照抄其中的证据或字段值。
```

定稿 vs 工作区版的关键变化：

| # | 变化 | 对应问题 |
|---|---|---|
| 1 | 第 5 条追加 cited ID 预检声明（证据装配缺失不归因于字段） | 评估口径≠生产口径时的误报归因 |
| 2 | 第 3 条恢复错读阈值句 + 新增"正确用字、符合规范的表述不得标记" | 6 条"正确用字当错读"误报 |
| 3 | 第 4 条恢复逻辑一致性细节（时间归属/否定翻转/体征互斥/数值关系） | step5 已验证行为句丢失回退 |
| 4 | 新增【输出契约】节（顶层 verifications 一一对应、五字段、checks 四布尔、comment 规则） | 结构漂移风险 |
| 5 | 示例从纯文字改为 2 个 JSON 结构示例（越界 suspicious + 全通过 pass）+ 占位标注 | 结构示范缺失 |

### 3.2 证据装配修复（`verifier.py` + 评估侧 `chunked_review.py`）

**编号统一**：复核器消费的证据 unit id 必须与字段 `evidence_ids` 引用的 id 一致。

- 生产链路已同源（`map_qwen_fields_to_review_candidates` 按 `evidence_ids` 回填字段自己的 units，`assemble_verification_groups` 消费同一份 id）；
- 评估链路（`chunked_review.py` 值定位回填）须保证生成的 unit id 与 `evidence_units.py::build_evidence_units` 生产侧同规——评估侧 `--inject-evidence` 构建 units 后，字段引用定位回填用**同一 units 的 id**，不得另造编号（step6 的 13 条编号错位来源即此）；
- 校验：每组请求前检查字段 `evidence_ids ⊆ 该组 units ids`，不满足的字段在请求前剔除并留痕（不送审），而非带错误编号进 prompt。

**完整证据来源**：`verify()` 分组时每组携带该组字段的**全部** evidence units（按字段去重聚合），字段引用缺失时**不得**回退为"全文兜底"（`_collect_evidence` 的 `document_text[:8000]` 兜底仅保留给无 evidence_units 的兼容调用方）——消 step6 的 28 条"证据不足就乱怀疑"。

### 3.3 分组组织（`verifier.py`）

- 字段级分块（`group_by="field"`）保留为 A' 形态；B（章节）不做；
- 失败语义保持现状（每组独立 try，单组失败跳过，全组失败降级为空）；
- system 定稿后逐字节固定，分组请求以同一 system 前缀开头，前缀缓存前提不变。

## 4. 验证方案（step7 实验）

1. `run_eval` 全量（确认抽取侧不回退）；
2. `calibrate export` 两臂：基线₂'（定稿 prompt + 上岗形态）与 A'（定稿 prompt + `--group-by field` + 完整证据）；
3. AI judge 增量裁定：与 step6 合并裁定（`20260802_adjudications_ai_step6_incremental_merged.json`）对比，只对 verdict 差异字段派同批 6 judge 增量重裁（沿用 step6 §6.2 策略）；
4. 指标对比（口径统一到 step6 裁定 + 增量裁定）：
   - kappa（基线₂' / A' vs step6 基线₂ / A）；
   - 漏检：step6 的 6 条是否保持修复，有无新增；
   - 误报：47 → ？，三类来源（28/13/6）各自的修复数；
   - 工程代价：每 case 请求数、总 prompt 字符、复核阶段 LLM 调用次数；
5. 用户重点确认 focus 页（同 step5/step6 口径）。

## 5. 测试约定

- `test_copd_verifier.py`：定稿措辞断言（输出契约节、cited ID 预检句、错读阈值句、2 个 JSON 示例存在且占位标注）；分组调用每组收到字段完整证据断言；`evidence_ids ⊆ units ids` 剔除断言；
- `test_copd_prompts.py`：verifier system 定稿断言、`VERIFIER_PROMPT_VERSION == "verifier.v2"`（定稿发布后）；
- 全量 pytest 保持通过（既有失败与本工作无关，勿修）。

## 6. 代价记录（如实）

- 复核器 system：工作区 987 字符 → 定稿约 1500 字符（+50%），均为有效载荷；定稿后固定，前缀缓存前提保持；
- 请求数：基线₂' 1/case；A' 35–61/case（同 step6 实测量级）；
- 代码改动：`prompts.py`（system 定稿 + 版本常量 v2）、`verifier.py`（分组证据装配/剔除校验）、评估侧 `chunked_review.py`（id 同规），prompt 措辞与输出契约零变更之外全部有单测。

## 7. 版本注册

- 复核器 prompt：`verifier.v1`（工作区精简版，2026-08-03 建档）→ **`verifier.v2`**（本 step 定稿发布）——按 `docs/Shared/version-registry.md` 规则登记（内容改动先登记再动代码）。

## 8. 文档同步

- 实验通过后：出 plan 落地生产路径时同步 `2026-08-01-verifier-normalization-design.md` 的 3.2 节（prompt 措辞随本轮变更）与调用组织描述；
- 更新 `docs/Shared/version-registry.md` 复核器迭代表。

## 9. 未来工作项（本次不做）

- 字段级 few-shot（A' 召回仍不足时的下一手段）；
- 人工全量评定 → 官方 kappa（工作量决策在用户）；
- 一般情况字段（需 PRD、spec、前端展示、导出联动）。
