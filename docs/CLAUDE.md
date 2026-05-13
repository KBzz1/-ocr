# CLAUDE.md

## 作用

本文件管辖 `docs/` 下所有文档。它补充根级 agent 文件，前端和后端目录的专属规则分别下放到对应子目录。

维护原则参考 HumanLayer 的 CLAUDE.md 指南：短、通用、渐进披露，用指针替代复制。

## 文档入口

- 产品需求源头：`docs/产品PRD.md`
- PRD 实现进度：`docs/PRD任务清单.md`
- 前端文档规则：`docs/Front/AGENTS.md` / `docs/Front/CLAUDE.md`
- 后端文档规则：`docs/Backend/AGENTS.md` / `docs/Backend/CLAUDE.md`

## 信息架构

- `产品PRD.md`：产品目标、主流程、前后端职责、验收标准；修改任何用户行为或业务边界前先读。
- `PRD任务清单.md`：PRD 到实现任务的当前进度索引；只记录边界和状态，不替代 spec/plan。
- `Shared/`：状态枚举、错误码、术语；修改 API、状态机、错误处理或测试断言前先读。
- `Front/`：前端 BDD/TDD 文档；改电脑端/手机端交互、审核、导出、错误展示前先读。
- `Backend/`：后端 BDD/TDD 文档；改本地服务、任务生命周期、算法端口、持久化、导出前先读。
- 后端已落地的 API 行为以 `app/backend/tests/test_api_contracts.py` 和 `app/backend/tests/test_backend_e2e.py` 为可执行契约；文档与测试冲突时先说明并同步修正。

## 共享文档

- `Shared/state-enums.md`：任务、采集会话、字段状态及合法转换。
- `Shared/error-codes.md`：标准错误码、HTTP 状态码映射、统一错误响应结构。
- `Shared/terminology.md`：工作站、采集会话、四边形框选、算法模块、Schema 等术语。

## 工作规则

- 修改产品流程或验收标准：先读 `产品PRD.md`，再读相关 `Front/*_BDD/`、`Backend/*_BDD/`。
- 修改任务/会话/字段状态：先读 `Shared/state-enums.md`，再扫前后端 TDD/BDD 引用。
- 修改错误码或错误响应：先读 `Shared/error-codes.md`，再读 `Backend/Backend_TDD/12-api-contracts.md` 和相关 BDD。
- 修改算法集成边界：先读 `产品PRD.md`、`Backend/Backend_TDD/02-algorithm-ports.md` 和 `Backend/Backend_TDD/07-algorithm-failure-contracts.md`。
- PRD 记录业务目标和验收标准；BDD 记录用户可观察行为；TDD 记录可执行测试设计、fixtures、失败条件和实施顺序。
- superpowers 的 specs/plans 放在 `docs/superpowers/specs/` 和 `docs/superpowers/plans/`；合并实现后同步去掉过期 worktree 或“待接入”表述。
- 共享契约变更必须同时扫描前端和后端引用，发现冲突先说明，不直接用局部文档覆盖全局契约。
- 文档不得要求本仓库实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则兜底抽取。
- AGENTS.md 与 CLAUDE.md 成对维护；同目录内容保持一致，只替换标题行。
- 不在 BDD/TDD 目录下继续新增 AGENTS.md / CLAUDE.md，除非该目录确有长期独有规则且不能由现有文件覆盖。

## 全局架构边界

- 系统离线运行；手机与电脑只通过本地局域网或电脑热点传输数据。
- 外部算法模块独立交付；本仓库只定义端口、契约校验、状态流转和失败映射。
- 算法模块缺失、异常、空结构化字段或契约非法时，任务进入 `failed`，不得降级为人工补录或规则抽取。
- 配置文档只描述命名空间和策略，不提交真实路径、密钥、患者数据路径或模型权重。
- `data/`、`exports/`、`logs/` 是运行产物位置，不作为需求或测试设计文档来源。
