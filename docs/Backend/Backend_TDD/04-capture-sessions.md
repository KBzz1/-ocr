# 后端 TDD — 采集会话管理

> PRD: PR-BE-002
> 会话状态见 `docs/Shared/state-enums.md`

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SES-001 | 单元 | 创建会话生成唯一 `session_id` | ID 为空或重复 |
| BE-SES-002 | 单元 | 创建会话记录 `created_at`、`expires_at`、`status: active` | 字段缺失 |
| BE-SES-003 | API | `POST /api/capture-sessions` 返回 201、会话信息和二维码 URL | 路由或响应结构缺失 |
| BE-SES-004 | API | `GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间 | 查询接口缺失 |
| BE-SES-005 | 单元 | 过期会话被判定为 `expired` | 过期判断缺失 |
| BE-SES-006 | API | 过期会话上传返回 409 和 `SESSION_EXPIRED` | 仍允许上传 |
| BE-SES-007 | API | 完成采集前允许新增、删除、排序、补拍页面 | 编辑接口未实现 |
| BE-SES-008 | API | `POST /api/mobile/{sessionId}/finish` 后会话变为 `locked` | 状态未锁定 |
| BE-SES-009 | API | `locked` 会话禁止新增、删除、排序页面，返回 `SESSION_LOCKED` | 完成后仍可编辑 |
| BE-SES-010 | 集成 | 完成采集后页面顺序固化，后续任务处理使用固化顺序 | 处理顺序仍受临时列表影响 |
| BE-SES-011 | API | 没有已成功上传页面的会话 `finish` 返回 `SESSION_EMPTY`，不创建任务 | 空任务或占位页面任务被创建 |
