# 前端 TDD — 导出功能

> PRD: PR-FE-007
> 前端只验证下载触发、文件名、Content-Type 和错误提示；Excel/JSON 内容结构由后端测试负责。

| ID | 类型 | 用例 |
|----|------|------|
| FE-EXP-001 | 组件 | 已确认任务显示 Excel 和 JSON 导出按钮 |
| FE-EXP-002 | 组件 | 未确认任务导出按钮禁用，tooltip 显示"请先确认审核" |
| FE-EXP-003 | 组件 | 直接调用导出 API 且后端返回完整性错误时，前端展示错误并不触发下载 |
| FE-EXP-004 | 组件 | 点击"导出 Excel"调用 `GET /api/tasks/{taskId}/export/excel` 并触发下载 |
| FE-EXP-005 | 组件 | 点击"导出 JSON"调用 `GET /api/tasks/{taskId}/export/json` 并触发下载 |
| FE-EXP-006 | 组件 | 导出前展示未审核、存疑、为空、未定位来源字段数量 |
| FE-EXP-007 | 组件 | 导出失败时显示"导出失败：{原因}"，审核数据不受影响 |
| FE-EXP-008 | 组件 | 导出成功后任务显示最近导出时间和格式 |
