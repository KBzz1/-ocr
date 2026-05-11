# 后端 TDD — 任务生命周期

> PRD: PR-BE-004
> 任务状态机定义见 `docs/Shared/state-enums.md`

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-TASK-001 | 单元 | 新任务默认状态为 `created` | 默认状态错误 |
| BE-TASK-002 | 单元 | 合法状态转换全部通过 | 状态机缺失 |
| BE-TASK-003 | 单元 | 非法状态转换返回 `INVALID_TASK_TRANSITION` | 非法转换被接受 |
| BE-TASK-004 | API | `GET /api/tasks` 支持按状态筛选 | 筛选无效 |
| BE-TASK-005 | API | `GET /api/tasks/{taskId}` 返回任务、页面、审核和导出摘要 | 详情缺字段 |
| BE-TASK-006 | 集成 | 任务失败时保存 `error_code`、`error_message`、`failed_at` | 失败原因丢失 |
| BE-TASK-007 | API | 失败任务可 `POST /api/tasks/{taskId}/retry` 回到 `processing` | 重试接口缺失 |
| BE-TASK-008 | 集成 | 处理过程中算法未配置时任务进入 `failed`，保存 `ALGORITHM_MODULE_NOT_CONFIGURED` | 未配置被当作可审核任务 |
| BE-TASK-009 | 集成 | 部分页处理失败时任务进入 `failed`，同时保留已成功页面的外部结果用于排查 | 成功结果被丢弃或任务被错误放行 |
| BE-TASK-010 | 集成 | 状态变更写入状态历史，包含时间和原因 | 无状态历史 |

合法状态转换表必须作为单元测试数据覆盖所有状态。
