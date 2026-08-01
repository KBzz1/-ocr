# Qwen Batch Engine Overlay Changelog

## 2026-08-01

- 强化 T 字段数值语义：运行时只读 `upstream/config.yaml` 的 `extraction.system_prompt`（`overlay/prompts/extraction_system_prompt.txt` 为同步记录），两处同步明确体温/脉搏/心率/呼吸/血压/身高/体重/BMI/血气/血常规等数值参数类 T 字段必须输出 `{"v": 数值}`，禁止输出 `{"s":...}` 判定格式；原文行含"正常"字样但存在数值时也必须截取数值。
- `run_job.py` 归一化防御：T 参数类字段即使收到带 `s`/`状态` 键的判定格式节点，也只取 `v`/`值` 的数值，不再把判定格式的"正常"当作字段值；LLM 定位了证据但未输出数值时字段置空并标 `attention_required` 交由审核页核验。
- 背景：批量抽取中生命体征行（如 `T36.5℃脉搏99次/分…正常，`）因行尾"正常"被 LLM 整体判为 s=0，体温等 6 个数值字段导出为"正常"。

## 2026-06-26

- 同步上游 `aufgh/qwen` commit `a746ba9d061d2af8878485f1f837e4d10e2bd755`。
- 新增工作站适配目标：job manifest、标准 `result.json`、`anchors.json` offset 回填、离线配置约束。
- 未改变上游字段含义、T/J 语义、核心 prompt 流程或并发算法。
- 当前回归：contract tests only；真实模型 smoke 由本地离线环境执行后补写 `snapshots/2026-06-26-a746ba9/smoke_result.md`。
