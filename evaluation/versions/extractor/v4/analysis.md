# extractor.v4 — 版本分析

- **版本号**: `extractor.v4`（首个显式版本常量；旧命名 `admission_record_structured_fields_prompt.v4`）
- **锚点**: 当前 HEAD（blob sha256 前16: `7f9ca9aece4be109`；注册表 §3 记录 `d121b834ff85688f` 为命名规范化时未提交工作区快照；PPEMA-V1 终态 `01250ed89387ba30`）

## 变更摘要

61 字段 T/J/D 策略标记（取值策略真源迁至 `field_policies.py`）+ 字段边界 description
（"仅："渲染）+ 3 个 JSON 局部微例（共享否定作用域/J 型异常优先/禁止推导 BMI，虚拟 ID u901-u903）。
字段目录行格式统一为 `field_key｜中文名｜P 标记｜特有边界`。

## 依据

- 版本注册表 §3（v4 两行：PPEMA-V1 终态 + 命名规范化后）
- PPEMA-V1 设计：`docs/codex_design/prompt-policy-metric-alignment-v1/DESIGN.md`

## 指标对比与结论

本目录报告（来自 `evaluation/data/reports/` 运行产物归档）：

- `report.html` — PPEMA-V1 主报告（2026-08-03，四项改造：约束解码保留/字段策略/指标对齐/评估结论），详见 `docs/codex_design/prompt-policy-metric-alignment-v1/WORKER_REPORT.md`
- `20260803-prompt-v4-appendix.html` — PPEMA-V1 prompt v4 完整附录（system/user/JSON Schema 全文）
- `20260803-prompt-refactor-v3-full-prompts.html` — 当前 v4 抽取+复核完整提示词（`build_verification_messages` 实际渲染）

本目录 prompt-full.md 为当前线上形态。
