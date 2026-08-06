# evaluation/ — 观测与评估体系

评估代码、测试与本地数据（金标/校准/报告/人工标注素材）的收拢目录。
**评估代码单向依赖 `app.backend` 生产模块**（绝对导入），不参与生产路径。

## 目录

- `code/` — Python 包 `evaluation.code`：指标 `metrics`、管线与报告 `runner`、CLI `run_eval`、校准 `calibrate`、分块复核 `chunked_review`、审核回流 `feedback`/`desensitize`
- `tests/` — 评估单测（含 `test_review_feedback.py`）
- `data/` — gitignored：`golden/`（评估金标，由 `text_data/ground_truth` 提炼）、`calibration/`（kappa 校准与裁定数据）、`reports/`（评估报告）、`text_data/`（人工标注原始素材：ground_truth/ ocr_results/ output/）
- `versions/` — 版本迭代归档（规范见下）

## 运行与测试

```bash
# 评估 CLI（仓库根）
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help
# 评估测试
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

## 文档统一索引（正文在 docs/ 原位，不迁移）

- 评估/复核/提示词实验设计：`docs/superpowers/specs/2026-08-0{1,2,3}-*.md`（evaluation-harness、verifier-normalization、verifier-chunked-review-experiment、verifier-recall-optimization、prompt-refactor-field-boundary、verifier-step7-scale-evidence）
- 实施计划：`docs/superpowers/plans/2026-08-0{1,2}-*.md` 对应 5 份
- 架构师实验记录：`docs/codex_design/`（prompt-policy-metric-alignment-v1、verifier-optimization-v1、verifier-judge-rubric-v1）
- 报告 HTML：`versions/<组件>/<版本号>/report.html`（本版本报告，如 `versions/verifier/v1/report.html`；前身抽取文档 `versions/verifier/v1/verifier-normalization.html`、`versions/evaluator/v1/report.html`；架构全景图 `docs/可视化html/architecture_overview.html`）
- 历史文档内旧路径映射：`app/backend/evaluation` → `evaluation.code`（命令 `python -m evaluation.code.run_eval`）；`data/evaluation`、`data/text_data` → `evaluation/data`

## 版本迭代规范（自下一次版本迭代起生效，不回溯补做历史版本）

每次提示词/评估口径版本迭代在 `versions/<组件>/<版本号>/` 建目录（组件为 `extractor` / `verifier` / `evaluator` 之一，版本号沿用 `ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION` / `VERIFIER_PROMPT_VERSION` / `METRIC_VERSION`，如 `versions/extractor/v4/`）：
- `analysis.md` — 改动点、依据、指标前后对比、结论
- `prompt-full.md` — 运行时完整渲染的 system+user 提示词全文（`build_admission_structured_fields_messages` 实际产出，不截断不摘要；评估器无 prompt 时放指标源码快照并注明）
- `report.html` — 本版本评估报告（若有）
- `versions/README.md` 索引表追加一行（版本号 | 日期 | 变更摘要 | 分析文档 | 全量提示词 | 报告）
