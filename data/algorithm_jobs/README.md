# data/algorithm_jobs

Qwen 批处理引擎的运行时 job 目录占位。

每次运行 `python algorithms/qwen_batch_engine/adapter/run_job.py --job-dir data/algorithm_jobs/{task_id}` 时，
引擎会在此目录生成任务包（`manifest.json`、`anchors.json`、`config.yaml`、`result.json`、上游与预处理中间产物）。

`result.json` 中包含 OCR 原文与抽取字段结果，属于真实运行数据，**不得提交**。
