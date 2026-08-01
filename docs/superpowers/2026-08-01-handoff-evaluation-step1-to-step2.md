# Handoff：评估体系第一步 → 第二步（验证器规范化）

> 日期：2026-08-01
> 决策：3 处架构小修正已执行，进入第二步

## 1. 当前状态总览

### 代码（分支 `eval-harness`，未合并 master，worktree 保留于 `.worktrees/eval-harness/`）

| 提交 | 内容 |
|---|---|
| `ca20ee2` | 金标提炼辅助脚本（OCR 差异/章节切分）+ data/evaluation gitignore |
| `37b08db` | 评估指标模块 metrics.py（15 tests） |
| `adc2a01` | 管线组装 runner.py（消融开关/报告生成，7 tests） |
| `614072a` | run_eval CLI（模型替换/基线对比/LLM 失败兜底，2 tests） |
| `8e3563d` | 最终审查修复：EVAL_LLM_FAILURE 样本详情落报告 |
| `2435157` | CLAUDE.md 补 evaluation/ 目录职责索引 |

评估测试 24 个全过；全量 700 passed，5 个既有失败（test_review_routes.py 4 个 + test_qwen_batch_engine_layout.py 1 个）与本次无关。

### master 独立提交（不属分支）

| 提交 | 内容 |
|---|---|
| `71d1d00` | spec：评估体系设计（markdown） |
| `4705227` | spec HTML 可视化版 |
| `8d1367b` | plan：评估体系实施计划 |
| `0089a6c` → `e770c24` | 复盘 HTML（已移至 `docs/可视化html/2026-08-01-evaluation-retrospective.html`） |

### 数据（`data/evaluation/`，不进 git）

- `golden/case_001~006.json`：6 份字段级金标（61 字段 × 6；用户裁定已回写：乙肝否定 found、血糖异常 uncertain、血气按语义 found）
- `reports/baseline_admission_record_structured_fields_prompt.v1.json`：首个基线

### 首个基线（Qwen3.5-4B-AWQ-4bit）

```
status 准确率: 98.09%   value 准确率: 88.32%   幻觉数: 43
契约非法: 0   任务级成功: 0/6   噪声带宽 ±0.2041
```

## 2. 关键决策记录

1. **金标语义**（agent 观测）：金标 = 「从这份 OCR 输入出发，期望抽取输出什么」。OCR 错读是 OCR 层问题，不做 OCR 识别准确率观测；agent 忠实摘录 OCR 阳性表述即正确。文档：spec §3、复盘第一章。
2. **评估先行路线**（A）：不选上下文工程/多 agent——单次调用场景已踩在正确范式上；多 agent 判据（是否引入新信息）不成立。
3. **确定性指标优先**：有金标就比对，不引入 LLM 打分；幻觉 = veto 维度（value 必须在 OCR 原文可定位）。
4. **审核数据回流刻意留到第二步**（金标活资产）。
5. **保留分支**：eval-harness 未合并，第二步继续在分支做，最后统一合入。

## 3. 第二步（验证器规范化）设计输入

### 书籍核心结论（《深入理解 AI Agent》）

- **循环的瓶颈在验证器，不在模型**；Agent 故障是拜占庭式的——从不自报错误，只能靠独立验证发现。
- **三层验证结构**：结果验证器（环境真值，代码优先）→ 过程验证器（规则/权限）→ 质量验证器（Rubric，LLM）。越靠下越依赖代码与真值，只有难形式化的才交 LLM。
- **验证器校准**：LLM 验证器放量前先建 100-200 例人工金标集校准（kappa≥0.7）；评价与诊断分离（不让同一模型既裁判又改规则）。
- **同源模型问题**：抽取与复核同用 Qwen 共享错误盲区——离线无异族模型，缓解方案：复核用不同温度/不同 prompt 风格 + 人工抽检审计。
- **审核数据回流**（ch6 可观测性）：生产轨迹 → 脱敏 → 评估集回归用例，评估集从静态变活资产。项目已具备数据基础：review_service 持久化 `original_value` + 医生修正值。

### 第一步基线暴露的 3 个判定改进方向（ledger 记录，第二步必须处理）

1. **幻觉判定误报**：否定短语重建（prompt 契约要求的规范化输出，如"否认糖尿病病史"）在 OCR 原文中不可定位 → 被误判幻觉（24/43 条为此类）。修正方向：金标 value 本身不可定位时跳过幻觉判定。
2. **J 型字段 value 粒度**：金标"正常" vs 抽取"鼻腔通畅"语义等价被判 mismatch（pe_nose 0/6）。修正方向：J 型字段 value 判定放宽为语义等价。
3. **长文本字段判定过严**：hpi_treatment_medications 等长摘录字段，摘录范围差异导致 value 判定过严（0/6）。修正方向：关键词覆盖或人工裁定。

### 架构预案（模块归属，设计时定）

- 复核器接入 → `copd_extraction/`（质量核验是其既有职责；`prompts.py` 已有 `build_verification_prompt` / `build_adversarial_verification_prompt` 死代码，接入 = 用起来）
- 校准工具（kappa）+ 审核回流 → `evaluation/` 或 `scripts/maintenance/`
- 轨迹日志（第三步）→ 届时再定

## 4. 第二步待办起点（brainstorming）

1. 复核器接入活动路径的形态：抽取 → 复核 → 分歧处理（谁裁决：规则/人工）→ 质量核验；复核器失败语义（复核失败是否任务 failed）
2. 验证器校准方案：用现有 6 份金标起步（样本不足 100-200 例，需定起步口径）+ 审核回流补样本
3. 审核回流管道：review_result.json → 脱敏 → 金标（source: review 标注，与 manual 分开统计）
4. 指标修正（3 个方向）并入本次 scope 或单独任务
5. 消融接口的真正用武之地：复核器接入后"有复核 vs 无复核"对比（run_eval --no-* 已有）
