# 复核器分块审核实验设计（Chunked Review Experiment）

> 日期：2026-08-02
> 状态：草案（待审阅）
> 关联：`2026-08-02-verifier-recall-optimization-design.md`（step5，本设计为其下一轮实验）；复核器设计权威 `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`
> 分支：worktree-prompt-refactor-field-boundary
> 性质：**实验设计**，评估通过前不改生产复核路径；verdicts 契约与 prompt 措辞不变

## 1. 背景与动机

step5（3 句措辞 + 2 个 few-shot 示例 + 13 条 pe_* description）结果：kappa 0.0834→0.5347、漏检 18→14（真实修复 7）、误报 1→3、抽取侧无回退。**仍漏 7 条**的形态共性：值忠实摘录原文，但原文本身有局部问题（吸支性/回流征性/胸状胸/古手错读、pe_eyes 整段越界、hpi 时间归属、氧合指数 961）——全是被长文本整体语义通顺带过。

现状复核器调用组织（`verifier.py`）：`verify()` 对一份病历的**全部候选字段**（实测 35–61 字段/case）构造**一条** LLM 请求——user 消息 = 全字段证据 unit 去重聚合 + 全字段值块，模型一次输出全部 verdicts。证据粒度（`evidence_units.py` 按句号/分号/新行切分）已经存在且稳定，但复核器消费时全部拼接。

**假设**：一次请求 40–60 字段 + 全量证据的上下文稀释了模型注意力，"逐句扫读"指令在单字段粒度下才真正可执行；把请求按字段（或字段簇）切分后，A 类 4 条 + B 类 1 条仍漏有望被标记。

**用户提出方向**：整体切分成一段一段审核，同时保证吃到 KV cache（前缀缓存）。

### 1.1 评估口径发现（用户指出，已核实）

复核器证据注入存在**评估口径 ≠ 生产口径**，前面 step4/step5 全部指标（kappa 0.0834→0.5347、漏检/误报）反映的不是生产复核器真实值：

| 链路 | evidence_units | candidates evidence | 复核器实际看到的证据 |
|---|---|---|---|
| 生产（orchestrator.py:131-133） | orchestrator 用 `build_evidence_units` 构建并传入抽取 | 抽取输出 `evidence_ids` → `map_qwen_fields_to_review_candidates` 回填**字段自己的 units** | `_collect_evidence` 聚合 = **字段证据 unit 聚合**（聚焦、unit 粒度） |
| 评估（run_eval.py:81 `_input_for`） | 硬编码 `evidence_units: []` | 回填空数组 | `_collect_evidence` 兜底 = **整篇 OCR 原文**（document_text[:8000]） |

事实细节：① 当前 6 个 golden 样本 ocr_text 均 < 8000 字符（1835–3561），"前 8000 截断"在评估样本上未实际触发，但真实长病历 > 8000 时会丢后半证据（含辅助检查/诊断段）——生产隐患；② 评估形态下证据块只有一条 `doc：<全文>`，复核器被迫在整篇里找每个字段的问题，错读句被长文本淹没——这正是"仍漏 7 条均为长文本局部问题"的结构性原因之一。

**结论**：step4/step5 指标是"整篇原文版"复核器的指标，不代表"字段证据版"（生产形态）复核器；评估管线必须先修证据注入（让评估复核器吃字段证据，逼近生产形态），才能谈分组实验。证据注入机制：评估侧从 ocr_text 构建 units（复用 evidence_units 切分规则）→ 按字段值定位回填（值前 8 字符命中 unit + 前后邻接各 1 个）——这是生产 `evidence_ids` 回填的**近似替代**（值定位 vs LLM 引用，证据集可能略有差异，作为口径近似记录在案）。

## 2. 方案

### 2.1 请求组织变化

| | 现状（step5） | 实验（step6） |
|---|---|---|
| 请求数 | 1 条/case（全证据 + 全字段） | N 条/case（每字段或每字段簇 1 条） |
| 每条 user 消息 | 全字段证据聚合 + 全字段值块 | 该组字段自己的证据 unit + 值块 |
| system | 固定（2911 tokens） | **逐字节不变** |
| 输出 | 一次全量 verdicts | 每组各自的 verdicts，合并后契约不变 |

### 2.2 实验变量：两种形态

- **形态 A（字段级）**：每字段 1 条请求，只带该字段自己的 evidence units + 值。
- **形态 B（字段簇级）**：按 evidence_units 的 `section_key`（主诉/现病史/既往史/体格检查/辅助检查…）分组，同节字段 1 条请求，保留同节内跨字段参照。

### 2.3 数据可切性（无新切分逻辑）

字段的 `evidence` 数组已由 `admission_contract.map_qwen_fields_to_review_candidates` 按 `evidence_ids` 回填（每字段自己的 unit 列表），**天然可切**；`evidence_units.py` 切分逻辑不动。现有 `build_verification_messages(evidence_units, fields)` 输入即为"证据子集 + 字段子集"，直接复用（system 字符串不碰）。

## 3. 关键约束（KVCache 前提）

- **system 字符串逐字节不变**（2911 tokens）：vLLM 前缀缓存按 token 前缀匹配，user 每次不同不影响 system 前缀命中——切分后每条请求仍以同一 system 开头，缓存行为与现状完全相同，且每条请求更短、无长 prompt 分块 prefill。
- **公共内容不得挪进 user**：缓存唯一来源是 system，任何从 system 移出的公共指令都会破坏前提。
- 温度恒为 0.0；输出契约（JSON 形状、verdict/reason_code 枚举、checks 结构）不变；`_parse_verdicts` 按 field_key 过滤与 `apply_verdicts` 合并逻辑不变。
- 失败语义（拟变更，需用户确认，见 §5）：现状"任何异常 → 整体降级为空意见"；切分后建议"**每组独立 try，失败组静默跳过，其余组正常；全组失败才降级为空列表**"——复核意见缺失只影响 suspicious 标记，字段仍可人工核验，部分失败不应连坐全部字段。
- 不动 evidence_units 切分逻辑、不动 schema 字段体系、不新增字段、不改 reason_code 枚举。

## 4. 已知权衡（切分的损失与对策）

| 权衡 | 影响 | 对策 |
|---|---|---|
| **跨字段矛盾丢失** | C 类 hpi_recent_symptoms（11 年前"无发热" vs 本次 39.5℃，39.5℃ 在体温字段证据里）：形态 A/B 均看不到 | 形态 B 保留同节参照；跨节矛盾只能靠"字段级 + 一条全量兜底"混合形态（第三臂，见 §6） |
| C 类同段矛盾 | pe_abdomen（示例 2 形态）、氧合指数 961 vs PO2/FiO2：血气组是单 unit 不切分，同字段证据内可见 | **不丢**，切分无影响 |
| 误报侧 | 现有 3 条误报均为单字段上下文内问题，切分影响有限；但独立上下文失去他字段参照（如房颤脉短绌"合理不一致"）可能新增误报 | 实验观察，作为指标跟踪 |
| 请求数 | 1 → 35–61/case（形态 A），HTTP 往返增加 | vLLM 并发批处理；每条 payload 短，单请求延迟低 |
| prefill 总量 | system 部分缓存命中只 prefill 一次；各请求 user 部分 = 各自证据，与全量聚合相当或更小（无重复聚合） | 实验时统计实际 prefill token 量 |
| 泛化陷阱（"粗测"过度标） | 字面模式依赖在单请求内仍存在，切分不解决 | 不在本轮范围 |

## 5. 修改点（实验实现范围）

- `verifier.py`：`verify()` 由一次调用改为循环分组调用；`_collect_evidence` 改为按组取该组字段的 evidence（数据直接来自各字段 `evidence` 数组）；**失败语义按 §3 拟变更**（每组独立 try-catch，失败组跳过，全组失败降级为空）。
- `prompts.py`：`build_verification_messages` 复用（证据子集 + 字段子集），system 字符串零改动；不改任何措辞。
- 单测（`test_copd_verifier.py`）：fake LLM 下断言分组调用次数、每组收到的证据/字段子集正确、各组 verdicts 合并完整、单组失败不影响其他组、全组失败降级为空。
- `calibrate.py` export 子命令加 `--inject-evidence`（布尔）与 `--group-by {field,section}` 两个向后兼容参数（§1.1 证据注入修正 + 四臂组合开关）；`chunked_review.py` 承载 units 构建与值定位回填；默认不传参数时行为与现状完全一致（基线₁ 复用前提）。

## 6. 实验设计（step6）

### 6.1 实验矩阵（4 臂，变量隔离）

| 臂 | 请求组织 | 证据形态 | 意义 |
|---|---|---|---|
| 基线₁ | 一次全量（现状） | 整篇原文（评估现状） | 历史对照——**复用 step5 verdicts 与 step5 AI 裁定**（温度 0.0 + 同输入，复核器输出确定性相同，零重跑） |
| 基线₂ | 一次全量（现状） | 字段证据聚合（注入后） | **生产形态现状**——生产复核器真实指标；vs 基线₁ 量化"评估口径失真" |
| A | 字段级切分 | 字段证据聚合 | 分组效果（vs 基线₂ 为干净对比：仅"分组"一个变量） |
| B | 字段簇级切分 | 字段证据聚合 | 同节跨字段参照保留（vs 基线₂） |
| C* | A/B + 一条全量兜底请求 | 字段证据聚合 | 若 A/B 显示 C 类跨节矛盾丢失明显，再跑（可选第五臂） |

\* 收敛原则：先跑基线₂/A/B 三臂，根据 A/B 中 hpi 时间归属类是否丢失再决定是否跑 C。

### 6.2 AI 裁定复用策略（用户确认）

- **基线₁ 臂**：直接复用 step5 verdicts + step5 AI 裁定（`20260802_adjudications_ai_step5.json`），不重跑、不重裁（确定性输出，详见 §1.1）；
- **基线₂/A/B 臂**：只对"verdict 与 step5 不同的字段"派**同一批** 6 个 AI judge 增量重裁（judge 包 items = 差异字段，ocr_text 不变），未变字段复用 step5 裁定——省掉三臂全量 judge 成本，且差异字段的裁定在同批口径内可比；
- 若某臂 verdicts 字段集合与 step5 不同（增/减），集合差异字段一并增量裁定。

### 6.3 流程（协调者执行）

1. `run_eval` 全量（对比 step5：status/value/幻觉不回退）；
2. 导出基线₂/A/B 三臂 verdicts（基线₁ 复用 step5；每臂 1 份，口径同 step5 的 284 条）；
3. 三臂 verdicts 与 step5 verdicts 的差异核对（逐条列出 verdict 变化字段：基线₂ 揭示"证据形态"变量的影响面，A/B 揭示"分组"变量影响面）；
4. 差异字段增量裁定（§6.2 策略）→ 合并出各臂完整裁定；
5. 对比指标：
   - kappa（基线₁ vs 基线₂ vs A vs B，口径统一到 step5 裁定 + 增量裁定）；
   - 漏检：A 类 4 条 / B 类 1 条 / C 类 2 条 各自的修复与新增；
   - 误报：与 step5 的 3 条对比，不显著增加；
   - **基线₂ vs 基线₁**：评估口径失真量化（生产形态复核器 vs 整篇版复核器）；
   - 跨字段矛盾丢失数（C 类 hpi 时间归属是否保住）；
   - 工程代价：每 case 请求数、总 prompt 字符（system+user 实测，1 汉字≈1 token 估算）、复核阶段 LLM 调用次数。
6. 用户重点确认 focus 页（同 step5 口径）。

### 6.4 成功标准

1. A 类仍漏 4 条（吸支性/回流征性/胸状胸/古手）至少修复 2 条（A/B 臂 vs 基线₂）；
2. B 类 case_002 pe_eyes 越界被标记；
3. C 类不新增漏检（形态 B 下 hpi 时间归属、氧合指数保持可检）；
4. 误报不显著增加（相对 step5 的 3 条）；
5. 基线₂ vs 基线₁ 明确量化"评估口径失真"程度（无论好坏如实记录）；
6. kappa 提升（不设 0.7 硬线，与 step5 相同策略）。

## 7. 代价

- system 长度不变（2911 tokens），前缀缓存前提保持（§3）；
- 请求数 1 → N/case；HTTP 往返与 vLLM 调度增加，payload 单条变短；
- prefill 总量与现状相当或更小（证据无重复聚合、system 只 prefill 一次）；
- 代码改动集中在 `verifier.py`（循环分组 + 失败语义），prompt 措辞与输出契约零变更。

## 8. 边界（明确不做）

- 不改 `evidence_units.py` 切分逻辑；
- 不改 prompt 任何措辞（本次只改请求组织，不改内容）；
- 不改 reason_code 枚举、schema 字段体系、输出契约；
- 不引入字段级 few-shot（§9 未来项）；
- 不做人工全量评定（AI judge 同批三臂裁定 + 用户重点确认的混合口径，同 step5 裁决）。

## 9. 未来工作项（本次不做）

- 字段级 few-shot（A/B 召回仍不足时的下一手段）；
- 抽取侧"字段边界理解过宽"根治（B 类根因，spec §7 已列）；
- 人工全量评定 → 官方 kappa（工作量决策在用户）；
- 一般情况字段（需 PRD、spec、前端展示、导出联动）。

## 10. 文档同步

- 实验通过后：出 plan 落地生产路径时同步 `2026-08-01-verifier-normalization-design.md` 的调用组织描述；
- 本轮 spec 只记录实验设计，不视为生产契约变更。
