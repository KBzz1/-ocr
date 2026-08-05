# extractor.v2 — 版本分析

- **版本号**: `extractor.v2`（旧命名沿用 `admission_record_structured_fields_prompt.v1` 常量，事后按里程碑命名）
- **锚点**: commit `69fe68d`（blob sha256 前16: `92cc870331a81185`）

## 变更摘要

压缩 Qwen 字段抽取输出：明确 evidence 用 `evidence_ids`（编号列表），不允许模型自行撰写
evidence 文本；补充严禁 OCR 修正/标题纠正/页序重排、诊断字段仅摘录原文等规则；未找到字段
返回 `status="not_found", value="", evidence_ids=[]` 不得省略。

## 依据

- 版本注册表 §3

## 指标对比与结论

无独立评估报告；为 v1→v3 中间形态。
