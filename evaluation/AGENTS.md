# AGENTS.md

## 作用

本目录是观测与评估体系：评估代码、测试与本地数据的收拢位置。评估代码**单向依赖 `app.backend` 生产模块**（绝对导入），不参与生产路径；本目录不新增业务字段、状态、服务或医学规则。

## 目录与运行

- `code/`：Python 包 `evaluation.code`（metrics/runner/run_eval/calibrate/chunked_review/feedback/desensitize）
- `tests/`：评估单测（含 test_review_feedback.py）
- `data/`：gitignored 本地数据（golden/calibration/reports/text_data），不提交患者数据或实验产物
- `versions/`：版本迭代归档（规范见 README.md）

```bash
# CLI（仓库根）
conda run -n manzufei_ocr python -m evaluation.code.run_eval --help
# 测试
conda run -n manzufei_ocr python -m pytest evaluation/tests -q
```

文档（spec/plan/报告）留在 `docs/` 原位，统一索引见 `README.md`。

## 变更约束

- 修改评估行为（指标口径/金标格式/CLI 参数）前先写 spec 并更新文档索引
- 评估代码不得被 `app/backend` 业务代码反向依赖
- 每版本迭代按 `README.md` 版本规范归档（analysis.md + prompt-full.md 全量提示词 + 报告）
