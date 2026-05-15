# 后端 TDD — 采集会话管理

> PRD: PR-BE-002
> 会话状态见 `docs/Shared/state-enums.md`

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-SES-001 | 单元 | 创建会话生成唯一 `session_id` | ID 为空或重复 |
| BE-SES-002 | 单元 | 创建会话记录 `created_at`、默认 30 分钟后的 `expires_at`、`status: active` | 字段缺失或默认有效期错误 |
| BE-SES-003 | API | `POST /api/capture-sessions` 返回 201、会话信息、关联 `task_id` 和二维码 URL | 路由或响应结构缺失 |
| BE-SES-004 | API | `GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间 | 查询接口缺失 |
| BE-SES-005 | 单元 | 过期会话被判定为 `expired` | 过期判断缺失 |
| BE-SES-006 | API | 过期会话上传返回 409 和 `SESSION_EXPIRED` | 仍允许上传 |
| BE-SES-007 | API | 完成采集前允许新增、删除、排序、补拍页面和重新框选已上传页面 | 编辑接口未实现 |
| BE-SES-008 | API | `POST /api/mobile/{sessionId}/finish` 后会话变为 `locked` | 状态未锁定 |
| BE-SES-009 | API | `locked` 会话禁止新增、删除、排序、补拍、重新框选页面，返回 `SESSION_LOCKED` | 完成后仍可编辑 |
| BE-SES-010 | 集成 | 完成采集后页面顺序和框选元数据固化，后续任务处理使用固化数据 | 处理顺序或框选数据仍受临时列表影响 |
| BE-SES-011 | API | 没有已成功上传页面的会话 `finish` 返回 `SESSION_EMPTY`，关联任务保持 `capturing` | 空任务被错误推进到 uploaded |
| BE-SES-012 | 集成 | 创建会话时同步创建关联任务，任务状态为 `capturing` | 任务仍等到 finish 才创建 |
| BE-SES-013 | API | 电脑端可修改 active 会话过期时间，手机端查询返回新的剩余时间 | 有效期无法调整 |
| BE-SES-014 | API | active 会话取消后状态变为 `cancelled`，关联任务变为 `failed` 且原因是用户取消采集 | 取消无状态或任务仍可继续 |
| BE-SES-015 | API | cancelled 会话所有写操作返回 `SESSION_CANCELLED` | 取消后仍可上传或 finish |
| BE-SES-016 | API | 非 `processing` 关联任务允许修订采集：locked → active，任务回到 `capturing`，session_id/task_id 不变 | 解锁丢失原会话或任务 |
| BE-SES-017 | API | `processing` 关联任务拒绝修订采集，返回 `SESSION_UNLOCK_NOT_ALLOWED` | 处理中输入被同时修改 |
