# evaluation/data/

评估体系的运行数据目录（不进 git）：

- `golden/`：字段级金标样本 `case_001.json` ~ `case_006.json`，格式见
  `docs/superpowers/specs/2026-08-01-evaluation-harness-design.md` 第 3 节。
- `reports/`：评估报告 `<日期>_<prompt版本>_<模型>.json`，首次跑通后另存
  `baseline_<prompt版本>.json` 作为回归基线。

- 本目录为评估本地数据（gitignored，不提交）：`golden/` 评估金标由 `text_data/ground_truth/` 提炼；`calibration/` kappa 校准与裁定数据；`reports/` 评估报告；`text_data/` 人工标注原始素材（ground_truth/ ocr_results/ output/）。
- 08-01/02 历史数据（adjudications/verdicts 旧系列）随合并留存于 calibration/reports 原位，不迁移不删除。
