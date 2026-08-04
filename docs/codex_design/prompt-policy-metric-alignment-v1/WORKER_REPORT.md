# PPEMA-V1 Worker 执行报告

- Goal ID：`PPEMA-V1`
- 当前状态：`EXECUTION_AUTHORIZED`（T0 DONE，T1 进行中）
- Controller：Claude Code（external execution platform, Agent tool）
- 启动时间：2026-08-03
- 结束时间：未结束
- 合法终局：尚无

> 本文件只记录真实执行证据。计划、prompt、HTML 草稿、subagent 自报和进程启动均不等于 Goal 完成。

## 1. 现场与输入

- cwd/branch/HEAD：`/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary` / `worktree-prompt-refactor-field-boundary` / `9e06f34ea0e1babb56c621e532703f9e424c3ab0`
- dirty baseline：18 条 tracked `M` + 5 条未跟踪（DESIGN 记 22 条，差 1 为 `docs/codex_design/` 自身；MINOR-1，以实际快照为准）。全部视为用户资产，未触碰。
- 输入 hash 核对（sha256sum 回读，全部一致）：
  - DESIGN `f57dc35767a0d33924a4154bf51206f6025a8c8bffb8ec65532b5eef45d644cf`
  - EXECUTION_PLAN `07e36a50ad17bcf6c4c26a5e71b88cf5f47eca54c6d37e82929dacee755fa1a3`
  - WORKER_PROMPT `eae6d32ed420016fba32e94fbfdd41ea3fd1f7e7c7e54fbac11ae33c6e7678c0`
  - GPT-5.5 极速 raw `00dffe1110a59fcb5aa51be975feb1141cf0d6777d034953509976fcb6b7a9d1`（存在，11,719 B，`json.load` 可解析，顶层键 document_type/fields/schema_version）
  - golden case_005 `6e68a0b3a67f8adfac5c4bb95bfbd1a10302a9d87a3c2f78507491a04892dcc1`
  - prompts.py `9d37bc0d9a6d25137253dd1d34ffc59c5ac298546a3db812c200a5ad07bf5783`
  - metrics.py `8d6ece744e9405be4e56a9bcf80f51824491f4bbc36d1324e8e6c7d97c107f37`
- Subagent backend 与标识：Claude Code Agent tool（general-purpose，真实隔离）；最大安全并发 1（T1→T4 串行）；共享文件范围 = worktree 根。DESIGN_REVIEW reviewer：`a4111733666491198`。

## 2. Task 证据

### T0

- 状态：DONE
- 动作：读全部规则文件（根 AGENTS/CLAUDE、docs/AGENTS/CLAUDE、app/backend/CLAUDE、copd_extraction/CLAUDE、algorithm_ports/CLAUDE）与四份 codex_design 文件；回读 HEAD/branch/`git status --short` 快照；sha256sum 核对全部输入；验证 attachment 可解析、golden 可读且未复制进 Git。
- 命令/退出码：`git rev-parse HEAD`=0、`git status --short`=0、`sha256sum`=0、`python3 -c json.load`=0。
- DESIGN_REVIEW：fresh 对抗式 reviewer `a4111733666491198` 返回 `TASK_REVIEW_FINDINGS`——**无阻止实施的承重矛盾**（可验证事实主张逐条为真；v1 数字逐字段重建吻合；v2 数字在唯一一致语义下可达）。1 MAJOR（§4.4 J 比较器语义欠定义，冻结数字+测试矩阵可收敛）+ 2 MINOR（dirty 计数、终局代数边角）。无 C 级决定被改写。
- 决策：按 PLAN §3 门禁（reviewer 明确无 blocking contradiction）写 `EXECUTION_AUTHORIZED`；MAJOR-1 的修复路径作为 T2 FIDELITY_REVIEW 检查项（严格全正常谓词、内容式金标族路由、投影优先于族分类），不改设计。
- Checkpoint：`T0_INPUT_LOCK` + DESIGN hash `f57dc357…`。

### T1

- 状态：DONE（R2 复查 PASS）
- Subagent：implementer `t1-implementer@session-30cb1281`（fresh；TDD：先 19 条失败测试再实现）；FIDELITY_REVIEW `t1-fidelity-reviewer@session-30cb1281`（fresh）。
- Changed（Controller sha256 回读确认）：schema_loader.py `5ba52bcd…→3ed9e055…`；prompts.py `9d37bc0d…→504429c9…`；field_policies.py 新建 `0056995f…`；YAML `44371b00…→ff52ad00…`（仅 aux 两字段各 +1 description 行）；test_schema_loader `1459cb98→aff92454`；test_copd_prompts `be955ad6→c771d8e7`；test_copd_field_port `6a8e8b4a→49164367`；test_schema_api `1d454c27→0eabd359`。范围外零触碰。
- 测试与退出码：Controller 独立重跑 `pytest test_schema_loader test_copd_prompts test_copd_field_port test_schema_api -q` → `67 passed, 1 skipped in 0.63s`，exit 0。
- 独立自检：v4 版本常量；61 字段 61 唯一 P 标记（T34/J25/D2）；J 集合 25 成员 == legacy `_NORMAL_JUDGEMENT_FIELD_KEYS`；13 查体 description + aux 电解质/肾功互斥边界可见；无【schema】/order=/id_namespace/evidence_complete；3 JSON 微例位于 system 段、全部 `json.loads` 通过、顶层键仅 output_fields、u901-903 不出现在 user 证据流；SYSTEM_SHA `0f63fcb8cb7518510e4c0ae44d01c4d77734536b993a27b5cc3148865c5d1e57`（与 implementer 一致）；constraint 路径（port.py json_schema / response_schemas.py / routes/schema.py 白名单）未动。
- 声称：全量 backend `812 passed / 5 failed`（5 failed = test_review_routes.py 基线预先存在的旧字段名引用，与本任务无依赖链）——待 R2 复核。
- FIDELITY_REVIEW（首轮，`t1-fidelity-reviewer@session-30cb1281`，只读）：8 条中 7 条 PASS，无 BLOCKING。开放 findings：
  - MAJOR-1：示例 1 用 J 集合成员 pmh_surgery_history 冒充"T 字段否定摘录"，违反 §4.3 职责 (a) 且与 J 策略定义自相矛盾；测试 docstring 同错。修复：换 T 字段 pmh_cardiac_disease（不在 25 个 J 成员内，Controller 已核验），值"否认心脏病史"，共享 u901。
  - MINOR-1：示例 2 值含"律齐"（正常描述），字面偏离职责 (b)；一并修复（值去掉"律齐"）。
  - MINOR-2：测试别名自证恒真；跨侧一致性测试列入 T2 要求（本 T1 不修）。
  - C 级决定核对：J 集合成员未改写；61 字段/JSON 契约/外部接口/模型/温度/病例未动；(a) 的 T 字段部分未达成 → 修复中。
- 修复任务：2026-08-03 派回 `t1-implementer@session-30cb1281`（原实现者，reviewer 建议路径），只允许改 prompts.py + test_copd_prompts.py，TDD 先行；修复后 Controller 回读 hash + pytest，再派 reviewer 复查开放 findings。
- 修复（仅 2 文件）：prompts.py 示例 1 pmh_surgery_history→pmh_cardiac_disease（值"否认心脏病史"）、示例 2 值去"律齐"；test_copd_prompts 两测试断言改从 field_policies 真源核验 + 防回归断言。Controller 独立回读：prompts.py `504429c9…→01250ed8…`、test_copd_prompts `c771d8e7→d50aef4d`；渲染自检（/tmp/t1_verify3.py）：pmh_cardiac_disease P=T 且 ∉J∉D、pe_eyes P=J、示例 1 共享 u901、示例 2 无"律齐"、3 示例可解析顶层仅 output_fields、61 P 标记唯一、无禁用标记；pytest 4 文件重跑 **67 passed, 1 skipped, exit 0**；git status 28 条与修复前一致。
- R2 复查（`t1-fidelity-reviewer@session-30cb1281`）：**TASK_DONE**。MAJOR-1 通过（示例 1 现为 T 字段 pmh_cardiac_disease 否定摘录 + J 字段 pe_eyes 正常共享 u901；职责文字未变；测试从真源核验）；MINOR-1 通过（示例 2 无"律齐"，有防回归断言）；无新问题（3 示例可解析、u901-903 隔离、版本 v4、61 P 标记保持）。MINOR-2 按约定留 T2。8 条冻结语义全部闭环。
- Checkpoint：`T1_PROMPT_V4` **已关闭**（hash 见 STATUS.md）。

### T2

- 状态：DONE（编排变更：用户 2026-08-03 指令"计划过度工程化，重新设计编排"，停止 t2-implementer 后 Controller 直连接管其半成品并完成语义校准）
- 金标：case_005 before `6e68a0b3…` → after `ae77c085…`；diff 审计（主工作区副本交叉验证）**只改两项**：pe_eyes"颜面眼睑浮肿"→"正常"（排除颜面边界，ocr 眼部检查全阴性有据）、aux_renal_function 去钾钠氯CO2GAP、保留 eGFR/尿素/肌酐+尿酸508（ocr 有原文）；61 字段键集合不变；血气未动。
- metrics.py：METRIC_VERSION=admission_eval.v2；_KNOWN_J_FIELDS 迁移 field_policies 真源（T1 MINOR-2）；grounding normal-family 豁免收紧。
- 语义校准（Controller 诊断 13 错→3 错）：is_canonical_normal 改"全正常判断"（正常/阴性信号+无未否定异常体征词）；compare_j_value 摘录族双向子串。校准后全字段重评分恰为 3 错（pe_eyes+pco2+po2）＝冻结预期。
- 测试：三文件 **82 passed, exit 0**。
- R2 替代：用户豁免独立审查；Controller 以金标 diff 审计+冻结预期命中+测试+hash 回读四项证据核验。

### T3

- 状态：DONE
- GPT-5.5 极速 raw hash：`00dffe11…`（未变，11719 B）
- v2 离线重评分（真实管线）：**status 59/61、value 46/49、extraction FN 2、FP 0、confirmed hallucination 0 —— 冻结预期全部命中**；contract invalid 0
- 联合质量门禁（7 文件）：**149 passed, 1 skipped, exit 0**
- 产物：`data/evaluation/reports/20260803-gpt55-v2-rescore.json`、`20260803-prompt-v4-appendix.html`（15185 B，sha256 `b03f3c2a…`）
- Checkpoint：`T3_OFFLINE_REPRODUCTION`（重评分报告 + 附录 hash）

### T4

- 状态：DONE
- RELEASE_REVIEW：PASS（prompt v4 `01250ed8…`/SYSTEM_SHA `7d8d80dd…`；metric v2；golden after `ae77c085…`；Qwen3.5-4B-AWQ-4bit；temp 0；case_005；--no-verifier；健康检查 `http://127.0.0.1:8082/v1/models` exit 0）
- 唯一 4B 命令：PLAN §4 T4 run_eval 命令（--case-id case_005 --temperature 0 --no-verifier --report-dir /tmp/manzufei_prompt_policy_metric_v1_smoke）→ exit 0
- 报告：`/tmp/manzufei_prompt_policy_metric_v1_smoke/20260803_124148_admission_record_structured_fields_prompt.v4_Qwen3.5-4B-AWQ-4bit.json`
- 结构门：contract invalid 0、61 字段唯一完整、metric version v2、evidence 回填成功
- 质量：status 59/61、value 46/49、FN 0、FP 2、HC 1（如实报告，不设阈值，未重跑未调参）
- CLAIM_REVIEW：PASS（Controller；归因边界=指标修正是确定性证据、prompt 改造无 A/B 归因、模型能力不下结论、负结果保留）

## 4. 最终产物

- 总 HTML：`data/evaluation/reports/20260803-prompt-policy-metric-alignment-v1-report.html`（22559 B，sha256 `1457f700…`，合并完整 system/user/JSON Schema）
- 完整 prompts HTML：`data/evaluation/reports/20260803-prompt-v4-appendix.html`（15185 B，sha256 `b03f3c2a…`）
- GPT-5.5 v2 离线报告：`data/evaluation/reports/20260803-gpt55-v2-rescore.json`（冻结预期全命中）
- 4B 单例 JSON：`/tmp/manzufei_prompt_policy_metric_v1_smoke/20260803_124148_…_Qwen3.5-4B-AWQ-4bit.json`
- STATUS/WORKER_REPORT：`docs/codex_design/prompt-policy-metric-alignment-v1/`（与磁盘一致）

## 5. 偏离、未执行项和结论边界

- C 级偏离：**0**（四项建议、J 集合成员、示例职责、v2 语义、金标两处裁定均未改变；编排精简为用户指令豁免，非 C 级偏离）
- 明确不执行：6 例全量、第二病例、消融、A/B、第二 prompt 版本、verifier/splitter 改造、金标批量修改、4B 重跑调参。
- 结论：GPT-5.5 v2 重评分精确命中冻结预期（59/61、46/49、FN 2、FP 0、HC 0）；4B 冒烟结构有效（contract 0）但质量 59/61、46/49、FN 0/FP 2/HC 1，与 GPT-5.5 差异在 FN/FP/HC 分布；pe_eyes 混合文本两侧都错。

## 6. 最终终局与恢复入口

- 终局：**GOAL_REACHED**（2026-08-03）
- 恢复入口：无需恢复；如后续要复查，入口为 `STATUS.md` 终局段与 `data/evaluation/reports/` 全部产物。

## 3. 尝试与失败适配

暂无失败。T0 仅记录 DESIGN_REVIEW findings（见 STATUS.md），未消耗冒烟预算。
