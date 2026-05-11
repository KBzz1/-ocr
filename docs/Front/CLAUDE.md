# CLAUDE.md

## 作用

本文件管辖 `docs/Front/` 下所有前端文档。它继承 `docs/AGENTS.md`，只保留前端文档的总边界和职责分派；BDD/TDD 细则下放到子目录。

## 目录职责

- `Front_BDD/`：前端用户旅程和可观察行为场景，覆盖电脑端工作台、手机采集、任务列表、人工审核、导出和错误恢复。
- `Front_TDD/`：前端技术测试设计，覆盖组件、交互、API mock、E2E 路径、fixtures 和实施顺序。

## 子目录规则

- BDD 场景索引和写法规则见 `Front_BDD/AGENTS.md` / `Front_BDD/CLAUDE.md`。
- TDD 设计索引和写法规则见 `Front_TDD/AGENTS.md` / `Front_TDD/CLAUDE.md`。

## 阅读顺序

- 改前端行为前，先读 `docs/产品PRD.md` 对应 PR-FE 条目，再读相关 `Front_BDD/` 场景。
- 改状态、错误提示或 API 断言前，先读 `docs/Shared/state-enums.md` 和 `docs/Shared/error-codes.md`。
- 写或调整测试设计时，再读 `Front_TDD/` 中对应编号文件。

## 工作规则

- 前端文档只覆盖采集交互、页面展示、字段编辑、确认操作、导出触发和错误展示。
- BDD 保持业务语言，不写组件、hook、mock 服务等实现细节。
- TDD 记录可执行测试设计，不要求真实 OCR、LLM、图像处理或外部网络。
- 不要求前端从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 不在 `Front_BDD/` 或 `Front_TDD/` 更深层继续新增 AGENTS.md / CLAUDE.md，除非存在长期独有规则。
