# 前端 TDD — 字段状态与确认校验

> PRD: PR-FE-006
> 字段状态定义见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-STS-001 | 组件 | 所有字段状态按状态枚举正确展示中文标签：unreviewed 未审核、confirmed 已确认、modified 已修改、suspicious 存疑、empty 为空、confirmed_empty 空值已确认 |
| FE-STS-002 | 组件 | 未审核、存疑、为空、已确认、空值已确认字段数量在统计栏正确展示 |
| FE-STS-003 | 组件 | 只有 `confirmed`、`modified`、`confirmed_empty` 字段时，确认审核不触发预警弹窗 |
| FE-STS-004 | 组件 | 存在 `unreviewed` 字段时，确认审核弹出预警窗显示未审核数量，提供"继续确认"和"取消" |
| FE-STS-005 | 组件 | 存在 `suspicious` 字段时，确认审核弹出预警窗显示存疑数量，提供"继续确认"和"取消" |
| FE-STS-006 | 组件 | `empty` 字段可显式确认为"空值可接受"，状态变为 `confirmed_empty`；`confirmed_empty` 不触发预警 |
| FE-STS-007 | 组件 | 用户选择"继续确认"后调用 `POST /api/tasks/{taskId}/review/confirm` |
| FE-STS-008 | 组件 | confirm API 返回校验失败时，展示后端返回的字段问题列表 |
| FE-STS-009 | 组件 | 取消预警弹窗后不调用 confirm API，审核页保持可编辑状态 |
| FE-STS-010 | 组件 | 批量确认后统计栏实时更新各状态字段数量 |
