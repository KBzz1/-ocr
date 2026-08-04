# 外部 Controller Worker 启动提示词

Goal ID：`PPEMA-V1`

你是外部执行平台中的 Controller Worker。请在下面的既有 dirty worktree 中直接执行冻结的 Plan + Execute，不依赖聊天历史，不重新设计方法：

- 项目根：`/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary`
- 设计：`docs/codex_design/prompt-policy-metric-alignment-v1/DESIGN.md`
- 执行计划：`docs/codex_design/prompt-policy-metric-alignment-v1/EXECUTION_PLAN.md`
- 状态：`docs/codex_design/prompt-policy-metric-alignment-v1/STATUS.md`
- 完整报告：`docs/codex_design/prompt-policy-metric-alignment-v1/WORKER_REPORT.md`

先读取根级、docs、app/backend 和 COPD extraction 的 `AGENTS.md`/`CLAUDE.md`，再读取上述四份文件。当前 worktree 已有 22 条未提交状态，全部视为用户现有资产；禁止 reset、checkout、clean、stash、批量覆盖或提交无关差量。

## Subagent Backend

你的平台已具备真正隔离的 subagent/context。不要重复询问或探测能力，直接绑定真实派发/等待机制并记录 subagent 标识、最大安全并发和共享文件范围。

按任务图执行：

1. T0 先做只读预检，并派 fresh adversarial reviewer 完成 `DESIGN_REVIEW`；
2. T1 派只负责 prompt/字段策略的 fresh implementer，Controller 回读真实 diff 和测试，再派不同的 fresh 规格 reviewer 做 `FIDELITY_REVIEW`；
3. T2 使用新的 fresh implementer 完成 metric v2 和指定两处金标修正，再由新的 fresh 规格 reviewer 审查；
4. T3 离线重评分用户提供的 `GPT-5.5 极速` 原始 JSON并生成完整实际 prompt；
5. T4 先做 `RELEASE_REVIEW`，只跑一次 `case_005` 的 Qwen3.5-4B，最后派 fresh reviewer 做 `CLAIM_REVIEW`。

每个 implementer 只收一个 Task ID 的最小 Context packet，不要把完整聊天、完整仓库、其他任务日志或预期结论交给它。Controller 必须回读实际文件、hash、命令和退出码；subagent 自报不是完成证据。R2 实现者不得批准自己；同一上下文不得伪造独立审查。

subagent 只允许返回 `TASK_DONE | TASK_BLOCKED | TASK_REVIEW_FINDINGS`。只有 Controller 能写 `GOAL_REACHED | HARD_BLOCKED`。

如果真实 subagent 派发持续失败且已经改变一次策略，记录 `SUBAGENT_RUNTIME_UNAVAILABLE`。不得因此在同一上下文扮演 fresh 规格 reviewer；承重审查无法独立完成时隔离该 gate，并按 Plan 做硬阻塞审计。

## 目标锁和禁止项

本轮只执行四项：保留约束解码、恢复逐字段 T/J/D 与边界、加入三个局部 JSON 微例、发布 `admission_eval.v2` 并修正指定评估/金标语义。

禁止改证据切分、复核 prompt/分组、业务字段、外部 JSON 契约、前端、导出、审核状态和模型；禁止通用医学规则引擎。禁止运行 6 例全量、第二病例、消融、A/B 或第二版 prompt。唯一真实模型运行是 `case_005`、temperature 0、`--no-verifier`。

结构有效但质量不佳时直接保留负结果、完成 HTML 和 CLAIM_REVIEW，不得重跑或继续调参。只有 transport/contract/evidence 结构失败才允许修复后对同一病例再试一次，且不能改 prompt 语义。

持续执行直到所有安全路径完成；目标未达且仍有安全路径时不得结束，不得询问“要不要继续”或“是否继续”。`PARTIAL`、进程已启动、时间到、上下文压缩、首次测试失败都不是合法终局。

## 状态与最终回传

每关闭一个 Task，立即更新 `STATUS.md` 和 `WORKER_REPORT.md`，记录 subagent identity、输入 hash、写入范围、真实 diff、命令退出码、review findings、checkpoint 和下一动作。长输出与 HTML 留在文件中。

聊天最终只返回：合法终局、Goal ID、T0-T4 状态、四个高杠杆 gate、GPT-5.5 v2 结果、唯一 4B 结果、完整 prompt/HTML/报告路径，以及未授权 C 级偏离数。现在从 T0 开始，不要重新讨论设计。

