# 后端 TDD — API 契约与错误响应

> 统一错误响应结构见 `docs/Shared/error-codes.md`

统一错误响应：

```json
{
  "error": {
    "code": "TASK_UPLOAD_CLOSED",
    "message": "任务已结束上传，不能继续上传图片",
    "details": {}
  }
}
```

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-API-001 | API | 所有成功响应包含稳定 JSON 结构或明确下载响应头 | 响应结构漂移 |
| BE-API-002 | API | 所有失败响应使用统一 `error.code/message/details` | 错误格式不统一 |
| BE-API-003 | API | 404 任务、图片或导出文件均返回对应错误码，不返回堆栈 | 泄露堆栈 |
| BE-API-004 | API | 上传接口缺少文件返回 400 和明确错误 | 500 崩溃 |
| BE-API-005 | API | 创建任务返回 `task_id`、`upload_url`、`upload_token` 和初始 `uploading` 状态 | 新建任务缺少手机上传入口 |
| BE-API-006 | API | 手机上传接口校验 `task_id`、上传令牌和任务状态 | 任意任务或无令牌可上传 |
| BE-API-007 | API | 完成上传无图片返回 `TASK_EMPTY`，有图片进入 `processing` | 空任务被处理或状态未推进 |
| BE-API-008 | API | 任务详情返回图片列表、OCR 文本、结构化字段、错误信息和导出信息的稳定结构 | 前端契约漂移 |
| BE-API-009 | API | `review` 和 `done` 任务可导出 JSON/Excel，其他状态返回 `EXPORT_VALIDATION_FAILED` | 非法状态可导出 |
| BE-API-010 | API | 批量 JSON zip 只接受 `review` / `done` 任务，失败响应包含统一错误结构 | 批量导出混入不可导出任务 |
| BE-API-011 | API | 重抽取接口缺少 OCR 文本或候选契约非法时返回 `REEXTRACTION_VALIDATION_FAILED` | 重抽取静默失败或覆盖人工值 |

当前 MVP 不设计 `/api/capture-sessions*`、`/api/mobile/{session_id}/*`、更新 `quad_points`、页面排序或修订采集 API 契约。
