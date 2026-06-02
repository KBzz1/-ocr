# 前端 TDD — 导出功能

> PRD: PR-FE-005
> 前端只验证下载触发、文件名、Content-Type、批量 zip 入口和错误提示；Excel/JSON 内容结构由后端测试负责。

| ID | 类型 | 用例 |
|----|------|------|
| FE-EXP-001 | 组件 | `review` 和 `done` 任务显示 Excel 和 JSON 导出按钮 |
| FE-EXP-002 | 组件 | 点击"导出 Excel"调用 `GET /api/tasks/{taskId}/export/excel` 并触发下载 |
| FE-EXP-003 | 组件 | 点击"导出 JSON"调用 `GET /api/tasks/{taskId}/export/json` 并触发下载 |
| FE-EXP-004 | 组件 | 导出失败时显示"导出失败：{原因}"，审核数据不受影响 |
| FE-EXP-005 | 组件 | 导出成功后可显示最近导出时间和格式，但任务状态不变为独立 exported |
| FE-EXP-006 | 组件 | 任务管理页选择多个 `review` / `done` 任务后可调用 `POST /api/tasks/export/batch-zip` |
| FE-EXP-007 | 组件 | 批量导出禁用不可导出的任务，并提示失败原因 |
| FE-EXP-008 | 组件 | 当前 MVP 不提供批量 Excel 下载入口 |
