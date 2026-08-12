# extractor.v3 — 版本分析

- **版本号**: `extractor.v3`（旧命名沿用 `admission_record_structured_fields_prompt.v1` 常量）
- **锚点**: commit `97627fb`（blob sha256 前16: `80fbb28245332302`）

## 变更摘要

精简重构为 6 段骨架（任务边界/状态判定/取值策略/字段目录/示例），删除【再次强调】与 OCR 风险段；
长文本字段拆句核验（`_split_sentences`，句末标点+逗号续拆）。

## 依据

- 版本注册表 §3（v3 终态 `6f9bf90` 另 +13 条 pe_* 字段边界 description，并入 v4 前的过渡形态）

## 指标对比与结论

为 v3 主状态（非终态），终态描述见 extractor.v4。本目录报告（来自 `evaluation/data/reports/` 运行产物归档）：

- `report.html` — 抽取与复核上下文工程重构·实施与评估报告（2026-08-03，v3 时代 6 例全量评估）
- `20260802-prompt-refactor-field-boundary-ablation-report.html` — 提示词瘦身+字段边界四步消融报告（v3 终态前身，字段边界演进）
- `20260803-case005-high-model-reproduction-pack.html` — case_005 高模型等价复现包（当前 v3 实际抽取请求原样复现）
- `20260803-case005-high-model-vs-4b-analysis.html` — case_005 高模型与 4B 同提示词对比（4B 能力/注意力为主要失败变量）
