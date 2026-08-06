# extractor.v3 — 版本分析

- **版本号**: `extractor.v3`（旧命名沿用 `admission_record_structured_fields_prompt.v1` 常量）
- **锚点**: commit `97627fb`（blob sha256 前16: `80fbb28245332302`）

## 变更摘要

精简重构为 6 段骨架（任务边界/状态判定/取值策略/字段目录/示例），删除【再次强调】与 OCR 风险段；
长文本字段拆句核验（`_split_sentences`，句末标点+逗号续拆）。

## 依据

- 版本注册表 §3（v3 终态 `6f9bf90` 另 +13 条 pe_* 字段边界 description，并入 v4 前的过渡形态）

## 指标对比与结论

无独立评估报告；为 v3 主状态（非终态），终态描述见 extractor.v4。
