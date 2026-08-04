# 抽取提示词策略映射与评估语义对齐设计

## 0. 元信息

- Task slug：`prompt-policy-metric-alignment-v1`
- Goal ID：`PPEMA-V1`
- 状态：`PLAN_FROZEN`
- 日期：2026-08-03
- 项目根：`/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary`
- 分支：`worktree-prompt-refactor-field-boundary`
- 起始提交：`9e06f34ea0e1babb56c621e532703f9e424c3ab0`
- 架构师：Codex `/root`
- 高模型身份：`GPT-5.5 极速`。这是用户确认的网页端产品档位，不推断或伪造 API `model_id`。

权威来源按优先级排列：

1. 用户批准的四项建议：保留约束解码、恢复字段边界与策略映射、加入局部 JSON 示例、修正评估与金标语义；
2. 本文件的冻结设计；
3. `AGENTS.md`、`CLAUDE.md`、`docs/AGENTS.md`、`app/backend/CLAUDE.md`、`app/backend/services/copd_extraction/CLAUDE.md`；
4. `docs/superpowers/specs/2026-06-18-qwen-admission-record-structured-fields-evidence-design.md`；
5. 当前代码与测试。此前分块复核实验里“prompts.py 零改动”只约束那一轮实验，不是本轮用户明确批准的提示词改造禁令。

## 1. 目标、非目标与完成定义

### 1.1 Goal

在不改变 61 个业务字段、外部字段结果、审核状态、前端和导出契约的前提下，一次完成以下四项改造：

1. 保留抽取 JSON Schema 约束解码和后端语义校验，并用回归测试证明二者仍在；
2. 让运行时抽取提示词真正看到字段边界和每字段 `T/J/D` 取值策略；
3. 用三个短小、对比明确的 JSON 微型示例替换当前三条自然语言示例；
4. 发布 `admission_eval.v2` 评估口径，修复已确认的 value 假阴性和 `case_005` 两处金标边界冲突。

完成后只对 `case_005` 做一次 Qwen3.5-4B 冒烟，生成包含完整实际提示词、GPT-5.5 极速离线重评分和新 4B 结果的 HTML 报告。本轮不运行 6 例全量，不做消融、A/B 或质量失败后的继续调参。

### 1.2 非目标

- 不修改证据切分器、证据 ID 规则、复核器 prompt、复核分组或 kappa 校准；
- 不新增业务字段、状态、服务、医学推理规则引擎或诊断建议；
- 不修改 JSON 响应形状、字段顺序合同、前端、导出、审核状态或 reason code；
- 不把 61 字段完整答案写成 few-shot；
- 不把 JSON Schema 当成语义正确性的保证；
- 不批量重写 6 例金标；除本设计明确列出的 `case_005` 两项外，不得改动金标；
- 不运行第二个病例，不运行 6 例全量，不依据单次冒烟结果再改第二版 prompt。

### 1.3 `GOAL_REACHED` 完成证据

- 四项改造的代码、合成单测、聚焦回归和 R2 忠实性审查均通过；
- 运行时完整 system prompt 中每个字段都有且只有一个 `P=T/J/D` 标记，13 个现有查体边界与新增辅助检查边界可见；
- 三个局部示例是合法 JSON，且正式响应仍由现有严格 JSON Schema 约束为 61 字段；
- `admission_eval.v2` 的同版本比较、J 型比较、大小便字段投影和金标变更有可回读证据；
- 原始 GPT-5.5 极速输出按 v2 离线重评分完成；
- `case_005` 新 4B 冒烟完成，结构门通过；质量无论好坏均如实报告，不触发调参；
- HTML 报告和完整提示词附录存在，`STATUS.md`、`WORKER_REPORT.md` 与磁盘一致；
- 未经批准的 C 级偏离为零。

## 2. 当前证据与真实阶段

### 2.1 已验证事实

- 当前 worktree 是脏工作区：22 条状态记录，其中 18 个 tracked 文件已有未提交差量，另有 4 个未跟踪文件。它们均视为用户现有工作，不得回退、覆盖或整批提交。
- 抽取路径已经通过 `response_format.type=json_schema` 使用严格结构约束；没有 schema 的旧调用仍使用 `json_object`。后端仍验证字段唯一性、完整覆盖、顺序和 evidence ID。
- `app/config/schemas/admission_record_structured_fields.v1.yaml` 已含 13 个查体 `description`，但 `schema_loader.py` 规范化时丢弃该键，因此实际运行 prompt 看不到这些边界。
- `prompts.py` 已有 `_field_is_judgement` 和 J 字段集合，但 `_field_line` 不渲染策略，模型只看到三种策略定义，不知道具体字段该用哪一种。
- 当前三个示例是自然语言说明，不展示 `status/value/evidence_ids` 的联动。
- GPT-5.5 极速在完全相同的 v3 system、user 和 JSON Schema 下，对 `case_005` 得到：status `59/61=96.72%`、value `41/49=83.67%`、extraction FN `2`、confirmed hallucination `0`。当前 4B 对应结果为 status `49/61=80.33%`、value `29/49=59.18%`、FN `12`。因此模型能力是主要变量，但不是唯一变量。
- 高模型原始扣分中，`hpi_stool_status`、`pe_neck`、`pe_cardiac_exam`、`pe_abdomen` 是确定性评估假阴性；`pe_eyes` 和 `aux_renal_function` 暴露金标与新字段边界不一致；血气两个状态错误来自辅助检查来源范围表述过窄。

### 2.2 输入身份

| 输入 | SHA-256 |
|---|---|
| GPT-5.5 极速原始 JSON | `00dffe1110a59fcb5aa51be975feb1141cf0d6777d034953509976fcb6b7a9d1` |
| `case_005` 当前金标 | `6e68a0b3a67f8adfac5c4bb95bfbd1a10302a9d87a3c2f78507491a04892dcc1` |
| 高模型对比 HTML | `2e137bed2a145788f74471296b902247345ca9e9cd67c72702fe78f6a22cadb9` |
| 当前 `prompts.py` | `9d37bc0d9a6d25137253dd1d34ffc59c5ac298546a3db812c200a5ad07bf5783` |
| 当前 `metrics.py` | `8d6ece744e9405be4e56a9bcf80f51824491f4bbc36d1324e8e6c7d97c107f37` |

原始 JSON 路径：`/mnt/c/Users/97949/.codex/attachments/1a10e97b-93ef-4c7d-9dcc-16aa0212bb4e/pasted-text.txt`。不得把该文件复制进 Git；只读消费并记录 hash。

### 2.3 当前阶段

这是已冻结、尚未由外部 Controller 启动的执行设计。已有 HTML、分析和 Worker prompt 都不等于本 Goal 已实现。

## 3. 四象限不确定性

| ID | 分类 | 证据与处理 | 负责人/最晚点 |
|---|---|---|---|
| U1 | 已知且可直接处理 | `description` 被 loader 丢弃；按冻结实现保留并测试公共 API allowlist 不变化 | T1 implementer / T1 结束前 |
| U2 | 已知且可直接处理 | J 字段集合在 prompt 与 metrics 重复；迁移为一个内部权威注册表，成员保持当前集合不变 | T1 implementer / FIDELITY_REVIEW |
| U3 | 已知未知、已有判据 | 单次 4B 质量结果未知；只跑一次并报告，质量不佳不是继续调参授权 | T4 Controller / CLAIM_REVIEW |
| U4 | 已知未知、可能外部阻塞 | 本地 vLLM 是否可用；先健康检查，可做一次传输/结构失败重试，不得改部署或模型 | T4 Controller / 运行前 |
| U5 | 未知但非承重 | helper 名称、报告 CSS、测试函数拆分由 Worker A 级决定 | 对应 implementer |

## 4. 架构师 Loop 与冻结设计

设计 Loop：问题定位 → 同提示词模型对照 → 识别能力变量与评估假阴性 → 选择最小可归因改造 → 冻结一次冒烟与结论边界。

### 4.1 建议一：保留约束解码，但不把它当语义能力

- `response_schemas.py` 和 `port.py` 的当前抽取 JSON Schema 路径保持不变；禁止改回 `json_object`。
- 结构约束继续只保证键、类型、枚举和 61 项长度；唯一性、顺序、真实 evidence ID 和字段语义继续由后端验证。
- 本轮只补回归测试，不增加 `prefixItems`、医学枚举或新的输出键。

### 4.2 建议二：字段边界和策略必须真实进入运行时 prompt

- `schema_loader.py` 保留可选字符串 `description`；非法非字符串必须 fail closed。
- 新建内部 `field_policies.py` 作为 prompt 与评估共同的值策略真源。J 集合成员与当前 `_NORMAL_JUDGEMENT_FIELD_KEYS` 完全一致，不得自行增删；diagnosis 组固定 D，其余固定 T。
- 字段目录固定格式：`field_key｜中文名｜P=T/J/D｜特有边界`。策略定义只写一次：T=原文摘录，J=正常/阴性输出“正常”、异常只摘异常，D=保留诊断编号和顺序。
- 保留当前章节共同规则与 HPI 时间边界；不恢复重复的 `source_scope/time_scope/include/exclude/value_policy` 长卡片。
- 辅助检查来源范围冻结为：明确带检查标签和值的结果可以出现在辅助检查章节或现病史中；仍禁止从诊断、症状或医学常识反推数值。
- 为 `aux_electrolytes` 与 `aux_renal_function` 增加互斥边界：前者是电解质/矿物项目，后者是 eGFR、尿素、肌酐、尿酸等肾功项目。
- `ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION` 升为 `admission_record_structured_fields_prompt.v4`。
- `/api/schema/current`、字段结果、审核状态、前端和导出允许键保持现状；prompt metadata 不得成为新业务字段。

### 4.3 建议三：固定三个局部 JSON 微型示例

示例只展示局部 `output_fields`，正式输出仍必须覆盖 61 字段；示例 ID `u901-u903` 只属于示例，禁止进入真实输出。

1. 共享否定作用域：同一合成证据同时支持一个 T 字段的否定摘录和一个 J 字段的“正常”，两者均为 `found` 并引用同一 ID；
2. J 型异常优先：合成心脏查体同时有异常与正常描述，输出只保留异常片段，不因出现“正常”而折叠；
3. 禁止推导 BMI：合成证据只有身高和体重，二者 `found`，BMI 必须 `not_found`、空 value、空 evidence IDs。

示例必须是可解析 JSON，不得给完整顶层响应，不得加入第四个示例。

### 4.4 建议四：`admission_eval.v2` 语义

- 报告 meta 必须有 `metric_version="admission_eval.v2"`；跨版本比较不得输出可比 delta，只能警告“口径不同”。
- J 型 value 比较是非对称合同：
  - 金标是异常摘录时，先做原文归一后的 exact/substring，比预测包含相同异常但附带正常描述判为正确；
  - 金标属于正常/阴性族时，预测必须是规范值“正常”才判正确，长篇混合正常与异常文本不得因含“正常”而通过；
  - grounding 的 normal-family 豁免也只允许预测规范值“正常”，不能豁免任意含正常词的长文本。
- `hpi_stool_status` 和 `hpi_urine_status` 允许把金标“大小便…”分别投影到“大便…”和“小便…”比较；不按普通逗号拆事实，不推广到其他字段。
- `case_005` 金标只改两处：
  - `pe_eyes` 遵守“排除颜面”的新边界，改为该眼部检查的正常判断；
  - `aux_renal_function` 只保留肾功项目并纳入尿酸，不再复制电解质项目。
- `aux_blood_gas_pco2/po2` 金标保持 found；由 4.2 的跨章节明确检查结果规则解决 prompt/金标冲突。
- 不修改其余 5 个病例，不修改 `case_005` 其他字段。

按上述语义，GPT-5.5 极速原始输出的确定性 v2 预期为：status `59/61`、value `46/49`、extraction FN `2`、over-extraction FP `0`、confirmed hallucination `0`；`pe_eyes` 和两个血气字段应仍是 value 错误。数值不符即说明实现或离线重评分接线有漂移，不能以“模型不同”解释。

## 5. Worker 自主权

### A 级：可自行处理并记录

- helper/测试函数命名、局部重构、报告 CSS、临时目录；
- conda 入口解析、只读健康检查、同等的 pytest 参数；
- 不改变语义的格式化和错误消息改良。

### B 级：按有限判据选择

- 若共享策略注册表引入循环依赖，可放在 `copd_extraction/field_policies.py` 或 `evaluation` 与 prompt 都能安全导入的更浅内部模块；判据是单一真源、无外部暴露、测试通过。
- 若 `description` 出现在内部 review artifact，允许保留；但公共 schema API、field result 和 export 的已允许键不能变化。
- 第一次 4B 调用若仅发生传输失败、契约/证据结构失败，可在修复确定性结构问题后对同一 `case_005` 重试一次；不能修改 prompt 语义。

### C 级：不得改变

- 四项建议、J 字段集合成员、三个示例职责、评估 v2 语义、两处金标裁定；
- 61 字段、JSON 输出契约、外部接口、模型、温度、病例、运行次数和无全量约束；
- 不得把质量失败变成新 prompt、第二病例、6 例全量或开放式调参。

承重 C 级冲突且安全替代穷尽时只能形成 `HARD_BLOCKED`，不能自行重新设计。

## 6. 执行轨道与接口

| Track | 目标 | 输入 | 写入范围 | 输出/最终门禁 | 整合者 |
|---|---|---|---|---|---|
| P / T1 | 运行时 prompt 策略与 JSON 微例 | schema、loader、prompts、现有约束解码 | prompt/schema loader/聚焦测试 | v4 完整 prompt + R2 fidelity pass | Controller |
| M / T2 | `admission_eval.v2` 与两处金标裁定 | metrics/runner/run_eval/golden | evaluation、聚焦测试、case_005 ignored golden | v2 单测 + hash + R2 pass | Controller |
| O / T3 | 离线同版本重评分 | GPT-5.5 原始 JSON、T1/T2 checkpoint | ignored reports、STATUS/REPORT | 预期 59/61、46/49 等 | Controller |
| S / T4 | 唯一 4B 冒烟与报告 | T3 release identity | `/tmp`、ignored HTML、STATUS/REPORT | 61 字段结构门 + 真实结果 | Controller |

T1 与 T2 因共享策略注册表串行；不得伪并行修改同一真源。

## 7. 资源、恢复和外部边界

- 环境：`/home/kbzz1/miniconda3/bin/conda run -n manzufei_ocr`；离线运行，不访问云 API。
- 当前 dirty worktree 是输入，不得 reset、checkout、clean、stash 或覆盖无关差量。
- 每个任务完成后记录文件 hash 和命令退出码；不强制 commit，避免把用户已有差量混入提交。
- 真实 4B 运行只允许 `case_005`，temperature `0`，`--no-verifier`，以隔离抽取 prompt 且节省调用。
- 原始 JSON、golden 和报告属于 `data/evaluation/` 或 attachment 运行资产，不进 Git。
- 若上下文压缩或 Worker 重启，从 `STATUS.md` 的首个非 DONE Task 恢复，不重跑已通过同 hash 门禁。

## 8. 最小验证矩阵

| 主张/风险 | 最小验证 | 通过条件 | 失败后的决定 |
|---|---|---|---|
| 约束解码仍启用 | fake client/请求参数单测 | extraction 传 `json_schema`，旧调用仍 `json_object` | 修接线，不改 schema 语义 |
| 边界真实可见 | 加载仓库 schema 生成实际 prompt | 13 个现有 description、辅助检查边界、61 个 P 标记出现 | 修 loader/render |
| 示例不会代替契约 | 解析 3 个 JSON 微例 + response schema 回归 | 3 个合法局部 JSON；正式 schema 仍 61 项 | 修示例或测试 |
| J 假阴性修正 | 合成 abnormal+normal、normal+mixed 测试 | 前者通过、后者失败 | 修专用比较器 |
| 大小便投影受控 | stool/urine 合成测试 + 其他字段反例 | 仅两字段等价 | 修字段路由 |
| 金标边界一致 | diff + hash | 只改指定两项 | 回退越界改动 |
| 高模型重评分可复现 | 离线 evaluate_sample | 精确命中冻结预期 | 停止并审计接线 |
| 4B 结构有效 | 一次 case_005 | contract invalid 0、61 字段、ID 合法 | 允许一次结构修复重试 |
| 结论不过界 | CLAIM_REVIEW | 区分模型能力、prompt、指标修正；保留负结果 | 修报告，不重跑 |

## 9. 硬阻塞与允许终局

- `GOAL_REACHED`：1.3 的证据全部成立；4B 质量可以不达旧硬门，但必须完成结构有效的一次运行并如实报告。
- `HARD_BLOCKED`：只有以下情况合法：原始承重输入不可读且无法安全恢复；R2 独立审查持续不可用；vLLM 在健康检查和一次安全重试后仍不可用；或实现需要改变 C 级决定/新权限。
- 单测首次失败、模型质量不佳、无 6 例全量、时间到、上下文压缩和 `PARTIAL` 都不是合法终局。
- 删除、部署变更、云调用、6 例全量和第二 prompt 版本需要用户新授权。

## 10. 交付证据合同

Worker 必须在 `WORKER_REPORT.md` 记录：实际修改文件、before/after hash、命令和退出码、R2 reviewer 身份与结论、GPT-5.5 重评分、唯一 4B 运行身份和结果、HTML 路径、失败适配历史、未执行项、最终终局与恢复入口。聊天不能用“计划完成”替代实现/运行证据。

## 11. 决策记录

| 时间 | 决策 | 原因/证据 | 影响轨道 | 批准者 |
|---|---|---|---|---|
| 2026-08-03 | 高模型记为 GPT-5.5 极速产品档位 | 用户明确纠正模型身份 | O/报告 | 用户 |
| 2026-08-03 | 四项改造一次完成，不做消融 | 用户要求低测试成本 | 全部 | 用户 |
| 2026-08-03 | 本轮仅 case_005，不跑 6 例 | 6 例 v3 已运行且失败；本轮先验证改造 | S | 架构师 |
| 2026-08-03 | v2 只改两处 case_005 金标 | 避免指标修复演变为批量改标 | M | 架构师 |
| 2026-08-03 | 质量失败也停止，不自动调参 | 保持一次性、可归因执行 | S/报告 | 架构师 |

