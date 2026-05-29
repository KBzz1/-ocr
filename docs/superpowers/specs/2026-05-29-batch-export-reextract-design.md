# 批量导出与 OCR 文本重抽取设计

## 背景

当前系统已经支持单任务 JSON/Excel 导出，以及基于本地 OCR 文档解析结果执行慢阻肺专病字段抽取。后续需要先搭建两个入口框架：

- 批量导出先采用 zip，暂不做汇总 Excel。
- 重抽取只复用已识别 OCR 文本，不重新跑 OCR，不重新处理图片。

## 范围

### 批量导出

- 新增后端批量导出 API，接收 `task_ids`。
- 只允许 `review` 和 `done` 任务进入批量导出。
- zip 中每个任务复用现有单任务 JSON 导出文件；Excel 暂不纳入批量 zip，避免当前 Excel 列/字段问题扩大。
- 单个任务校验失败时，整个批量导出返回现有导出校验错误，不生成部分成功 zip。

### OCR 文本重抽取

- 新增后端 API：对已有任务执行 `ocr_text_only` 重抽取。
- 任务必须已有可用 OCR 文本，优先读取 `results/{task_id}/document_result.json`，缺失时可从持久化审核结果中的 OCR 字段兜底。
- 重抽取复用现有字段抽取端口和 schema 校验，不调用图片处理或 OCR/文档解析端口。
- 新候选结果写入 `results/{task_id}/field_candidates.json`，并写入 `results/{task_id}/reextract_runs/{run_id}.json` 审计记录。
- 旧人工审核结果不被静默覆盖；若已有 `review_result.json`，重抽取只记录候选和元数据，任务回到 `review`。

### 版本元数据

- schema 版本来自当前 schema 的 `version`。
- prompt 版本由 COPD prompt 模块显式暴露常量。
- 每次重抽取保存 `schema_version`、`prompt_version`、`source`、`run_id`、`created_at`。

## 非目标

- 不修复当前单任务 Excel 字段问题。
- 不做批量汇总 Excel。
- 不做前端完整多选交互。
- 不允许前端从 OCR 文本或 schema 推断字段。
- 不扩展成通用医学规则引擎。

## 错误处理

- 批量导出沿用 `EXPORT_VALIDATION_FAILED` 和 `EXPORT_FAILED`。
- 重抽取状态不允许或缺少 OCR 文本时返回 `REEXTRACTION_VALIDATION_FAILED`。
- 字段抽取端口未配置、候选为空、候选契约非法时返回相同错误码；本入口不把任务推进到 `failed`，避免覆盖原任务状态。

