# AGENTS.md

## 作用

本文件管辖 `app/backend/`，补充仓库根级 `CLAUDE.md` 与 `docs/AGENTS.md`。全局规则（离线、隐私、PRD 索引）已在根级和 `docs/AGENTS.md` 写明，本目录文件只列进入 `app/backend/` 工作时才需要的长期独有规则。

## 后端职责边界

- 不得实现医学诊断建议、通用病种规则引擎或病历写回。
- OCR、图像处理、文档解析和 LLM 结构化提取按算法子系统管理；算法实现可以在独立目录、镜像、脚本或适配器中迭代，但后端业务流程必须通过稳定端口、配置和部署契约调用。
- 可以实现：任务状态、持久化、导出、审核契约、字段结果归一化、薄规则质量核验、本地算法子系统调用编排和失败映射。
- `services/algorithm_ports/` 是算法子系统与后端主流程的边界；这里可以写适配器、契约转换、失败处理和轻量编排，避免路由/服务层直接耦合某一套算法内部协议。
- 算法子系统缺失、失败、整体结构化字段为空或契约非法 → 任务进入 `failed`；单字段可疑 → 进入审核页由人工核验。
- 启动入口与 Flask app 工厂在 `main.py`；错误响应统一入口在 `errors.py` / `responses.py`。

## 目录职责（用指针，不复制代码）

- `routes/`：Flask 蓝图，每个文件对应一类接口
  - `task.py` — 任务生命周期、状态推进
  - `review.py` — 人工审核与字段修订
  - `export.py` — 导出请求入口（实现落 `services/export_service.py`）
  - `mobile.py` — 手机端采集与上传
  - `schema.py` — schema 查询与版本管理
  - `maintenance.py` — 维护类接口
  - `system.py` — 健康检查、离线自检
- `services/`：业务服务
  - `algorithm_ports/` — 图像、OCR、文档解析、结构化字段抽取算法子系统的端口、适配器、orchestrator、PaddleOCR VLM server 客户端
  - `copd_extraction/` — 慢阻肺专病字段抽取核心：extractor、port、prompts、admission_contract、llm_client、quality_checks、field_result
  - `task_service.py` — 任务状态机主逻辑
  - `reextraction_service.py` — 模板切换 / 重抽取
  - `export_service.py` — 导出文件生成
  - `review_service.py` — 审核与字段结果更新
  - `cleanup_service.py`、`local_event_log.py`、`offline_check_service.py` 等 — 维护与日志
- `storage/`：`json_store.py` 本地 JSON 持久化（任务、会话、字段结果、审核记录）
- `tests/`：pytest 测试；可执行契约权威来源是 `test_api_contracts.py` 和 `test_backend_e2e.py`
- `config.py`、`settings.py`：后端配置加载与校验；`../config/` 模板在仓库根 `app/config/`，**不在**本目录

## 端口契约原则

- 算法子系统通过 `services/algorithm_ports/` 暴露给主流程；端口签名、失败类型和持久化契约变更前先同步文档与测试。
- COPD 字段抽取的字段体系、结果归一化、质量核验和审核契约在 `services/copd_extraction/`；如切换为新的 OCR/LLM 结构化算法包，应优先保持输出契约兼容，必要时新增适配层。
- `services/algorithm_ports/orchestrator.py` 编排端口调用顺序，是任务推进的唯一入口之一。

## 持久化与导出

- 本地 JSON 存储：`storage/json_store.py`；所有任务、页面图像、字段结果、审核与导出记录的入口。
- 导出：`services/export_service.py` 负责文件生成，路由入口在 `routes/export.py`。
- 状态枚举、错误码统一在 `enums.py`、`errors.py`；与 `docs/Shared/` 保持一致。

## 测试命令

- 全量后端测试：`conda run -n manzufei_ocr python -m pytest app/backend/tests -q`
- API 契约：`app/backend/tests/test_api_contracts.py`
- 端到端：`app/backend/tests/test_backend_e2e.py`
- COPD 抽取单测：`app/backend/tests/test_copd_*.py`
- 端口契约单测：`app/backend/tests/test_*_port.py`
- 仓库根 `app/config/` 不在 pytest 收集范围；测试 fixtures 在 `app/backend/tests/fixtures/`。

## 文档与代码冲突

- 本目录的 API 行为以 `app/backend/tests/test_api_contracts.py` 和 `app/backend/tests/test_backend_e2e.py` 为可执行契约。
- `docs/Backend/Backend_BDD/` 或 `docs/Backend/Backend_TDD/` 与测试冲突时，**先告知用户**，不要直接覆盖；按根级工作方式规则同步修正。
- 修改状态机、错误码、端口契约前，先读 `docs/Shared/state-enums.md`、`docs/Shared/error-codes.md` 和 `docs/Backend/Backend_TDD/02-algorithm-ports.md`、`07-algorithm-failure-contracts.md`、`12-api-contracts.md`。

## 工作方式

- 修改任务/会话/字段状态、错误处理或接口契约前，先确认对应 `docs/Shared/` 与 `docs/Backend/` 文档，再动测试和实现。
- 不得在本目录提交真实本机路径、模型路径、患者数据、密钥；`data/`、`exports/`、`logs/` 是运行产物，不进入仓库。
