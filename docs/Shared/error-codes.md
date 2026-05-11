# BDD 标准错误码

| 错误码 | HTTP 状态码 | 场景 |
|--------|------------|------|
| `REQUEST_NOT_FOUND` | 404 | 请求路径不存在 |
| `INTERNAL_SERVER_ERROR` | 500 | 未预期服务端异常 |
| `SESSION_NOT_FOUND` | 404 | 会话不存在 |
| `SESSION_EXPIRED` | 409 | 会话已过期 |
| `SESSION_LOCKED` | 409 | 会话已完成采集，禁止编辑 |
| `UNSUPPORTED_FILE_TYPE` | 400 | 非图片文件 |
| `FILE_TOO_LARGE` | 400 | 图片超过限制 |
| `INVALID_QUAD_POINTS` | 400 | 框选坐标格式非法 |
| `TASK_NOT_FOUND` | 404 | 任务不存在 |
| `INVALID_TASK_TRANSITION` | 400 | 非法状态流转 |
| `ALGORITHM_MODULE_NOT_CONFIGURED` | — | 算法模块未配置（任务进入 failed） |
| `ALGORITHM_MODULE_FAILED` | — | 外部算法模块异常（任务进入 failed） |
| `ALGORITHM_CONTRACT_INVALID` | — | 外部算法模块返回结构不符合契约（任务进入 failed） |
| `REVIEW_VALIDATION_FAILED` | 400 | 审核确认校验失败 |
| `EXPORT_VALIDATION_FAILED` | 400 | 导出前完整性校验失败 |
| `EXPORT_FAILED` | 500 | 导出文件系统写入失败 |

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
