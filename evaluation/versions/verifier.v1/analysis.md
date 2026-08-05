# verifier.v1 — 版本分析

- **版本号**: `verifier.v1`（2026-08-03 建档基线；此前复核器无版本管理）
- **锚点**: 源码未提交（blob sha256 前16: `05703d3761d989bc`，不在 git 对象库）

## 变更摘要

精简五步式（固定审核顺序：grounding → field scope → OCR quality → logic consistency →
verdict），checks 键为 `grounding_supported/field_scope_valid/ocr_text_clear/logic_consistent`，
示例为纯文字（无 JSON）。kappa 0.40 旧口径，未达 0.7 上岗线。

## 依据

- 版本注册表 §5（v1 基线行）
- step7 spec 描述：工作区已是精简五步式（用户差量，未提交；HEAD 为"通用原则 7 条"完整版）

## 指标对比与结论

kappa 0.40（旧口径，未达 0.7 上岗线）。前身里程碑（注册表 §5）：初版 `bb61f1b`、
降误报 `ae2f1f1`、去对抗改造 `2039e80`、精简重构 `afd1722`、召回强化 `c3946a9`、
分组调用 `6a765af`。

## 附：本目录报告说明

`report.html` 为 2026-08-02 复核器去对抗改造实验报告。**注意：报告内 "v2/v3" 为实验轮次
命名**（对应去对抗改造 2039e80 / 精简重构 afd1722 里程碑），非本目录正式版本号；
作为 v1 基线前身实验证据收录。
