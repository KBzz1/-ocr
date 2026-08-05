# evaluator.v2 — 版本分析

- **版本号**: `evaluator.v2`（显式版本常量 `METRIC_VERSION`；旧命名 `admission_eval.v2`）
- **锚点**: 当前 HEAD（blob sha256 前16: `77bed02fb070b47d`；注册表 §4 记录 `2a1944a318cf75fd` 为 2026-08-04 建档时未提交工作区快照）

## 变更摘要

非对称 J 比较器（全正常判断谓词/摘录族双向子串/大小便投影）+ case_005 金标两处修正；
J 字段集合以 prompt 策略共享真源（`field_policies.NORMAL_JUDGEMENT_FIELD_KEYS`）为准。

## 依据

- 版本注册表 §4（v2 两行：PPEMA-V1 终态 + 命名规范化后）

## 指标对比与结论

跨版本比较不得输出可比 delta（`run_eval._print_compare` 对版本不同只警告）；
v1→v2 为口径演进，非回归比较。
