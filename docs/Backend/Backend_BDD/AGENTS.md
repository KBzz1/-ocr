# AGENTS.md

## 作用

本文件管辖后端 BDD 场景文档。它继承 `docs/Backend/AGENTS.md`，只约束后端用户可观察行为场景。

## 文档索引

- `system-startup.md`、`capture-session.md`、`file-upload.md`：启动、采集会话、图片上传。
- `task-lifecycle.md`、`algorithm-integration.md`、`schema-management.md`：任务状态、算法集成、Schema。
- `review-persistence.md`、`export.md`：审核结果持久化和导出。
- `logging-privacy.md`、`error-recovery.md`：日志隐私和错误恢复。

## 工作规则

- 场景使用业务语言描述 Given/When/Then，不写框架、数据库、类名或函数名。
- 场景只覆盖后端业务壳、状态流转、持久化、导出、日志和外部算法端口编排。
- 不评价 OCR、LLM、图像处理质量，不要求真实算法模块参与测试。
- 算法模块缺失、异常、空结构化字段或契约非法时，场景必须要求任务进入 `failed`，不得出现规则兜底或人工降级。
- 涉及状态、错误码或术语时，引用 `docs/Shared/` 的权威定义。
