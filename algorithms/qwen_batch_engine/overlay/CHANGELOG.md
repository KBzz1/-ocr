# Qwen Batch Engine Overlay Changelog

## 2026-06-26

- 同步上游 `aufgh/qwen` commit `a746ba9d061d2af8878485f1f837e4d10e2bd755`。
- 新增工作站适配目标：job manifest、标准 `result.json`、`anchors.json` offset 回填、离线配置约束。
- 未改变上游字段含义、T/J 语义、核心 prompt 流程或并发算法。
- 当前回归：contract tests only；真实模型 smoke 由本地离线环境执行后补写 `snapshots/2026-06-26-a746ba9/smoke_result.md`。
