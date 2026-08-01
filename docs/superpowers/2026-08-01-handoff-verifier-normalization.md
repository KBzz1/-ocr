# Handoff：验证器规范化（评估体系第二步）设计完成 → 实施

> 日期：2026-08-01
> 状态：设计已批准、计划已就绪，进入实施
> **执行方式：Subagent-Driven（每个任务派独立 subagent，任务间两阶段评审）**

## 1. 当前状态总览

### 代码（分支 `eval-harness`，未合并 master，worktree 保留于 `.worktrees/eval-harness/`）

| 提交 | 内容 |
|---|---|
| `2435157` | CLAUDE.md 补 evaluation/ 目录职责索引（第一步收尾） |
| `f146a0f` | **spec**：验证器规范化设计（markdown） |
| `6cd867d` | spec 更新：校准裁定改为 Claude 子 agent 模拟人工 |
| `bd9742c` | **plan**：验证器规范化实施计划（8 任务 TDD） |
| `d703f0b` | 设计 HTML 移至主目录管理（避免合入冲突） |

### master 独立提交（不属分支）

| 提交 | 内容 |
|---|---|
| `2c78356` | **设计 HTML**：`docs/可视化html/2026-08-01-verifier-normalization.html`（仿 agent book 排版，主目录管理） |
| `e770c24` | 第一步复盘 HTML（`docs/可视化html/2026-08-01-evaluation-retrospective.html`） |

### 权威文档

- spec：`docs/superpowers/specs/2026-08-01-verifier-normalization-design.md`
- plan：`docs/superpowers/plans/2026-08-01-verifier-normalization-implementation-plan.md`
- 可视化：`docs/可视化html/2026-08-01-verifier-normalization.html`（master 分支）

### 数据（`data/evaluation/`，不进 git）

- `golden/case_001~006.json`：6 份字段级金标（61 字段 × 6，用户已裁定）
- `reports/baseline_admission_record_structured_fields_prompt.v1.json`：首个基线（status 98.09% / value 88.32% / 幻觉 43 / 任务级 0/6）

## 2. 第二步设计定稿（决策记录，勿推翻）

| 决策点 | 结论 |
|---|---|
| 分歧处理 | 复核意见 → quality_flags（`verifier_suspicious`）→ suspicious → 审核页；**不做二次抽取** |
| 复核范围 | 只复核 status=found 且 value 非空 的字段（not_found 由审核页兜底） |
| 同源模型缓解 | 同一 Qwen 模型、温度恒 0.0；靠上下文差异：evidence 前置防锚定（字段在后，防找补）+ 缺陷清单 + 每条可疑 verdict 必须引用 evidence 编号；verdict 型主干 + 对抗精神（先找茬再放行） |
| 复核器失败语义 | 静默降级为空意见，**绝不抛出、绝不导致任务失败、绝不修改字段值** |
| prompt 结构 | 全部拆 system（固定规则，前缀缓存友好）/ user（变量数据）；适配 Qwen ChatML；`complete_json` 支持 system_prompt（向后兼容） |
| 校准 | 真实样本复核输出（约 180 条字段 verdict）→ 裁定 → Cohen's kappa ≥ 0.7 才上岗；**裁定由 Claude 子 agent 模拟人工执行**（大模型裁小模型） |
| thinking | 加 `--thinking` 消融开关，实测 CoT 收益/代价后定默认值（抽取倾向 off、复核倾向 on） |
| 回流 | 审核确认（complete_review）时聚合 `auto_value ≠ final_value` 字段 → 回流文件（运行数据）→ 脱敏 → 金标活资产（source: review 增量文件，单独统计"修正字段错误率"）；回流写失败降级不阻断审核 |
| 指标修正 | ① 金标 value 在 OCR 不可定位 → 跳过该字段幻觉判定（真错误由 value_mismatch 兜底）；② J 型字段（schema qwen_type=J / review_control=judgement）"正常族"归一（正常/通畅/未见异常/阴性/无压痛 → 同一 token）；③ 长文本字段（初始：hpi_* 类 + chief_complaint）核心句重合率 ≥ 0.6 判对 |
| 性能 | vLLM 已开 `--enable-prefix-caching`；system 固定部分全命中；prompt 模板改动=打断缓存，改动走版本化 |

## 3. 实施计划概要（plan 全文为执行依据）

| Task | 内容 | 测试 |
|---|---|---|
| 1 | ChatML 消息结构改造：complete_json system+user、抽取 prompt 拆层 | test_qwen_vllm_client / test_copd_prompts |
| 2 | 复核器 FieldVerifier + 复核 prompt 激活（防锚定布局/few-shot/失败降级/apply_verdicts 映射） | test_copd_verifier |
| 3 | 复核器接入：port 注入 / run_pipeline apply_verify / run_eval --no-verifier | test_evaluation_runner / test_copd_field_port |
| 4 | 指标修正：幻觉豁免 / J 型归一 / 长文本重合率（evaluate_sample 加 schema 参数） | test_evaluation_metrics / test_evaluation_runner |
| 5 | 校准工具 calibrate.py：Cohen's kappa / 裁定模板导出 / CLI（export / kappa） | test_evaluation_calibrate |
| 6 | 审核数据回流：review_service 聚合 / desensitize / feedback（金标活资产）/ run_eval --golden-review | test_review_feedback / test_review_service |
| 7 | thinking 消融开关：complete_json enable_thinking / --thinking | test_qwen_vllm_client |
| 8 | 数据任务（真实 LLM）：修正后基线重跑 / 复核消融对比 / 校准执行（Claude 子 agent 裁定）/ thinking 实测 | 报告对比 |

**Task 依赖顺序：1 → 2 → 3 → 4 → 5 → 6 → 7 → 8**（1 是地基；4 独立可并行，但为减少冲突按序执行；8 最后统一跑真实 LLM）。

## 4. 执行约定

- 环境：`conda run -n manzufei_ocr python -m pytest <path> -v`（worktree 根目录执行）
- Git commit message 中文；每个 Task 完成后单独提交
- 单测注入 fake LLM 客户端，不依赖真实 vLLM 服务；真实推理只发生在 Task 8
- **Subagent-Driven**：每个任务派一个全新 subagent（读 plan 对应 Task + 本 handoff），完成后两阶段评审（子 agent 自我评审 + 独立评审 agent），通过后进入下一任务
- 全量 pytest 既有 5 个失败（test_review_routes 4 + test_qwen_batch_engine_layout 1）与本工作无关，勿修
- `data/`、`exports/`、`logs/` 运行数据不进 git
- 校准裁定（Task 8 Step 3）：开一个 Claude 子 agent 逐条裁定 `should_flag`，写入裁定文件后跑 kappa
- thinking 实测（Task 8 Step 4）结论记录，供复盘与默认值决策

## 5. 收尾定义

- 8 个 Task 完成、评估测试全绿、真实 LLM 四轮运行（基线/消融/校准/thinking）报告齐
- kappa 实测值（达标与否）、thinking 实测结论写入复盘 HTML（参照第一步惯例，放 master 的 `docs/可视化html/`）
- eval-harness 分支统一合入 master
