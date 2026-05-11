# 后端 TDD — 导出服务

> PRD: PR-BE-009

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-EXP-001 | 单元 | 导出前完整性检查返回未审核、存疑、为空、无来源数量 | 统计缺失 |
| BE-EXP-002 | 单元 | JSON 导出结构包含任务编号、导出时间、schema 版本、字段结果和审核状态 | 结构缺字段 |
| BE-EXP-003 | 集成 | JSON 导出字段顺序稳定，与 schema 顺序一致 | 输出顺序不稳定 |
| BE-EXP-004 | 单元 | Excel 数据按字段组组织，字段值来自人工 `final_value` | 使用了自动候选值 |
| BE-EXP-005 | 集成 | 导出文件保存到任务独立 `exports/` 目录 | 文件路径错误 |
| BE-EXP-006 | API | `GET /api/tasks/{taskId}/export/json` 返回下载响应和正确文件名 | 响应头错误 |
| BE-EXP-007 | API | `GET /api/tasks/{taskId}/export/excel` 返回下载响应和正确文件名 | 响应头错误 |
| BE-EXP-008 | API | 未确认任务导出必须返回 `EXPORT_VALIDATION_FAILED`，不允许 warning 后继续导出 | 未确认任务被导出 |
| BE-EXP-009 | 集成 | 导出失败不修改审核结果和任务确认状态 | 失败产生脏状态 |
| BE-EXP-010 | 集成 | 导出成功后记录导出时间、格式和文件路径，任务可变为 `exported` | 导出记录缺失 |
