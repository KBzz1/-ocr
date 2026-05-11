# AGENTS.md

## 作用

本文件管辖前端 BDD 场景文档。它继承 `docs/Front/AGENTS.md`，只约束用户旅程和可观察行为场景。

## 文档索引

- `workstation.md`：电脑端工作台。
- `mobile-capture.md`、`page-management.md`、`quad-selection.md`：手机采集、页序管理、四边形框选。
- `task-list.md`、`desktop-review.md`：任务列表和电脑端人工审核。
- `field-evidence.md`、`field-status.md`：字段来源和字段状态。
- `export.md`、`error-recovery.md`、`offline-security.md`、`e2e-workflows.md`：导出、错误恢复、离线隐私、端到端流程。

## 工作规则

- 场景使用业务语言描述 Given/When/Then，不写组件、hook、CSS、mock 服务或测试框架细节。
- 场景只覆盖前端可观察行为和 API 契约结果，不评价 OCR、LLM、图像处理质量。
- 算法模块失败、空结果或契约非法时，场景必须要求任务显示 `failed`，不得出现人工降级路径。
- 涉及状态、错误码或术语时，引用 `docs/Shared/` 的权威定义。
