# 前端 TDD — 任务列表

> PRD: PR-FE-003
> 任务状态见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-TASK-001 | 组件 | 列表至少显示任务编号、创建时间、图片数量、当前状态、错误原因和操作按钮 |
| FE-TASK-002 | 组件 | 所有任务状态按状态枚举正确展示中文标签：`uploading` 上传中、`processing` 处理中、`review` 待审核、`done` 已完成、`failed` 失败 |
| FE-TASK-003 | 组件 | 新建任务后列表自动新增 `uploading` 任务 |
| FE-TASK-004 | 组件 | 任务从 `uploading` → `processing` → `review` → `done` 的状态变化可见 |
| FE-TASK-005 | 组件 | 算法模块未配置、解析失败或 LLM 字段抽取失败时，任务显示 `failed` 和错误原因 |
| FE-TASK-006 | 组件 | `failed` 状态显示错误摘要，可查看完整失败原因 |
| FE-TASK-007 | 组件 | 失败任务显示"重新处理"按钮，点击调用重新处理 API |
| FE-TASK-008 | 组件 | 重新处理成功后状态更新为 `processing` |
| FE-TASK-009 | 组件 | 筛选"上传中/处理中/待审核/已完成/失败"只展示对应任务 |
| FE-TASK-010 | 组件 | `review` 和 `done` 任务显示导出入口 |
| FE-TASK-011 | 组件 | `uploading` 任务显示查看二维码入口 |
| FE-TASK-012 | 组件 | 任务列表不显示修订采集、取消会话、重新框选、拖拽排序或补拍替换入口 |
