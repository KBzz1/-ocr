# evaluator.v1 — 版本分析

- **版本号**: `evaluator.v1`（旧命名 `admission_eval.v1`）
- **锚点**: v1 初版 commit `37b08db`；v1 终态 commit `f8cabaa`（blob sha256 前16: `10df6daa516cced6`）

## 变更摘要

评估指标模块：文本归一化（NFKC/去空白/去标点）、value 两级比较（exact/substring/mismatch）、
幻觉定位（value_located_in_text）、status 比对。v1 终态新增 J 型归一接线、金标不可定位豁免、
长文本核心句重合。

## 依据

- 版本注册表 §4

## 指标对比与结论

无先前版本可比；评估口径从 v1 起建立，report meta 以 `metric_version` 记录。
