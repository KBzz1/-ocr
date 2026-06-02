# 前端 TDD — 建议实施顺序

每一轮必须按 RED → GREEN → REFACTOR 执行。

1. 工作台基础状态、新建任务、二维码、`uploading` 任务和空列表。 (`03-workstation.md`)
2. 手机任务上传、文件选择、上传状态、失败重试和完成上传。 (`04-mobile-capture.md`)
3. 页面列表与页序展示，页序按上传成功顺序固化。 (`05-page-management.md`)
4. 旧四边形框选入口收敛断言。 (`06-quad-interaction.md`)
5. 任务列表 MVP 五状态展示、重试、重新处理和导出入口。 (`07-task-list.md`)
6. 算法失败态、审核页成功结果、字段编辑保存和统一审核完成。 (`08-manual-review.md`)
7. 字段来源提示、抽取元数据展示和三种人工审核状态。 (`09-field-evidence.md`, `10-field-status-confirmation.md`)
8. JSON/Excel 导出、批量 JSON zip 和错误恢复。 (`11-export.md`, `12-error-recovery.md`)
9. 离线、安全和 E2E 主流程。 (`13-offline-security-privacy.md`, `14-e2e-paths.md`)

算法能力只能来自后端成功 fixture；未配置、异常、空结构化结果或契约非法都按失败处理，不允许前端补一套降级逻辑。当前 MVP 不实现采集会话、四边形框选、拖拽排序、补拍替换或修订采集。
