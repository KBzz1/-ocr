# 前端 TDD — 字段状态与确认

> PRD: PR-FE-004
> 字段状态定义见 `docs/Shared/state-enums.md`

| ID | 类型 | 用例 |
|----|------|------|
| FE-STS-001 | 组件 | 人工审核字段状态按状态枚举正确展示中文标签：unreviewed 未审核、confirmed 已确认、modified 已修改 |
| FE-STS-002 | 组件 | 字段统计展示未审核、已确认、已修改数量 |
| FE-STS-003 | 组件 | 自动抽取元数据 `extraction_status`、`verification_status`、`quality_flags` 以风险提示展示，不替代人工审核状态 |
| FE-STS-004 | 组件 | 修改字段值后状态变为 `modified` |
| FE-STS-005 | 组件 | 统一审核并完成时，未修改的 `unreviewed` 字段提交为 `confirmed` |
| FE-STS-006 | 组件 | 保存 API 返回校验失败时，展示后端返回的字段问题列表 |
| FE-STS-007 | 组件 | 不渲染 `suspicious`、`empty`、`confirmed_empty` 作为人工审核状态 |
| FE-STS-008 | 组件 | 普通文本字段、判定字段、诊断列表字段和 `not_found`/未提及占位字段均渲染独立确认勾选框 |
| FE-STS-009 | 组件 | 判定字段确认勾选框位于判定分组框内部；普通字段确认勾选框与字段值右侧对齐 |
