# 前端 TDD — 任务列表

> PRD: PR-FE-003
> 任务状态见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-TASK-001 | 组件 | 列表至少显示任务编号、首页缩略图、创建时间、页数、处理状态、审核状态、导出状态 |
| FE-TASK-002 | 组件 | 所有任务状态按状态枚举正确展示中文标签：`capturing` 采集中、`uploaded` 上传完成、`processing` 处理中、`ready_for_review` 待审核、`confirmed` 已确认、`exported` 已导出、`failed` 失败 |
| FE-TASK-003 | 组件 | 轮询或推送返回新任务时，列表自动新增记录；新建采集后立即出现 `capturing` 任务 |
| FE-TASK-004 | 组件 | 任务从 `capturing` → `uploaded` → `processing` → `ready_for_review` 的状态变化可见 |
| FE-TASK-005 | 组件 | 算法模块未配置、解析失败或 LLM 字段抽取失败时，任务显示 `failed` 和错误原因 |
| FE-TASK-006 | 组件 | `failed` 状态显示错误摘要，可查看完整失败原因 |
| FE-TASK-007 | 组件 | 失败任务显示"重新处理"按钮，点击调用 `POST /api/tasks/{taskId}/retry` |
| FE-TASK-008 | 组件 | 重新处理成功后状态更新为 `processing` |
| FE-TASK-009 | 组件 | 筛选"待审核/失败/采集中"只展示对应任务 |
| FE-TASK-010 | 组件 | `ready_for_review` 任务显示"重新处理"按钮，点击调用 `POST /api/tasks/{taskId}/reprocess` 后状态回到 `processing` |
| FE-TASK-011 | 组件 | 非 `processing` 的 locked 任务显示"修订采集"按钮，确认后任务回到 `capturing`；`processing` 状态时"修订采集"禁用 |
| FE-TASK-012 | 组件 | `capturing` 状态任务显示"查看二维码"和"取消采集"操作 |
| FE-TASK-013 | 组件 | 任务列表每项在任务编号旁展示首页缩略图（基于第一页原图）；`capturing` 无页面时显示占位图 |
