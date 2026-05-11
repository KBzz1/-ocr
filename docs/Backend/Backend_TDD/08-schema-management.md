# 后端 TDD — 字段 Schema 管理

> PRD: PR-BE-007

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SCH-001 | 单元 | schema 文件必须包含 `version`、`document_type`、字段组和字段 key | 缺字段仍通过 |
| BE-SCH-002 | 单元 | 重复 `field_key` 被拒绝 | 重复 key 被接受 |
| BE-SCH-003 | 单元 | 字段组顺序稳定，导出和前端展示使用同一顺序 | 顺序不稳定 |
| BE-SCH-004 | 集成 | 修改 schema 后，新任务读取新 schema，历史任务保留旧 `schema_version` | 历史任务被新 schema 影响 |
| BE-SCH-005 | API | `GET /api/schema/current` 返回当前 schema，前端可动态展示字段 | schema 接口缺失 |
| BE-SCH-006 | 集成 | schema 只用于校验外部字段候选、前端展示和导出顺序；不得在算法失败时生成替代字段 | schema 被用于兜底抽取 |
| BE-SCH-007 | 单元 | 不同 `document_type` 可选择不同 schema；第一版默认通用 schema | 文书类型选择失败 |
