# 版本注册表（Version Registry）

> 建档：2026-08-03。目的：三个 LLM 组件（抽取 prompt / 评估指标 / 复核器）的版本号统一带组件前缀，
> 一眼区分"哪个组件的 vN"；每个版本锚定代码 blob sha256 供追溯。历史产物中的旧版本字符串不做追溯性改写。

## 1. 命名规范

| 组件 | 版本常量 | 常量位置 | 报告用语 | 去向 |
|---|---|---|---|---|
| 抽取 prompt | `extractor.vN` | `prompts.py::ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION` | 抽取器 vN | 报告 meta `prompt_version` |
| 评估指标 | `evaluator.vN` | `metrics.py::METRIC_VERSION` | 评估器 vN | 报告 meta `metric_version` |
| 复核器 | `verifier.vN` | `prompts.py::VERIFIER_PROMPT_VERSION` | 复核器 vN | 追踪标识（不渲染进 prompt） |

规则：

- 版本号只表示**该组件自身**演进；任何场景禁止裸写 "v2/v3/v4"，必须带组件词。
- 跨版本比较不得输出可比 delta（`run_eval._print_compare` 对版本不同只警告）。
- 复核器版本常量**不渲染进 prompt**——复核 system 逐字节不变是 vLLM 前缀缓存前提。
- 不在本注册表范围：schema **文件**版本（`admission_record_structured_fields.v1.yaml`、
  `qwen_batch_admission_record.v2.yaml`）是契约文件名而非组件版本；`qwen_batch_prompt.v1`
  是另一引擎（qwen_batch）的 prompt 版本，保持原名。

## 2. 新旧命名映射（2026-08-03）

| 新 | 旧 |
|---|---|
| `extractor.v4` | `admission_record_structured_fields_prompt.v4` |
| `evaluator.v2` | `admission_eval.v2` |
| `verifier.v1` | （无——复核器此前无版本管理，本次建档为基线） |

`data/evaluation/reports/` 与 `/tmp` 下的历史 JSON/HTML 产物保留旧字符串，不做追溯性改写；
跨版本对照以本节映射为准。

## 3. 抽取 prompt 迭代（prompts.py）

| 版本 | 锚点 | blob sha256（前 16） | 变更摘要 |
|---|---|---|---|
| v1 | commit `9307833` | `859614c281ece328` | 固定字段 Qwen prompt 契约初版 |
| v2 | commit `69fe68d` | `92cc870331a81185` | 压缩 Qwen 字段抽取输出 |
| v3 | commit `97627fb` | `80fbb28245332302` | 精简重构为 6 段骨架（删【再次强调】与 OCR 风险段） |
| v3 终态 | commit `6f9bf90`（=HEAD `9e06f34`） | `ec935f027cbd12d5` | +13 条 pe_* 字段边界 description（"仅："渲染） |
| v4（PPEMA-V1 终态） | 未提交 | `01250ed89387ba30` | 61 字段 T/J/D 策略标记 + 字段边界 + 3 个 JSON 微例（旧命名） |
| v4（命名规范化后） | 未提交（当前工作区） | `d121b834ff85688f` | 同上 + 版本常量改 `extractor.v4`；**复核器版本常量在此文件建档** |

> v1–v3 为事后按里程碑命名（PPEMA 报告曾用"抽取器 v3"指 6f9bf90 状态）；v4 是显式版本常量。

## 4. 评估指标迭代（metrics.py）

| 版本 | 锚点 | blob sha256（前 16） | 变更摘要 |
|---|---|---|---|
| v1 初版 | commit `37b08db` | `bd8fea1c00ea29b3` | 评估指标模块（归一化/两级 value/幻觉定位/status 比对） |
| v1 终态 | commit `f8cabaa`（=HEAD `9e06f34`） | `10df6daa516cced6` | J 型归一接线 + 金标不可定位豁免 + 长文本核心句重合 |
| v2（PPEMA-V1 终态） | 未提交 | `bc926f9f…` | 非对称 J 比较器（全正常判断谓词 / 摘录族双向子串 / 大小便投影）+ case_005 金标两处（旧命名） |
| v2（命名规范化后） | 未提交（当前工作区） | `2a1944a318cf75fd` | 同上 + 版本常量改 `evaluator.v2` |

## 5. 复核器迭代（verifier.py，v1 基线 2026-08-03 建档）

复核器此前**无版本管理**；关键迭代按 commit 归档，v1 基线 = 当前工作区状态。

| 里程碑 | 锚点 | blob sha256（前 16） | 变更摘要 |
|---|---|---|---|
| 初版 | commit `bb61f1b` | `96edb64da1e7a500` | FieldVerifier：verdict 解析/失败降级/quality_flags 映射 + 复核 prompt 激活 |
| 降误报 | commit `ae2f1f1` | — | 证据一致性硬约束/找茬失败转 pass/误报反例 |
| 去对抗改造 | commit `2039e80` | `817de47260f04975` | 中性核验 + OCR 错读职责显式化 + 长字段拆句逐句检查 + comment 截断 |
| 精简重构 | commit `afd1722` | — | 统一骨架/去重/错读 1 行 3 例 |
| 召回强化（step5） | commit `c3946a9` | — | 表达瑕疵阈值句 + 逻辑一致性扩展 + 越界不豁免 + 2 个行为示例 |
| 分组调用（step6 实现） | commit `6a765af`（=HEAD） | `75eaf2922c370a9b` | group_by 字段级/字段簇级 + 分组失败隔离 |
| v1 基线 | 未提交（2026-08-03 建档时） | `05703d3761d989bc` | 精简五步式（用户差量；kappa 0.40 旧口径，未达 0.7 上岗线） |
| v2 定稿 | 未提交（2026-08-03） | `1035dfcc5bed471e` | step7：三类边界 + 4 个 JSON 微例（u9xx 虚拟 ID）+ 输出契约节 + cited ID 预检 + 后端语义契约（pass↔checks↔reason 一致性 / reason↔check 对应 / comment 引用真实 uXXX；违规整组跳过） |
| **v3 定稿** | 未提交（2026-08-04） | `7f9ca9aece4be109` | prompts.py（v3 文本）+ verifier.py（新契约）：表述规范性契约（错读/病句等非标准表述，术语陌生不标）+ 术语陌生判别 + 5 个 JSON 微例（含错读形似规范词对照）+ 逗号级拆句（value >40 字补充拆分）+ checks 键 `ocr_text_clear`→`text_standard`、`ocr_quality_issue`→`nonstandard_expression` + 字段级分组 |

## 6. 当前状态速查（2026-08-04）

全部改动**未提交**（HEAD `9e06f34`，worktree `prompt-refactor-field-boundary`）：

- prompts.py（extractor.v4 + verifier.v3 常量）：`7f9ca9aece4be109fe320dee5fda291d4fde62be4db78610738cefc8c4e23dcb`
- metrics.py（evaluator.v2）：`2a1944a318cf75fdd9fd91d309462ef3405e646098e8c2e5314bf9155a52d5ff`
- verifier.py（v3 新契约 + verifier.v2 语义契约）：`8ff3212742821139181ef223b327aec0a7c6aa695d624194c54a3754ff31e6f1`

版本注册表变更规则：组件版本演进（prompt/指标/复核器内容改动）时，先在本表登记新版本与锚点 hash，
再动代码；本表是跨组件版本对照的唯一权威。
