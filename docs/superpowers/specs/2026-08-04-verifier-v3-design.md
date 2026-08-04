# 复核器 v3 设计：非标准表述契约 + 判别细则 + 字段级调用（Verifier v3）

> 日期：2026-08-04
> 状态：草案（待审阅）
> 关联：`2026-08-03-verifier-step7-scale-evidence-design.md`（v2 定稿，本设计为其后续）；复核器设计权威 `docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`（spec 5.2 上岗门槛 kappa≥0.7）
> 分支：worktree-prompt-refactor-field-boundary

## 1. 背景与动机

verifier.v2 冒烟（2026-08-03 22:29，唯一真实 case_006 / Qwen3.5-4B / temp 0，报告 `20260803-verifier-opt-v1-report.html`）结果：

| 项 | 值 |
|---|---|
| verdicts 覆盖 / 契约违规 / 装配误报 | 61/61，0，0 |
| TP/FP/FN/TN | 1/3/5/52 |
| Po / Pe / kappa | 86.9% / 84.9% / **0.1317**（provisional，仅陈列） |
| 漏检 5 条形态 | 长字段整段摘录内嵌错读（胸状胸、古手）、越界（神经系统混入一般情况）、数值矛盾（氧合指数 961） |

### 1.1 漏检机制分析（三层，已核实）

1. **拆句核对失效**：`grounding` 按句号/分号/换行拆 value 片段，而 pe_chest 的 value 74 字只有句尾 1 个句号 → 拆出 1 个片段 = 整段，"逐句核对"无拆分效果，整段语义通顺被放行。
2. **判别标准缺失 + 微例后门**：system 只有"- 术语陌生……不构成明确问题 → pass"，无"术语陌生 vs 错读"二分；微例 4（粗测听力正常→pass）形态上与「胸状胸」几乎一致，模型把错读归类为"陌生术语"放行。反证：微例 3 本就是「古手」错读示例，真实 case 里照样漏——注意力稀释（60+ 字段挤一请求）使模型根本没"看到"该字。
3. **归因困境**：`reason_code=ocr_quality_issue` 强制归因"这是 OCR 造成的"，而复核器只看到文本，无法区分 OCR 错读/原文固有瑕疵/摘录问题；同时"不要凭医学常识猜测修正词"的约束让模型不敢断言错读——标错读需要先知道正确词，而 prompt 禁止猜词。

### 1.2 调用形态实测（2026-08-04，case_006 61 found 字段，temp 0）

数据：`data/evaluation/reports/20260804-verifier-parallel-vs-serial-timing.json`

| 方式 | 请求数 | 总耗时 | 单请求均值 | 说明 |
|---|---|---|---|---|
| A. section 分组串行（现状） | 8 | 52.8s | 6.6s | 最大组 20 字段 17.0s |
| B. 字段级分组串行 | 61 | 66.4s | 1.09s | 首个 1.27s，KV cache 命中后稳定 |
| C. 字段级分组并行(8) | 61 | 65.9s | 感知 8.2s | **并行无收益**：`qwen_vllm_max_num_seqs=1` 服务端排队 |

结论：**当前服务端配置下并行不加速（客户端并发在服务端排队），选择字段级分组 + 串行**；单例复核 66s 在任务流程（抽取后、审核前，异步后台）可接受。若未来需并行加速，前提是服务端 `max_num_seqs>1`（部署侧变更，另立任务）。

## 2. 目标与边界

### 目标

1. **契约改名**：`reason_code` 枚举 `ocr_quality_issue` → `nonstandard_expression`（非标准表述）；`checks` 键 `ocr_text_clear` → `text_standard`（表述规范）。解除归因困境：复核器只需观察"表述是否标准"，不归因、不猜修正词。
2. **判别细则落地 prompt**："术语陌生"（规范医学/日常用词，如粗测/代偿）→ pass；"非标准表述"（非任何标准用词、形近/音近标准词、病句、残缺）→ suspicious；明确"不需要给出修正词"。
3. **对照微例**：微例 4 改为对照式——规范但少见用词 → pass 与 错读但形似规范词 → suspicious 并排展示（u911-u914 段重写）。
4. **拆句边界扩展**：`grounding` 拆句从句号/分号/换行扩展到逗号/顿号级（value 超长时），含否定作用域豁免（"否认/无/未见"片段不拆，沿用证据切分器 `_looks_like_history_negation_scope` 思路）。
5. **字段级分组调用**：复核调用从 `group_by="section"` 改为 `group_by="field"`，串行；换注意力集中（单 claim + 小证据区），KV cache 收益保留（system 固定）。
6. **版本登记**：定稿发布 `verifier.v3`，登记 `docs/Shared/version-registry.md`。

### 验证范围（用户 2026-08-04 指示放宽：边界可扩大、不担心耗时）

- **全量 6 例验证**：重跑 case_001~006 抽取（extractor.v4，本步授权；此前"仅一次"限制取消）→ 6 例复核全量冒烟。耗时预算：复核每例 ~66s（字段级串行）× 6 ≈ 7 分钟，加抽取时间，可接受。
- **kappa 6 例口径**：6 例复核结果对 `adjudications_library.json`（287 条 AI 模拟裁定，覆盖全部 6 例）重算 kappa，样本从 1 例扩到 6 例；口径仍为 provisional（非人工金标），记录变化方向，不作上岗结论。

### 边界（本步不做）

- 不调 LLM-as-Judge / 人工裁定（kappa 口径维持 provisional，仅作参考不作上岗结论）；
- 不改证据切分器（长证据行是 OCR 形态，逗号切分破坏否定作用域，保持现状）；
- 不调 vLLM 服务端 `max_num_seqs`（并行已实测无收益：max_num_seqs=1 排队；串行全量耗时已满足预算）；
- 不改抽取器 prompt。

## 3. 变更清单（契约层）

### 3.1 `response_schemas.py` — `build_verification_json_schema`

- `checks` required/properties 键：`ocr_text_clear` → `text_standard`
- `reason_code` 枚举：`["extraction_mistake", "ocr_quality_issue", "none"]` → `["extraction_mistake", "nonstandard_expression", "none"]`

### 3.2 `verifier.py` — 语义验证与解析

- `_ALLOWED_REASONS`：加入 `nonstandard_expression`；`ocr_quality_issue` 保留为**历史兼容输入值**（解析旧数据），新生成拒绝
- 语义契约：`nonstandard_expression` ↔ `text_standard=false`（替代 ocr_quality_issue ↔ ocr_text_clear=false）
- checks 键名解析：接受新旧两套键名（`text_standard` 优先，`ocr_text_clear` 兼容），输出归一为 `text_standard`

### 3.3 `prompts.py` — system 文本（verifier.v2 → v3）

- 【固定审核顺序】第 3 步："OCR quality" → "表述规范性"：只检查证据中可定位的**非标准表述**（错读、病句、残缺、标签/单位问题）；**不归因于 OCR、不要求给出修正词**；"术语陌生"（规范用词但少见）不构成问题
- 【判定与原因】："可定位且影响理解的确切 OCR 病句 → ocr_quality_issue" → "可定位的非标准表述 → nonstandard_expression"；新增："术语陌生 = 规范医学/日常用词；非任何标准用词或形近/音近标准词 → 非标准表述，标注时不需要给出正确词"
- 【固定审核顺序】第 1 步 grounding：拆句边界"按句号、分号或换行"→"按句号、分号、换行；value 超过 40 字时按逗号、顿号补充拆分；含'否认/无/未见'的片段不拆"
- 【示例】微例 3 措辞更新（古手 → 非标准表述，不归因）；微例 4 改为对照两条（规范少见用词 → pass；错读形似规范词 → suspicious）

### 3.4 调用侧 — 字段级分组

- `verifier.verify(..., group_by="field")`（评估 runner 与生产注入点同步）；串行；证据区 = cited ± 1 邻接（不变）
- 分组失败隔离语义不变（missing_ids 分组跳过）

## 4. 验收标准（冻结预期，测后逐项对照）

**V1-V4 判定范围：case_001~006 全量冒烟**（重点核查 case_006 上轮 5 条漏检 + 3 条误报的对应字段）。

| # | 预期 | 判定 |
|---|---|---|
| V1 | case_006 pe_chest 至少一项可疑（「胸状胸」错读 或 乳房内容越界） | 全量冒烟逐字段 |
| V2 | case_006 pe_neurological_exam 越界（一般情况混入）标 suspicious | 同上 |
| V3 | case_006 pmh_surgery_history「古手」标 suspicious（nonstandard_expression） | 同上 |
| V4 | 6 例正常短字段（pe_temperature/pe_ears/pe_pulse 等）不新增误报；case_006 上轮 3 条 FP（人名医院/仍未白色粘痰/否认与主诉并存）不回归为必标 | 同上 |
| V5 | 语义契约 0 违规（reason_code ↔ check 对应、comment 引用、field_key 唯一），6 例全量 | 全量冒烟 |
| V6 | 单例复核耗时 ≤ 90s（字段级串行基线 66s），6 例总耗时记录 | 计时记录 |
| V7 | 历史数据（含 `ocr_quality_issue` / `ocr_text_clear`）解析兼容 | 单测 |
| V8 | 6 例 kappa 相对单例口径记录变化方向（不设达标线） | kappa 重算 |

kappa 仍为 provisional 口径（AI 模拟裁定，6 例样本），本步**不作上岗结论**，仅记录变化方向。

## 5. 测试设计（先于实现）

- `test_copd_verifier.py`：新增 reason_code/check 改名后的语义验证用例；历史键名解析兼容；非标准表述 ↔ text_standard=false 对应；术语陌生 → pass 不误报
- `test_copd_prompts.py`：system 含判别细则与对照微例；拆句边界文字；微例 JSON 可解析
- `test_evaluation_runner.py`（如涉调用侧）：group_by="field" 参数生效、串行
- 冒烟复测脚本：case_001~006 抽取（extractor.v4）+ 61 字段全量复核，对照 V1-V8；产物冻结 `data/evaluation/reports/20260804-verifier-v3-case*-candidates.json` / `-smoke.json`

## 6. 实验数据附录（2026-08-04）

见 `data/evaluation/reports/20260804-verifier-parallel-vs-serial-timing.json`；原始冒烟基线 `20260803-verifier-opt-v1-case006-smoke.json`。
