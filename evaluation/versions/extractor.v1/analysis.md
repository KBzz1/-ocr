# extractor.v1 — 版本分析

- **版本号**: `extractor.v1`（旧命名 `admission_record_structured_fields_prompt.v1`）
- **锚点**: commit `9307833`（blob sha256 前16: `859614c281ece328`）
- **日期**: 注册表建档日 2026-08-03（v1–v3 为事后按里程碑命名）

## 变更摘要

固定字段 Qwen prompt 契约初版。字段表来自 `admission_record_structured_fields.v1` schema，
证据以编号单元（evidence_units）形式入 prompt，含 OCR 风险提示（1/I/l、P62/PO2 等近形错读）、
药名纠偏规则、字段输出契约（section_key/section_label/field_key/field_label/status/value/evidence_ids）。

## 依据

- 版本注册表 §3（`docs/Shared/version-registry.md`）

## 指标对比与结论

v1 为体系初版，无先前版本可比；无独立评估报告（评估体系 08-01 才建立）。
