<!-- 组件口径全文（prompt-full.md 统一模板）
组件: verifier（复核器）
版本: verifier.v1
恢复来源: ⚠️ 源码未提交且 blob 05703d3761d989bc 不在 git 对象库，无法逐字恢复
渲染日期: 2026-08-05
-->

# verifier.v1 — 口径全文不可恢复声明

**本版本 prompt 源码从未提交**（2026-08-03 建档时为工作区差量），注册表锚点 blob
`05703d3761d989bc` 不在 git 对象库，**无法逐字恢复 prompt-full 原文**。以下为
注册表与 step7 spec 对该版本的描述片段（**非原文**）：

## 注册表 §5 描述

> 精简五步式（用户差量；kappa 0.40 旧口径，未达 0.7 上岗线）

## step7 spec 描述（2026-08-03-verifier-step7-scale-evidence-design.md）

> 工作区 `build_verification_messages` 已是精简五步式（用户差量，未提交；HEAD 为
> "通用原则 7 条"完整版）——checks 键已改为
> `grounding_supported/field_scope_valid/ocr_text_clear/logic_consistent`，
> 示例为纯文字（无 JSON）

## 与 verifier.v2 的关系

v2 定稿在 v1 基础上增加三类边界、4 个 JSON 微例、输出契约节与 cited ID 预检
（见 `verifier.v2/prompt-full.md`，取自 step7 spec 逐字定稿）。
