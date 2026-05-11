# CLAUDE.md

## 作用

本文件管辖前端 TDD 测试设计文档。它继承 `docs/Front/AGENTS.md`，只约束组件、交互、API mock 和 E2E 测试设计。

## 文档索引

- `00-boundaries-and-principles.md`、`01-test-environment.md`、`02-quality-gates.md`：边界、测试环境、质量门禁。
- `03-workstation.md`、`04-mobile-capture.md`、`05-page-management.md`、`06-quad-interaction.md`：工作台、手机采集、页序、四边形交互。
- `07-task-list.md`、`08-manual-review.md`、`09-field-evidence.md`、`10-field-status-confirmation.md`：任务列表、人工审核、字段来源、字段状态。
- `11-export.md`、`12-error-recovery.md`、`13-offline-security-privacy.md`：导出、错误恢复、离线隐私。
- `14-e2e-paths.md`、`15-fixtures.md`、`16-implementation-order.md`：E2E、fixtures、实施顺序。

## 工作规则

- 测试设计只描述可执行测试目标、mock 数据、失败条件和边界，不写实现代码。
- 使用 Vitest、React Testing Library、Playwright、MSW 的测试语义时，保持与 `01-test-environment.md` 一致。
- 所有外部 HTTP 请求必须被 mock 或失败；不得要求运行时联网。
- 不设计 OCR 准确率、LLM 抽取质量、图像处理像素效果测试。
- 前端不得基于 schema、OCR 文本或页面内容生成可审核字段。
