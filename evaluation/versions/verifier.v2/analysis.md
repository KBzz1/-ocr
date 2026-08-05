# verifier.v2 — 版本分析

- **版本号**: `verifier.v2`（2026-08-03 定稿）
- **锚点**: 源码未提交（blob sha256 前16: `1035dfcc5bed471e`，不在 git 对象库）

## 变更摘要

step7：三类边界（字段越界/OCR 错读/完整有据）+ 4 个 JSON 微例（u9xx 虚拟 ID）+
输出契约节（顶层 verifications 一一对应、五字段、checks 四布尔、comment 规则）+
cited ID 预检声明（证据装配缺失不归因于字段）+ 后端语义契约（pass↔checks↔reason 一致性 /
reason↔check 对应 / comment 引用真实 uXXX；违规整组跳过）。

## 依据

- 版本注册表 §5（v2 定稿行）
- 设计定稿：`docs/superpowers/specs/2026-08-03-verifier-step7-scale-evidence-design.md` §3.1

## 指标对比与结论

v2 为 step7 实验基线₂'（定稿 prompt + 上岗形态）与 A'（+字段级分块+完整证据）的
共同 prompt 基线；kappa 结果见 step7 实验（spec 附录）与
`docs/可视化html/2026-08-02-verifier-prompt-v3-report.html` 实验轮次对比。
