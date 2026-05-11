# CLAUDE.md

## 作用

本文件管辖 `docs/Backend/` 下所有后端文档。它继承 `docs/AGENTS.md`，只保留后端文档的总边界和职责分派；BDD/TDD 细则下放到子目录。

## 目录职责

- `Backend_BDD/`：后端用户可观察行为场景，覆盖本地启动、采集会话、上传、任务生命周期、算法集成、Schema、审核持久化、导出、日志隐私和错误恢复。
- `Backend_TDD/`：后端技术测试设计，覆盖单元、集成、API、契约测试、fixtures 和实施顺序。

## 子目录规则

- BDD 场景索引和写法规则见 `Backend_BDD/AGENTS.md` / `Backend_BDD/CLAUDE.md`。
- TDD 设计索引和写法规则见 `Backend_TDD/AGENTS.md` / `Backend_TDD/CLAUDE.md`。

## 阅读顺序

- 改后端行为前，先读 `docs/产品PRD.md` 对应 PR-BE 条目，再读相关 `Backend_BDD/` 场景。
- 改状态机、错误码或响应结构前，先读 `docs/Shared/state-enums.md` 和 `docs/Shared/error-codes.md`。
- 改算法边界前，先读 `Backend_TDD/02-algorithm-ports.md` 和 `Backend_TDD/07-algorithm-failure-contracts.md`。
- 写或调整测试设计时，再读 `Backend_TDD/` 中对应编号文件。

## 工作规则

- 后端文档只覆盖本地服务、文件接收、状态机、持久化、导出、日志和外部算法端口编排。
- BDD 保持业务语言，不写框架、数据库或具体类名等实现细节。
- TDD 记录可执行测试设计，不要求真实 OCR、LLM、图像处理或外部网络。
- 算法模块缺失、异常、空结构化字段或契约非法时，文档必须要求任务进入 `failed`。
- 不在 `Backend_BDD/` 或 `Backend_TDD/` 更深层继续新增 AGENTS.md / CLAUDE.md，除非存在长期独有规则。
