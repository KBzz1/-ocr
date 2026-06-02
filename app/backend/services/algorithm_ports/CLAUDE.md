# CLAUDE.md

## 作用

本文件管辖 `app/backend/services/algorithm_ports/`，是外部算法模块的端口层。根级规则在 `CLAUDE.md`；后端目录规则在 `app/backend/CLAUDE.md`。本文件只写端口层长期独有的边界和契约。

## 端口层定位

- 本目录只写接口抽象、失败处理、契约适配；不实现 OCR、图像预处理、裁剪、透视矫正、文档版面分析或模型推理。
- 不得把外部模块的内部协议、模型权重、依赖算法代码搬进本目录或仓库。
- 调用方根据端口返回的失败类型把任务推到 `failed`（任务级失败），单字段可疑走人工审核；端口层不生成兜底字段或替代结果。

## 当前端口

- `document_parsing.py`：外部文档版面解析端口。
- `field_extraction.py`：外部结构化字段抽取端口的抽象集合。
- `paddleocr_vlm_server.py`：PaddleOCR VLM 常驻服务客户端端口。
- `orchestrator.py`：端口编排与失败聚合。
- `results.py`：端口返回结果的契约类型。
- `fixtures.py`：测试用端口适配器集合，供单元测试替换真实外部模块。

当前 MVP 不使用独立图像处理端口；任务原图列表直接进入 OCR/文档解析端口。若未来重新引入图像预处理或框选能力，必须先改 PRD、Shared 契约和后端 BDD/TDD。

## 端口设计原则

- 每个外部模块一个端口文件，端口签名（输入/输出契约）保持稳定；契约变更需先同步 `docs/Backend/Backend_TDD/02-algorithm-ports.md` 与 `07-algorithm-failure-contracts.md`。
- 端口实现通过依赖注入或工厂接入；测试用 `fixtures.py` 里的适配器替换真实模块，单元测试不依赖 PaddleOCR/LLM/网络。
- 失败类型至少分清：模块缺失、起不来（Docker/PaddleOCR service 不可达）、超时、结果为空、结果契约非法。详见 `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`。
- 端口层不替失败结果生成兜底字段，只能向上抛契约化的失败信号；重试策略属于 `orchestrator` 与任务层。

## COPD 字段抽取端口

- 端口抽象在本目录（`field_extraction.py` 中的 COPD 客户端接口）；具体模型路径、prompt 编排、规则分段、归一化逻辑属于 `app/backend/services/copd_extraction/`，不在本目录。
- 改 COPD 抽取行为前先读 `docs/superpowers/specs/2026-05-21-copd-field-extraction-design.md` 与对应 plan；端口层不携带专病规则。

## 测试约定

- 每个端口必须有单元测试覆盖：模块缺失、起不来、超时、结果为空、结果契约非法 5 类失败路径，外加至少一条正常路径。
- 测试 fixture 走 `fixtures.py`；不允许在测试里直接 import 或 stub 真实 PaddleOCR/LLM/网络。
- 任务级失败契约（端口层 → 任务状态机）以 `app/backend/tests/test_api_contracts.py` 与 `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md` 为准。

## 不在本目录做的事

- 不写专病规则、prompt、规则分段、归一化。
- 不实现图像算法、OCR 算法、版面分析算法。
- 不替外部模块做超时重试策略。
- 不在本目录下再下设 `CLAUDE.md` / `AGENTS.md`。
