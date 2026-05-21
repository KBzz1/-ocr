# 后端 TDD — 任务生命周期

> PRD: PR-BE-004
> 任务状态机定义见 `docs/Shared/state-enums.md`

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-TASK-001 | 单元 | 新建任务默认状态为 `uploading` | 默认状态错误 |
| BE-TASK-002 | 单元 | 只允许 `uploading / processing / review / done / failed` 的合法转换 | 状态机缺失或接受旧状态 |
| BE-TASK-003 | 单元 | 非法状态转换返回 `INVALID_TASK_TRANSITION` | 非法转换被接受 |
| BE-TASK-004 | API | `GET /api/tasks` 支持按 MVP 状态筛选 | 筛选无效 |
| BE-TASK-005 | API | `GET /api/tasks/{taskId}` 返回任务、页面、处理摘要和审核状态 | 详情缺字段 |
| BE-TASK-006 | 集成 | 任务失败时保存 `error_code`、`error_message`、`failed_at` | 失败原因丢失 |
| BE-TASK-007 | API | 失败任务可 `POST /api/tasks/{taskId}/retry` 回到 `processing` | 重试接口缺失 |
| BE-TASK-008 | 集成 | 外部 OCR/文档解析未配置或异常时任务进入 `failed` | 未配置被当作可审核任务 |
| BE-TASK-009 | 集成 | 慢阻肺字段结果整体不可用、全字段为空或契约非法时任务进入 `failed` | 无效结果进入审核 |
| BE-TASK-010 | 集成 | 单字段可疑或复核失败不阻断任务进入 `review`，字段在审核页提示 | 单字段问题阻断整单或风险丢失 |
| BE-TASK-011 | API | `review` 或 `done` 任务可重新处理回到 `processing` | 待审核或已完成任务无法重新处理 |

合法状态转换表必须作为单元测试数据覆盖所有 MVP 状态。
