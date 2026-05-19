# MVP 标准错误码

| 错误码 | HTTP 状态码 | 场景 |
|--------|------------|------|
| `REQUEST_NOT_FOUND` | 404 | 请求路径不存在 |
| `INTERNAL_SERVER_ERROR` | 500 | 未预期服务端异常 |
| `INVALID_REQUEST_PARAMS` | 400 | 请求参数缺失、类型错误、格式错误或取值非法 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 非图片文件 |
| `FILE_TOO_LARGE` | 400 | 图片超过限制 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `TASK_UPLOAD_CLOSED` | 409 | 任务不处于 `uploading`，禁止继续上传图片 |
| `TASK_EMPTY` | 400 | 任务没有任何已上传图片，不能完成上传或进入处理 |
| `INVALID_TASK_TRANSITION` | 400 | 非法任务状态流转 |
| `ALGORITHM_MODULE_NOT_CONFIGURED` | — | OCR/结构化模块未配置（任务进入 `failed`） |
| `ALGORITHM_MODULE_FAILED` | — | 本地算法模块异常（任务进入 `failed`） |
| `ALGORITHM_CONTRACT_INVALID` | — | 本地算法模块返回结构不符合契约（任务进入 `failed`） |
| `REVIEW_VALIDATION_FAILED` | 400 | 审核保存或确认请求非法 |
| `EXPORT_VALIDATION_FAILED` | 400 | 导出请求非法或任务状态不允许导出 |
| `EXPORT_FAILED` | 500 | 导出文件系统写入失败 |

MVP 不再使用 `SESSION_*` 和 `INVALID_QUAD_POINTS` 错误码；手机扫码上传直接绑定任务，不单独维护采集会话或四边形框选坐标。

## 统一错误响应结构

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的中文错误描述",
    "details": {}
  }
}
```

所有错误响应均不包含调用堆栈。
