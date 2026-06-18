# AGENTS.md

## 作用

本文件管辖 `docs/` 下所有文档。它补充根级 agent 文件，前端和后端目录的专属规则分别下放到对应子目录。

维护原则参考 HumanLayer 的 CLAUDE.md 指南：短、通用、渐进披露，用指针替代复制。

## 文档入口

- 产品需求源头：`docs/PRD文档/产品PRD.md`
- PRD 实现进度：`docs/PRD文档/PRD任务清单.md`
- 前端文档规则：`docs/Front/AGENTS.md` / `docs/Front/CLAUDE.md`
- 后端文档规则：`docs/Backend/AGENTS.md` / `docs/Backend/CLAUDE.md`

## 信息架构

- `PRD文档/产品PRD.md`：产品目标、主流程、前后端职责、验收标准；修改任何用户行为或业务边界前先读。
- `PRD文档/PRD任务清单.md`：PRD 到实现任务的当前进度索引；只记录边界和状态，不替代 spec/plan。
- `Shared/`：状态枚举、错误码、术语；修改 API、状态机、错误处理或测试断言前先读。
- `Front/`：前端 BDD/TDD 文档；改电脑端/手机端交互、审核、导出、错误展示前先读。
- `Backend/`：后端 BDD/TDD 文档；改本地服务、任务生命周期、算法端口、持久化、导出前先读。
- `部署/`：Windows 离线 Docker 包、GPU/OCR/LLM 运行前提、现场排障和版本锁定经验；改打包、启动、Docker 或模型挂载策略前先读。
- 后端已落地的 API 行为以 `app/backend/tests/test_api_contracts.py` 和 `app/backend/tests/test_backend_e2e.py` 为可执行契约；文档与测试冲突时先说明并同步修正。

## 共享文档

- `Shared/state-enums.md`：MVP 任务状态、字段状态、字段抽取元数据及合法转换。
- `Shared/error-codes.md`：标准错误码、HTTP 状态码映射、统一错误响应结构。
- `Shared/terminology.md`：工作站、任务、手机上传入口、页面图像、算法子系统、Schema 等术语。

## 工作规则

- 修改产品流程或验收标准：先读 `PRD文档/产品PRD.md`，再读相关 `Front/*_BDD/`、`Backend/*_BDD/`。
- 修改任务/会话/字段状态：先读 `Shared/state-enums.md`，再扫前后端 TDD/BDD 引用。
- 修改错误码或错误响应：先读 `Shared/error-codes.md`，再读 `Backend/Backend_TDD/12-api-contracts.md` 和相关 BDD。
- 修改算法集成边界：先读 `PRD文档/产品PRD.md`、`Backend/Backend_TDD/02-algorithm-ports.md` 和 `Backend/Backend_TDD/07-algorithm-failure-contracts.md`。
- PRD 记录业务目标和验收标准；BDD 记录用户可观察行为；TDD 记录可执行测试设计、fixtures、失败条件和实施顺序。
- superpowers 的现行 specs/plans 放在 `docs/superpowers/specs/` 和 `docs/superpowers/plans/`；`docs/superpowers/archive/` 只作历史资料，不作为当前产品契约。
- 共享契约变更必须同时扫描前端和后端引用，发现冲突先说明，不直接用局部文档覆盖全局契约。
- 文档应把 OCR、图像处理、文档解析和 LLM 结构化提取描述为可替换算法子系统，而不是写死某一套实现。是否把具体算法包纳入仓库或部署包，由端口契约、隐私边界、离线交付和版本管理共同决定。
- 不在 BDD/TDD 目录下继续新增 AGENTS.md / CLAUDE.md，除非该目录确有长期独有规则且不能由现有文件覆盖。

## 全局架构边界

- 系统离线运行；手机与电脑只通过本地局域网或电脑热点传输数据。
- 算法子系统可以独立交付，也可以通过镜像、脚本或适配器纳入离线部署；主流程必须保持模块化调用、契约校验和可替换能力。
- 算法子系统缺失、异常、字段结果整体不可用或契约非法时，任务进入 `failed`；单字段可疑进入审核页由人工核验。
- 配置文档只描述命名空间和策略，不提交真实路径、密钥、患者数据路径或模型权重。
- `data/`、`exports/`、`logs/` 是运行产物位置，不作为需求或测试设计文档来源。
