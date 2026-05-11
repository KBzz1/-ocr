# 后端 TDD — 实施顺序

每个条目执行时必须：先写失败测试 → 运行确认 RED → 写最小实现 → 运行确认 GREEN → 运行相关测试确认无回归 → 重构后再次运行。

1. 状态机、错误码、统一响应结构。 (`docs/Shared/state-enums.md`, `docs/Shared/error-codes.md`)
2. 系统状态、离线启动、局域网地址选择。 (`03-system-startup.md`)
3. 采集会话创建、过期、锁定。 (`04-capture-sessions.md`)
4. 上传文件校验、任务目录、页面元数据。 (`05-file-upload.md`)
5. 页面删除、排序、finish 幂等和页序固化。
6. 算法端口失败契约：未配置、异常、空结构化字段、契约非法。 (`07-algorithm-failure-contracts.md`)
7. 任务处理编排：算法失败进入 `failed`，成功 fixture 进入 `ready_for_review`。 (`06-task-lifecycle.md`)
8. schema 管理和候选字段契约校验。 (`08-schema-management.md`)
9. 人工审核保存、确认校验、修改历史。 (`09-review-results.md`)
10. JSON/Excel 导出和导出前完整性检查。 (`10-export-service.md`)
11. 日志、隐私、部署与断网测试。 (`11-logging-privacy.md`, `13-deployment.md`)
12. API 全量契约测试和关键 E2E。 (`12-api-contracts.md`)
