# 前端 TDD — 字段状态与确认校验

> PRD: PR-FE-006
> 字段状态定义见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-STS-001 | 组件 | 所有字段状态按状态枚举正确展示中文标签 |
| FE-STS-002 | 组件 | 未审核、存疑、为空字段数量在统计栏正确展示 |
| FE-STS-003 | 组件 | 只有 `confirmed` 和 `modified` 字段时，允许确认审核 |
| FE-STS-004 | 组件 | 存在 `unreviewed` 字段时，确认审核被阻断，显示数量且不调用 confirm API |
| FE-STS-005 | 组件 | 存在 `suspicious` 字段时，确认审核被阻断，显示数量且不调用 confirm API |
| FE-STS-006 | 组件 | 存在 `empty` 字段且未被后端确认可接受时，确认审核被阻断 |
| FE-STS-007 | 组件 | 所有阻断项清除后，调用 `POST /api/tasks/{taskId}/review/confirm` |
| FE-STS-008 | 组件 | confirm API 返回校验失败时，展示后端返回的字段问题列表 |
