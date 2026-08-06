# verifier.v3 — 版本分析

- **版本号**: `verifier.v3`（显式版本常量 `VERIFIER_PROMPT_VERSION`，不渲染进 prompt）
- **锚点**: commit `cc6cb78`（2026-08-04；blob sha256 前16: `7f9ca9aece4be109`）

## 变更摘要

表述规范性契约（只检查证据中确实可定位的非标准表述——错读/病句/残缺/标签或单位问题，
不归因于 OCR、不要求给出修正词）；术语陌生判别（规范用词但少见如"粗测听力"不标；
非标准用词或形近/音近标准词如"胸状胸→桶状胸"必须标）；5 个 JSON 微例（含错读形似
规范词对照，虚拟 ID u911-u913）；逗号级拆句（value>40 字按逗号/顿号补充拆分）；
checks 键 `ocr_text_clear`→`text_standard`、reason `ocr_quality_issue`→`nonstandard_expression`；
字段级分组调用。

## 依据

- 版本注册表 §5（v3 定稿行）
- 设计：`docs/superpowers/specs/2026-08-04-verifier-v3-design.md`

## 指标对比与结论

v3 为当前上线形态（定稿后未再迭代）；kappa 达标验证见上线报告
`verifier/v1/report.html`（原 `docs/可视化html/2026-08-02-verifier-prompt-v3-report.html`）的实验轮次对比
（注：该报告内 v2/v3 为实验轮次命名，非本目录正式版本号）。
