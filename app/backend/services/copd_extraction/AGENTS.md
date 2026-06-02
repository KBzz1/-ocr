# AGENTS.md

## 作用

本文件管辖 `app/backend/services/copd_extraction/`，是慢阻肺/呼吸系统入院记录专病字段抽取核心业务代码的长期独有规则。它补充仓库根级 `CLAUDE.md`、`docs/AGENTS.md` 与 `app/backend/CLAUDE.md`，只列进入本目录工作时才需要的额外约束。

## 范围（仓库边界内的允许实现）

- 慢阻肺/呼吸系统入院记录的专病字段抽取主流程。
- 规则分段、字段结果归一化、薄规则质量核验。
- 本地 LLM prompt harness：prompt 编排、结果解析、失败映射和可审计风险标记。
- 第一版只支持慢阻肺/呼吸系统入院记录，**不得扩展为通用医学规则引擎**（根级硬约束）。

## 明确不在本目录做

- OCR、图像预处理、裁剪、透视矫正、版面分析。
- HIS/EMR 接入、医学诊断建议、云服务调用。
- OCR / 文档解析客户端；这些是 `services/algorithm_ports/` 的事，本目录只消费其输出。
- 在算法失败时凭空补造"看起来合理"的字段；空就空，必须进 `failed`。

## 设计权威与实施计划

- 权威设计：`docs/superpowers/specs/2026-05-21-copd-field-extraction-design.md`（字段体系、输出契约、抽取与复核编排）。
- 实施计划：`docs/superpowers/plans/2026-05-21-copd-field-extraction-implementation.md`。
- 工作顺序：先读 spec，再读 plan，最后再写代码；行为与 spec 冲突时按根级规则告知用户，不要直接覆盖。
- 字段清单与 schema：以 `app/config/schemas/copd_admission_record.v1.yaml` 为权威；字段增删必须同步更新 spec 与 PRD 引用。

## 模块职责（指针，不复制代码）

- `extractor.py`：抽取主流程入口；策略选择（`field_batches` / `section_groups`）、失败映射、输出全量字段结果。
- `port.py`：与 `services/algorithm_ports/` 的端口契约边界（消费 OCR/文档解析结果）。
- `section_splitter.py`：规则分段；将原文切到 schema 使用的 `source_section`（主诉、现病史、既往史、个人史、体格检查、辅助检查等）。
- `prompts.py`：抽取与复核 prompt 模板、section group 抽取 prompt、source hint 重生 prompt；prompt 改动视为契约变更。
- `llm_client.py`：本地 LLM 客户端抽象；调用方注入，实现可替换。
- `field_result.py`：字段结果结构、`_default_result`、补齐全量字段、空值判定。
- `quality_checks.py`：薄规则质量核验，产出 `quality_flags`；不静默改写原文。
- `__init__.py`：对外只导出 extractor 与必要类型，不暴露内部 prompt 模板和分段细节。

## 输出契约

- 返回后端的字段结果必须覆盖当前 schema 全量字段；每个字段有且只有一条结果。
- `extraction_status` 合法值：`extracted` / `not_found` / `uncertain`。
- `verification_status` 合法值：`passed` / `suspicious` / `failed` / `not_checked`。
- `original_value` 未抽到时为空字符串；`evidence` 未抽到时为 `null`；`ocr_correction` 不得静默改写。
- 字段结果整体为空、规则不命中、LLM 返回非法 JSON、外部模块契约非法 → 任务进入 `failed`；单字段可疑 → 走人工审核页。

## 测试约定

- 单元测试必须使用可注入的 LLM 客户端（fixture / mock），不依赖真实本地 LLM 推理。
- 覆盖：规则分段、字段结果归一化、prompt 编排、LLM 解析失败映射、整体为空进入 `failed` 的判定。
- 测试样本使用 `app/backend/tests/fixtures/` 下的手写 fixture；不得引用真实患者数据。
- COPD 抽取单测文件位于 `app/backend/tests/test_copd_*.py`，与 `app/backend/CLAUDE.md` 索引一致。

## 禁止事项

- 不实现 HIS/EMR 写回。
- 不生成医学诊断建议。
- 不做云服务调用或运行时联网下载模型。
- 不写规则兜底产生"看起来合理"的字段；空就空，必须进 `failed`。
- 不静默改写 OCR 文本；修正必须留痕在 `ocr_correction`。

## 工作方式

- 修改字段体系、prompt 模板、规则分段、契约字段前：先读 spec，再读 plan，再改测试和实现。
- 状态枚举、错误码、术语以 `docs/Shared/` 为准；与本目录契约冲突时先告知用户。
- 不得在本目录新增更深的 `CLAUDE.md` / `AGENTS.md`。
