# 前端 TDD — 任务列表

> PRD: PR-FE-003
> 任务状态见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-TASK-001 | 组件 | 列表至少显示任务编号、创建时间、页数、处理状态、审核状态、导出状态 |
| FE-TASK-002 | 组件 | 所有任务状态按状态枚举正确展示中文标签 |
| FE-TASK-003 | 组件 | 轮询或推送返回新任务时，列表自动新增记录 |
| FE-TASK-004 | 组件 | 任务从 `uploaded` → `processing` → `ready_for_review` 的状态变化可见 |
| FE-TASK-005 | 组件 | 算法模块未配置、解析失败或 LLM 字段抽取失败时，任务显示 `failed` 和错误原因 |
| FE-TASK-006 | 组件 | `failed` 状态显示错误摘要，可查看完整失败原因 |
| FE-TASK-007 | 组件 | 失败任务显示"重新处理"按钮，点击调用 `POST /api/tasks/{taskId}/retry` |
| FE-TASK-008 | 组件 | 重新处理成功后状态更新为 `processing` |
| FE-TASK-009 | 组件 | 筛选"待审核/失败"只展示对应任务 |
