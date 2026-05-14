# 后端 TDD — API 契约与错误响应

> 统一错误响应结构见 `docs/Shared/error-codes.md`

统一错误响应：

```json
{
  "error": {
    "code": "SESSION_EXPIRED",
    "message": "采集会话已过期",
    "details": {}
  }
}
```

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-API-001 | API | 所有成功响应包含稳定 JSON 结构或明确下载响应头 | 响应结构漂移 |
| BE-API-002 | API | 所有失败响应使用统一 `error.code/message/details` | 错误格式不统一 |
| BE-API-003 | API | 404 任务、会话、页面均返回对应错误码，不返回堆栈 | 泄露堆栈 |
| BE-API-004 | API | 上传接口缺少文件返回 400 和明确错误 | 500 崩溃 |
| BE-API-005 | API | 重复 finish 同一会话幂等返回 locked 状态，不重复创建任务 | 重复任务 |
| BE-API-006 | API | 重复上传同一 page_id 按幂等策略处理，不产生重复页序 | 页序重复 |
| BE-API-007 | API | 删除不存在页面返回 404，不影响其他页面 | 错误删除 |
| BE-API-008 | API | 排序请求含未知 page_id 时整体拒绝，不局部应用 | 顺序被破坏 |
| BE-API-009 | API | `PUT /api/mobile/{sessionId}/pages/{pageId}/quad` 成功时返回稳定页面结构，包含 page_id、page_no、quad_points、updated_at | 响应缺字段或结构漂移 |
| BE-API-010 | API | `PUT /api/mobile/{sessionId}/pages/{pageId}/quad` 中 session/page 不存在、会话锁定、坐标非法时分别返回统一错误结构 | 错误码混乱或泄露堆栈 |
