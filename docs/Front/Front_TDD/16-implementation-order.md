# 前端 TDD — 建议实施顺序

每一轮必须按 RED → GREEN → REFACTOR 执行。

1. 工作台基础状态、二维码、`capturing` 任务、空列表。 (`03-workstation.md`)
2. 手机采集会话、文件选择、上传状态。 (`04-mobile-capture.md`)
3. 四边形框选 UI 与坐标上传契约（全手动，无外部算法）。 (`06-quad-interaction.md`)
4. 页面管理（仅拖拽排序）、完成采集、锁定会话、修订采集。 (`05-page-management.md`)
5. 任务列表状态展示、缩略图、重试、重新处理、修订采集、取消采集。 (`07-task-list.md`)
6. 算法失败态、审核页成功结果、批量确认、失焦保存（仅值变化时）、空值确认。 (`08-manual-review.md`)
7. 字段状态（含 `confirmed_empty`）、来源提示、确认校验（预警窗而非硬阻断）。 (`09-field-evidence.md`, `10-field-status-confirmation.md`)
8. 导出触发（预警面板）和错误恢复（含取消/修订采集）。 (`11-export.md`, `12-error-recovery.md`)
9. 离线、安全、E2E 主流程（含修订采集、取消采集）。 (`13-offline-security-privacy.md`, `14-e2e-paths.md`)

算法能力只能来自外部成功 fixture；未配置、异常、空结构化结果或契约非法都按失败处理，不允许前端或后端补一套降级逻辑。
框选完全由用户手动调节，前端不实现自动边界识别，也不测试外部模块返回的自动边界。
