# AGENTS.md

## 作用

本文件管辖后端 TDD 测试设计文档。它继承 `docs/Backend/AGENTS.md`，只约束单元、集成、API 和契约测试设计。

## 文档索引

- `00-boundaries-and-principles.md`、`01-test-layers.md`：边界和测试层次。
- `02-algorithm-ports.md`、`07-algorithm-failure-contracts.md`：算法端口和失败契约。
- `03-system-startup.md`、`04-capture-sessions.md`、`05-file-upload.md`、`06-task-lifecycle.md`：启动、会话、上传、任务生命周期。
- `08-schema-management.md`、`09-review-results.md`、`10-export-service.md`、`11-logging-privacy.md`：Schema、审核、导出、日志隐私。
- `12-api-contracts.md`、`13-deployment.md`、`14-fixtures.md`、`15-implementation-order.md`、`16-prohibited-items.md`：API、部署、fixtures、实施顺序、禁止项。

## 工作规则

- 测试设计只描述测试目标、fixture、失败条件和契约边界，不写实现代码。
- 外部算法模块使用 fixture 适配器模拟；不得要求真实 OCR、LLM 或图像处理模块参与测试。
- 算法端口失败、空结构化字段、契约非法必须映射为任务 `failed`。
- 不设计规则抽取、人工降级、HIS/EMR 写回、云服务或外部网络依赖。
- API、状态机和错误码以 `docs/Shared/` 为权威来源。
