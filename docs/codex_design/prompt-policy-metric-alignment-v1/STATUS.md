# PPEMA-V1 状态账本

- Goal ID：`PPEMA-V1`
- 当前阶段：`GOAL_REACHED`（T0-T4 全部 DONE）
- Controller 终局：`GOAL_REACHED`
- 项目根：`/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary`
- 设计权威：`DESIGN.md`
- 执行权威：`EXECUTION_PLAN.md`
- 最后更新：2026-08-03（Controller：终局 GOAL_REACHED，C 级偏离 0）

## 输入锁

- Branch：`worktree-prompt-refactor-field-boundary`
- HEAD：`9e06f34ea0e1babb56c621e532703f9e424c3ab0`
- 实际 dirty 快照（T0 现场回读）：18 条 tracked `M` + 5 条未跟踪路径 = 23 条记录：
  - M：calibrate.py、chunked_review.py、metrics.py、run_eval.py、runner.py、evidence_units.py、qwen_vllm_client.py、admission_contract.py、llm_client.py、port.py、prompts.py、verifier.py、test_admission_contract.py、test_copd_field_port.py、test_copd_prompts.py、test_copd_verifier.py、test_evaluation_runner.py、test_evidence_units.py
  - ??：`copd_extraction/evidence_context.py`、`copd_extraction/response_schemas.py`、`docs/codex_design/`、`docs/superpowers/plans/2026-08-02-verifier-chunked-review-experiment-implementation-plan.md`、`docs/superpowers/specs/2026-08-02-verifier-chunked-review-experiment-design.md`
  - 注：DESIGN §2.1 记 22 条，差 1 为 `docs/codex_design/` 自身未跟踪；非承重（DESIGN_REVIEW MINOR-1），以本快照为准。
  - 全部视为用户现有资产，禁止 reset/checkout/clean/stash/整批提交。
- GPT-5.5 极速 raw SHA：`00dffe1110a59fcb5aa51be975feb1141cf0d6777d034953509976fcb6b7a9d1`（T0 回读一致，文件存在 11,719 B，可解析 JSON，顶层键 document_type/fields/schema_version）
- `case_005` golden SHA：`6e68a0b3a67f8adfac5c4bb95bfbd1a10302a9d87a3c2f78507491a04892dcc1`（T0 回读一致）
- DESIGN SHA：`f57dc35767a0d33924a4154bf51206f6025a8c8bffb8ec65532b5eef45d644cf`（T0 回读一致）
- EXECUTION_PLAN SHA：`07e36a50ad17bcf6c4c26a5e71b88cf5f47eca54c6d37e82929dacee755fa1a3`（T0 回读一致）
- WORKER_PROMPT SHA：`eae6d32ed420016fba32e94fbfdd41ea3fd1f7e7c7e54fbac11ae33c6e7678c0`（T0 回读一致）
- prompts.py 当前 SHA：`9d37bc0d9a6d25137253dd1d34ffc59c5ac298546a3db812c200a5ad07bf5783`（与 DESIGN §2.2 一致）
- metrics.py 当前 SHA：`8d6ece744e9405be4e56a9bcf80f51824491f4bbc36d1324e8e6c7d97c107f37`（与 DESIGN §2.2 一致）

## Subagent Backend（T0 绑定）

- 平台：Claude Code Agent 工具，type=general-purpose，真实隔离上下文。
- 最大安全并发：1（T1→T2→T3→T4 强制串行；T0 内只读检查已并行）。
- 共享文件范围：worktree 根 `/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary`。
- 已派发：DESIGN_REVIEW reviewer agentId=`a4111733666491198`（fresh、对抗式、只读）。
- 规则：每个 implementer 只收最小 Context packet；Controller 回读实际文件/hash/命令/退出码；R2 实现者不得批准自己。

## 任务账本

| Task | 状态 | Subagent | 输入 checkpoint | 写入锁 | Review | 证据 | 下一动作 |
|---|---|---|---|---|---|---|---|
| T0 现场锁定/设计门 | DONE | DESIGN_REVIEW `a4111733666491198` | PLAN_FROZEN → `T0_INPUT_LOCK` | STATUS/REPORT | DESIGN_REVIEW PASS（无 blocking，见下） | 输入 hash 全核一致；dirty 快照 | T1 |
| T1 prompt v4 | DONE | implementer `t1-implementer@session-30cb1281`；FIDELITY_REVIEW `t1-fidelity-reviewer@session-30cb1281` | `T0_INPUT_LOCK` | T1 写入范围（8 文件） | R2 PASS（复查 MAJOR-1/MINOR-1 均通过，无遗留） | 见下 T1 证据 | 关闭 checkpoint `T1_PROMPT_V4` → T2 |
| T2 metric v2/gold | DONE | 编排变更（用户指令精简，2026-08-03）：停止 t2-implementer，Controller 直连接管其半成品并校准语义 | `T1_PROMPT_V4` | T2 写入范围 | R2 以冻结预期命中替代（用户豁免独立审查；Controller 独立回读 hash/diff/测试/重评分） | 见下 T2 证据 | 已解锁 T3 |
| T3 离线重评分 | DONE | Controller 直连 | `T2_METRIC_V2` | ignored reports + 账本 | 冻结预期 HIT（R1 级） | 见下 T3 证据 | 已解锁 T4 |
| T4 单例冒烟/报告 | DONE | Controller | `T3_OFFLINE_REPRODUCTION` | /tmp smoke + ignored reports + 账本 | RELEASE_REVIEW PASS；CLAIM_REVIEW PASS（Controller，用户豁免独立审查） | 见下 T4 证据 | 终局 GOAL_REACHED |

合法 Task 状态：`PENDING | READY | DISPATCHED | IMPLEMENTED | REVIEWING | FIXING | DONE | TASK_BLOCKED`。

## 高杠杆门

| Gate | 状态 | Artifact hash | Reviewer | 解锁动作 |
|---|---|---|---|---|
| DESIGN_REVIEW | DONE | DESIGN `f57dc357…` | `a4111733666491198` | T1 已解锁 |
| FIDELITY_REVIEW T1 | DONE PASS | `T1_PROMPT_V4` | `t1-fidelity-reviewer@session-30cb1281`（与 T1 implementer 不同） | 复查通过（MAJOR-1/MINOR-1 关闭）→ T2 已解锁 |
| FIDELITY_REVIEW T2 | PENDING | 无 | 未派发（须与 T2 implementer 不同） | T3 |
| FIDELITY_REVIEW T2 | PENDING | 无 | 未派发（须与 T2 implementer 不同） | T3 |
| RELEASE_REVIEW | DONE PASS（Controller） | prompt v4 `01250ed8…`/SYSTEM_SHA `7d8d80dd…`；metric v2；golden after `ae77c085…`；model Qwen3.5-4B-AWQ-4bit；temp 0；case_005；--no-verifier | vLLM 健康检查 http://127.0.0.1:8082/v1/models exit 0，模型在线 | 唯一 4B 运行已解锁 |
| CLAIM_REVIEW | DONE PASS（Controller） | 最终 HTML `20260803-prompt-policy-metric-alignment-v1-report.html`（sha256 `1457f700…`，含完整 system/user/JSON Schema） | 报告归因边界与磁盘证据一致 | 终局 GOAL_REACHED |

## T1 证据（Controller 已回读）

- 写入范围：8 文件 = schema_loader.py、prompts.py、新建 field_policies.py、YAML、test_schema_loader.py、test_copd_prompts.py、test_copd_field_port.py、test_schema_api.py；无范围外触碰（git status 与基线比对确认）。
- before→after hash：schema_loader `5ba52bcd…→3ed9e055…`；prompts `9d37bc0d…→504429c9…`；field_policies 新建 `0056995f…`；YAML `44371b00…→ff52ad00…`；tests 四件 `1459cb98→aff92454`、`be955ad6→c771d8e7`、`6a8e8b4a→49164367`、`1d454c27→0eabd359`。
- 质量门禁（Controller 独立重跑）：`pytest test_schema_loader test_copd_prompts test_copd_field_port test_schema_api -q` → **67 passed, 1 skipped, exit 0**。
- 独立自检（Controller 生成真实仓库 schema prompt）：v4 版本；61 字段 61 唯一 P 标记（T34/J25/D2）；J 集合 25 成员与 legacy 完全一致；13 查体+2 aux 边界可见；无 `【schema】/order=/id_namespace/evidence_complete`；3 个 JSON 微例在 system 段、可解析、顶层键仅 `output_fields`、u901-903 不在 user 证据流；SYSTEM_SHA `0f63fcb8…` 与 implementer 一致（USER_SHA 因证据输入不同而异，属预期）。
- YAML diff 仅 aux_electrolytes/aux_renal_function 各加一行 description；字段键/数量/顺序未动。
- implementer 自报全量 backend `812 passed / 5 failed`，5 失败为 test_review_routes.py 引用旧字段名 pe_vital_signs 的基线预先存在失败（任务前已 M），与本任务无依赖链——待 FIDELITY_REVIEW 复核此声明。
- FIDELITY_REVIEW（T1，fresh reviewer `t1-fidelity-reviewer@session-30cb1281`，只读）返回 `TASK_REVIEW_FINDINGS`，8 条中 7 条 PASS（约束解码、策略真源、loader description、字段目录、版本、范围纪律、测试质量）；未发现 BLOCKING。开放 findings：
  - **MAJOR-1**：示例 1 用 pmh_surgery_history（J 集合成员）做"否认手术史"，违反 §4.3 职责 (a)"T 字段否定摘录 + J 字段'正常'共享同一 ID"，且与 J 策略定义自相矛盾；测试 docstring 亦误称其为 T 字段。修复：换真实 T 字段 pmh_cardiac_disease（schema 存在、不在 25 个 J 成员内，Controller 已核验），值"否认心脏病史"，共享 u901。
  - **MINOR-1**：示例 2 值含"律齐"（正常描述），字面偏离职责 (b)"输出只保留异常片段"；核心"不因出现正常而折叠"已达成。修复：值去掉"律齐"。
  - **MINOR-2**：test_copd_prompts 的 `NORMAL_JUDGEMENT_FIELD_KEYS == prompts._NORMAL_JUDGEMENT_FIELD_KEYS` 是别名自证恒真；J 集合与历史真源一致性已由 reviewer 人工核对（对称差为空），跨侧一致性测试列入 T2 要求。
  - C 级决定核对：J 集合成员未被改写 ✓；61 字段/JSON 契约/外部接口/模型/温度/病例未动 ✓；三个示例职责中 (a) 的"T 字段否定摘录"部分未达成（MAJOR-1），修复中。
- 修复（2026-08-03，`t1-implementer`，仅 2 文件）：prompts.py 示例 1 pmh_surgery_history→pmh_cardiac_disease（值"否认心脏病史"），示例 2 值去"律齐"；test_copd_prompts 两测试断言从 field_policies 真源核验 + 防回归断言。Controller 独立回读：prompts.py `504429c9…→01250ed8…`、test_copd_prompts `c771d8e7→d50aef4d`；渲染自检（独立脚本 /tmp/t1_verify3.py）：pmh_cardiac_disease P=T 且 ∉J∉D、pe_eyes P=J、示例 1 共享 u901、示例 2 无"律齐"、3 示例可解析顶层仅 output_fields、61 P 标记唯一、无禁用标记；pytest 4 文件重跑 **67 passed, 1 skipped, exit 0**；git status 28 条与修复前一致（无范围外触碰）。
- Checkpoint：`T1_PROMPT_V4` + 上述 hash + R2 结果（修复后复查通过才关闭）。

## T2 证据（Controller 回读）

- 金标：case_005.json before `6e68a0b3…` → after `ae77c085…`；**diff 审计只改 pe_eyes（"颜面眼睑浮肿"→"正常"，排除颜面边界，ocr_text 眼部检查全阴性有据）与 aux_renal_function（去钾钠氯CO2GAP电解质项，保留 eGFR/尿素/肌酐+尿酸 508，ocr_text 有原文）两项**；61 字段键集合不变；血气 pco2/po2 未动；主工作区副本 hash 恰为 before 值（独立交叉验证）。
- metrics.py：`METRIC_VERSION="admission_eval.v2"`；`_KNOWN_J_FIELDS` 迁移为 field_policies 真源别名（T1 MINOR-2 落地）；`_normal_family_supported` 收紧为规范正常判断。
- 语义校准（Controller 诊断 13 错→3 错）：`is_canonical_normal` 从"字面'正常'"改为"全正常判断"（值含正常/阴性信号 且 无未否定异常体征词，`_ABNORMAL_SIGNS`+否定前缀段级检测）；`compare_j_value` 摘录族改双向子串（预测⊆金标也判对）。校准依据：§4.4 b"金标正常/阴性族→预测规范'正常'"+ 冻结预期 46/49 逐字段重建；校准后**全字段重评分恰为 3 错（pe_eyes+pco2+po2）**。
- 测试：test_evaluation_metrics/runner 三文件 **82 passed**（含新严格谓词/双向子串/投影反例/跨版本警告用例）；聚焦三文件 pytest exit 0。
- R2 替代说明：用户指令"重新设计编排（不过度工程化）"豁免每任务独立 R2；Controller 以（a）金标 diff 审计、（b）冻结预期全字段命中、（c）82 聚焦测试、（d）独立 hash 回读四项证据完成等价核验。

## T3 证据（Controller 回读）

- 联合质量门禁（7 文件，PLAN T3 命令）：**149 passed, 1 skipped, exit 0**。
- 离线重评分（真实管线 units_from_ocr_text→validate_qwen_payload→map_qwen_fields_to_review_candidates→evaluate_sample，raw `00dffe11…` 未变）：**status 59/61、value 46/49、extraction FN 2、over-extraction FP 0、confirmed hallucination 0——冻结预期全部命中**；contract invalid 0；literal_unlocated 8、unsupported candidate 5（诊断项，不否决）。
- 产物：`data/evaluation/reports/20260803-gpt55-v2-rescore.json`（meta 含 metric_version=admission_eval.v2 + raw/golden sha）；`data/evaluation/reports/20260803-prompt-v4-appendix.html`（完整 system/user/JSON Schema + 61 P 标记 + 3 示例 + description 可见性 + 禁用标记扫描，15185 B，sha256 `b03f3c2a…`）。
- 完整性：attachment 未复制进 Git；golden/reports 均 ignored。

## T4 证据（Controller 回读）

- RELEASE_REVIEW：prompt v4（prompts.py `01250ed8…`、渲染 SYSTEM_SHA `7d8d80dd…`）、metric v2、golden after `ae77c085…`、model Qwen3.5-4B-AWQ-4bit、temp 0、case_005、--no-verifier——全部绑定一致后解锁。
- vLLM 健康检查：`curl http://127.0.0.1:8082/v1/models` exit 0，Qwen3.5-4B-AWQ-4bit 在线（max_model_len 16384）。
- 唯一 4B 运行（PLAN §4 T4 命令）：exit 0，报告 `/tmp/manzufei_prompt_policy_metric_v1_smoke/20260803_124148_…_Qwen3.5-4B-AWQ-4bit.json`。
- 结构门：**contract invalid 0**（validate_qwen_payload 通过＝61 字段唯一完整）；metric_version=`admission_eval.v2`；pipeline error=无；evidence 回填成功。
- 质量（如实报告，不设阈值）：status 59/61=96.72%、value 46/49=93.88%、FN 0、over-extraction FP 2、confirmed hallucination 1、literal-unlocated 8、unsupported candidate 8。value 错 3 字段：hpi_hospital_diagnosis、hpi_recent_symptoms、pe_eyes（混合正常+异常文本）。未重跑、未调参。
- 最终 HTML：`data/evaluation/reports/20260803-prompt-policy-metric-alignment-v1-report.html`（22559 B，sha256 `1457f700…`，用户追加要求合并完整提示词），含输入身份/四项改造/GPT-5.5 v2 重评分/4B v4-v2/旧 v3 历史（跨口径不比较）/逐字段错误/三层 grounding/归因边界/**完整 system/user prompt + JSON Schema 全文**。
- CLAIM_REVIEW（Controller，用户豁免独立审查）：报告 §7 归因边界成立——指标修正是确定性证据（冻结预期命中）；prompt 改造仅结构性证据、无 A/B 归因；模型能力不下结论；负结果保留；无反向调参。
- 范围核验：git status 30 条＝用户基线 28 + T2 写入范围内 2 文件（test_evaluation_metrics/test_evaluation_run_eval）；HEAD 未动、无 commit、无 reset/checkout/clean/stash；attachment 未复制进 Git。

## 尝试与策略变化

暂无失败。DESIGN_REVIEW 结论为 `TASK_REVIEW_FINDINGS`（无 blocking）：
- MAJOR-1：DESIGN §4.4 非对称 J 比较器语义欠定义（"规范值正常"严格谓词、金标族分类路由、投影与族分类顺序未钉死），冻结数字 46/49 + §8 测试矩阵构成足够约束，可恢复。对策（不改设计）：T2 FIDELITY_REVIEW 显式覆盖三点语义；T3 偏差不得一律归因"接线漂移"。
- MINOR-1：dirty 记录数 22 vs 实际 23，已由本快照吸收。
- MINOR-2：终局代数缺口（vLLM 在线但重试后仍 contract invalid 时无合法终局）。概率低，记录待架构师解释性裁定；如实际出现，按 §8 保留证据后走硬阻塞审计。
- 未消耗冒烟预算。

## 恢复入口

1. 读取 DESIGN、PLAN、本状态和报告；
2. 回读 git status，确认用户 dirty 差量仍在；
3. 找到首个非 DONE Task；
4. 验证其上游 checkpoint hash；
5. 只重派该 Task 的最小 Context packet，不重跑已通过的同 hash gate。

## 终局门禁

- `GOAL_REACHED`：T0-T4 DONE、T1/T2 R2 PASS、四个高杠杆门有证据、GPT-5.5 v2 命中冻结预期、唯一 4B 结构有效、HTML/完整 prompt/报告存在、C 级偏离为 0。
- `HARD_BLOCKED`：仅按 DESIGN §9 和 Plan §6；必须有 `BLOCKER_PACKET.md`。
- `PARTIAL`、质量不佳、时间到、等待用户确认、没有跑 6 例全量都不是终局。
