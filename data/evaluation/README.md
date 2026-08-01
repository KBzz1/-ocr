# data/evaluation/

评估体系的运行数据目录（不进 git）：

- `golden/`：字段级金标样本 `case_001.json` ~ `case_006.json`，格式见
  `docs/superpowers/specs/2026-08-01-evaluation-harness-design.md` 第 3 节。
- `reports/`：评估报告 `<日期>_<prompt版本>_<模型>.json`，首次跑通后另存
  `baseline_<prompt版本>.json` 作为回归基线。
