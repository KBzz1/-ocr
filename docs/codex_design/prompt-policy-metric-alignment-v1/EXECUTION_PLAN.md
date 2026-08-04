# 抽取提示词策略映射与评估语义对齐：外部 Controller 执行计划

## 0. Goal Lock

- Goal ID：`PPEMA-V1`
- Goal：实现 `DESIGN.md` 冻结的四项改造，完成 GPT-5.5 极速离线同版本重评分和一次 `case_005` 4B 冒烟，并交付完整提示词与 HTML 报告。
- Completion evidence：T0-T4 全部 DONE、T1/T2 R2 规格审查通过、聚焦测试通过、v2 重评分命中冻结预期、一次结构有效 4B 报告、完整 prompt HTML、状态和报告一致。
- Controller terminal states：`GOAL_REACHED | HARD_BLOCKED`
- Task return states：`TASK_DONE | TASK_BLOCKED | TASK_REVIEW_FINDINGS`
- Design authority：`DESIGN.md`
- Status ledger：`STATUS.md`
- Full report：`WORKER_REPORT.md`

`PARTIAL`、进程启动、时间到、等待确认、质量低于预期都不是合法终局。质量不佳时如实完成报告并停止，不能用它授权调参。

## 1. Subagent Backend 与持续执行

- 外部 Controller 默认具备真实 subagent backend；直接绑定平台接口并记录实际标识，不重复探测。
- 每个承重任务使用 fresh implementer；T1、T2 必须由与 implementer 不同的 fresh 规格 reviewer 做 R2 忠实性审查。
- 最大并发由平台记录，但 T1→T2→T3→T4 必须串行；只有 T0 内互不写文件的只读检查可并行。
- subagent 持续失败时记录 `SUBAGENT_RUNTIME_UNAVAILABLE`，可降级做非承重机械任务；不能在同一上下文伪造 R2 独立审查。
- Controller 按 `Select → Packet → Dispatch → Inspect → Review → Repair → Persist → Continue` 循环，回读实际 diff、文件、日志和退出码后才关闭 Task。

## 2. 全局冻结项

- 必读：根/目标目录规则、`DESIGN.md`、当前 schema/prompt/metrics 实现与指定测试。
- dirty worktree 22 条状态是输入；禁止 reset、checkout、clean、stash、批量格式化、整批提交或触碰无关差量。
- 只实现四项建议；不改证据切分、复核 prompt、复核分组、前端、导出、状态、业务字段和 JSON 响应契约。
- 只运行 `case_005`；不运行 6 例全量、第二病例、消融、A/B 或第二 prompt 版本。
- 合成测试先于实现；真实 LLM 不得用于单测。

## 3. 预检

Controller 启动后必须：

1. 读取 `AGENTS.md`、`CLAUDE.md`、`docs/AGENTS.md`、`app/backend/CLAUDE.md`、`app/backend/services/copd_extraction/CLAUDE.md` 和本目录全部文件；
2. 核对 cwd、branch、HEAD 和 `git status --short`，把实际 dirty 基线写进 `STATUS.md`；
3. 核对 `DESIGN.md` 输入 hash。非重叠漂移可更新状态；承重文件语义已变且与冻结设计冲突时停止相关分支；
4. 验证 attachment 与 `case_005` 可读但不复制进 Git；
5. 绑定 subagent backend；
6. 派 fresh adversarial reviewer 执行一次 `DESIGN_REVIEW`，只回答冻结设计是否存在阻止实施的承重矛盾。Reviewer 不得改方法。

通过后在 `STATUS.md` 写 `EXECUTION_AUTHORIZED`，再派 T1。

## 4. Task Graph

### Task T0：现场锁定与 DESIGN_REVIEW

- Depends on：none
- Goal：锁定实际输入和 dirty 边界，并取得实现授权。
- Context packet：
  - Rules：根/文档/后端/COPD extraction 的 AGENTS/CLAUDE；
  - Files/sections：`DESIGN.md`、`git status`、DESIGN §2/§4/§5/§9；
  - Forbidden context：归档、大日志、无关前端与部署代码。
- Input identity：HEAD `9e06f34ea0e1babb56c621e532703f9e424c3ab0` 加实际 dirty 清单。
- Write scope：仅 `STATUS.md`、`WORKER_REPORT.md`。
- Forbidden changes：任何产品代码、方法、金标或 prompt。
- Subagent execution：Controller 只读预检 + fresh DESIGN_REVIEW reviewer。
- Outputs：输入清单、hash 核对、reviewer 标识、`EXECUTION_AUTHORIZED`。
- Fidelity gate：reviewer 明确无 blocking contradiction；C 级决定未被改写。
- Quality gate：attachment、golden、关键代码均可读；dirty 状态有快照。
- Review tier：R2 decision gate。
- Checkpoint：`T0_INPUT_LOCK` + DESIGN hash。
- Failure alternatives：重新解析非重叠路径；若承重冲突需要 C 级变化，写阻塞包。
- Downstream：T1。

### Task T1：运行时字段策略、边界与三个 JSON 微例

- Depends on：T0 + `EXECUTION_AUTHORIZED`
- Goal：生成 v4 prompt，使模型逐字段看到 `P=T/J/D` 和真实边界，同时保持约束解码与外部契约不变。
- Context packet：
  - Rules：COPD extraction 目录规则；
  - Files/symbols：
    - `app/backend/services/schema_loader.py::load_schema`
    - `app/config/schemas/admission_record_structured_fields.v1.yaml`
    - `app/backend/services/copd_extraction/prompts.py::_field_line,_render_field_catalog,build_admission_structured_fields_messages`
    - `app/backend/services/copd_extraction/response_schemas.py::build_extraction_json_schema`
    - `app/backend/services/copd_extraction/port.py::COPDAdmissionQwenFieldPort.extract`
    - `app/backend/routes/schema.py::get_current_schema`
    - 对应 schema/prompt/field-port/schema-api 测试；
  - Forbidden context：verifier prompt、evidence splitter、前端实现、历史归档。
- Input identity：DESIGN §4.1-§4.3 与 T0 hash。
- Write scope：
  - `app/backend/services/schema_loader.py`
  - `app/config/schemas/admission_record_structured_fields.v1.yaml`
  - `app/backend/services/copd_extraction/prompts.py`
  - 新建 `app/backend/services/copd_extraction/field_policies.py`，或 DESIGN 允许的无循环等价内部路径
  - `app/backend/tests/test_schema_loader.py`
  - `app/backend/tests/test_copd_prompts.py`
  - 必要的 `test_copd_field_port.py`、`test_schema_api.py` 局部断言。
- Forbidden changes：J 集合成员、response JSON shape、字段数量/顺序、public API keys、verifier/evidence code。
- Subagent execution：fresh implementer；完成后 fresh 规格 reviewer。
- Actions：
  1. 先写失败测试：description 透传/非法类型拒绝、61 个唯一 policy 标记、三个示例 JSON 可解析、辅助检查例外和两类辅助字段边界可见、public schema API 未新增键、约束 schema 仍透传；
  2. 实现共享内部 policy 真源，成员与当前集合精确一致；
  3. loader 保留 description；字段目录渲染 `P=T/J/D`；
  4. 加入三个冻结 JSON 微例并删除当前三条 prose 示例；
  5. prompt version 升 v4；
  6. 生成实际仓库 schema prompt，检查无 `【schema】`、`order=`、`id_namespace`、`evidence_complete`。
- Outputs：v4 prompt 实现、测试、实际 prompt 文本 hash。
- Fidelity gate：fresh reviewer 对照 DESIGN §4.1-§4.3 和真实 diff，确认四项具体语义、无外部契约漂移。
- Quality gate：
  ```bash
  /home/kbzz1/miniconda3/bin/conda run -n manzufei_ocr python -m pytest \
    app/backend/tests/test_schema_loader.py \
    app/backend/tests/test_copd_prompts.py \
    app/backend/tests/test_copd_field_port.py \
    app/backend/tests/test_schema_api.py -q
  ```
  全部通过；实际 field keys 数量仍为 61。
- Review tier：R2。
- Checkpoint：`T1_PROMPT_V4` + changed-file hashes + reviewer PASS。
- Failure alternatives：循环依赖时移动共享 registry；public exposure 时保留 route allowlist 或内部化 metadata，不能删边界。
- Downstream：T2。

### Task T2：`admission_eval.v2` 与受控金标修正

- Depends on：T1 + `T1_PROMPT_V4`
- Goal：实现冻结的同版本评估语义，只修改 `case_005` 两个已裁定金标。
- Context packet：
  - Rules：后端与 evaluation 相关规则；
  - Files/symbols：
    - T1 的共享 field policy registry
    - `app/backend/evaluation/metrics.py::compare_value,j_judgement_normalize,grounding_result`
    - `app/backend/evaluation/runner.py::evaluate_sample,build_report`
    - `app/backend/evaluation/run_eval.py::_print_compare,main`
    - `data/evaluation/golden/case_005.json`
    - evaluation metrics/runner/run_eval tests；
  - Forbidden context：其他 golden、复核 calibration、生产 verifier。
- Input identity：DESIGN §4.4；golden before hash `6e68a0...892dcc1`。
- Write scope：
  - `app/backend/evaluation/metrics.py`
  - `app/backend/evaluation/runner.py`
  - `app/backend/evaluation/run_eval.py`
  - `app/backend/tests/test_evaluation_metrics.py`
  - `app/backend/tests/test_evaluation_runner.py`
  - `app/backend/tests/test_evaluation_run_eval.py`
  - ignored `data/evaluation/golden/case_005.json` 的指定两项。
- Forbidden changes：其他病例、其他 case_005 字段、status 定义、grounding 三层命名、confirmed hallucination 定义、生产字段结果。
- Subagent execution：fresh implementer；完成后 fresh 规格 reviewer。
- Actions：
  1. 先写合成失败测试，覆盖 abnormal+normal J、normal+mixed J、canonical normal、grounding normal 豁免、stool/urine 投影及非目标字段反例、跨 metric version 拒绝比较；
  2. 引入精确版本 `admission_eval.v2`；
  3. 实现 DESIGN §4.4 的非对称 J comparator 和受控投影；
  4. 修改指定两项 golden，验证 JSON 和 61 字段完整；
  5. diff 审计必须证明没有第三个 golden 字段变化。
- Outputs：v2 metrics、测试、golden before/after hash 和结构化 diff。
- Fidelity gate：fresh reviewer 只看冻结语义、实际 diff 和测试；重点拒绝“含正常词就归一正常”、跨版本直接比较、批量改金标。
- Quality gate：
  ```bash
  /home/kbzz1/miniconda3/bin/conda run -n manzufei_ocr python -m pytest \
    app/backend/tests/test_evaluation_metrics.py \
    app/backend/tests/test_evaluation_runner.py \
    app/backend/tests/test_evaluation_run_eval.py -q
  ```
  全部通过；`case_005` 仍有 61 个唯一字段且只两项 value 变化。
- Review tier：R2。
- Checkpoint：`T2_METRIC_V2` + golden after hash + reviewer PASS。
- Failure alternatives：将 comparator 拆为字段路由 helper；不得用通用医学词典或 LLM judge 替代确定性语义。
- Downstream：T3。

### Task T3：集成回归、完整 prompt 和 GPT-5.5 极速离线重评分

- Depends on：T1 + T2 checkpoints。
- Goal：证明实现接线完整，并在不发起模型请求的情况下按 v2 重评分用户提供的高模型原始 JSON。
- Context packet：T1/T2 输出、attachment、case_005、admission contract/evidence mapping、报告生成入口；禁止读取无关 calibration 长日志。
- Input identity：GPT-5.5 原始 JSON SHA `00dffe...b6b7a9d1`；T1/T2 hashes。
- Write scope：`data/evaluation/reports/` ignored 产物、`STATUS.md`、`WORKER_REPORT.md`；除修复 T1/T2 finding 外不改代码。
- Forbidden changes：不得人工修正 GPT 输出、不得调用 GPT 或 4B、不得改 gold 以追预期值。
- Subagent execution：fresh implementer 可生成确定性报告；Controller 独立回读并运行门禁。
- Actions：
  1. 跑 T1+T2 聚焦测试联合命令；
  2. 用真实 schema、`units_from_ocr_text`、`validate_qwen_payload`、`map_qwen_fields_to_review_candidates`、`evaluate_sample` 离线评分原始 JSON；
  3. 生成 v4 完整 system/user/JSON Schema HTML 附录；
  4. 记录提示词字符数、61 policy marker、3 JSON 示例、description 可见性和禁用标记扫描。
- Outputs：离线评分 JSON/HTML、完整 prompts HTML、聚焦测试日志摘要。
- Fidelity gate：重评分精确为 status 59/61、value 46/49、FN 2、FP 0、confirmed hallucination 0；原始 attachment hash 不变。
- Quality gate：
  ```bash
  /home/kbzz1/miniconda3/bin/conda run -n manzufei_ocr python -m pytest \
    app/backend/tests/test_schema_loader.py \
    app/backend/tests/test_copd_prompts.py \
    app/backend/tests/test_copd_field_port.py \
    app/backend/tests/test_schema_api.py \
    app/backend/tests/test_evaluation_metrics.py \
    app/backend/tests/test_evaluation_runner.py \
    app/backend/tests/test_evaluation_run_eval.py -q
  ```
  全部通过；HTML 是 UTF-8 且可打开。
- Review tier：R1；若冻结预期不符，升级为 T1/T2 R2 finding，不得放宽预期。
- Checkpoint：`T3_OFFLINE_REPRODUCTION` + report hashes。
- Failure alternatives：attachment 不可读时按原 hash 搜索同一文件；不能从 HTML 或叙述重建原始答案。
- Downstream：T4。

### Task T4：RELEASE_REVIEW、唯一 4B 冒烟与 CLAIM_REVIEW

- Depends on：T3 + `T3_OFFLINE_REPRODUCTION`
- Goal：只运行一次 `case_005` 抽取并交付结论边界清楚的 HTML 总报告。
- Context packet：冻结 DESIGN、T1/T2/T3 hashes、当前 vLLM 配置、case_005、旧 v3 aggregate 与高模型 v2 重评分；禁止完整聊天和其他病例。
- Input identity：prompt v4 hash、metric v2、golden after hash、model `Qwen3.5-4B-AWQ-4bit`、temperature 0、case `case_005`、`--no-verifier`。
- Write scope：`/tmp/manzufei_prompt_policy_metric_v1_smoke/`、ignored `data/evaluation/reports/`、`STATUS.md`、`WORKER_REPORT.md`。
- Forbidden changes：运行解封后不得改 prompt、metric、gold、model 或 case；不得跑全量/第二病例/消融。
- Subagent execution：Controller 做 RELEASE_REVIEW；运行结束后 fresh CLAIM_REVIEW reviewer。
- Actions：
  1. `RELEASE_REVIEW` 绑定上述 identity、健康检查、预算和输出目录；
  2. 健康检查 `http://127.0.0.1:8082/v1/models`；
  3. 执行：
     ```bash
     /home/kbzz1/miniconda3/bin/conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval \
       --golden-dir data/evaluation/golden \
       --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
       --base-url http://127.0.0.1:8082/v1 \
       --model Qwen3.5-4B-AWQ-4bit \
       --case-id case_005 \
       --temperature 0 \
       --no-verifier \
       --report-dir /tmp/manzufei_prompt_policy_metric_v1_smoke
     ```
  4. 验证 contract invalid=0、61 字段、evidence IDs 真实、metric version v2；
  5. 生成 `data/evaluation/reports/20260803-prompt-policy-metric-alignment-v1-report.html`，包含完整输入身份、旧 4B 历史值（跨版本明确不可正式比较）、GPT-5.5 v2、4B v4-v2、逐字段错误、三层 grounding 和负结果；
  6. fresh CLAIM_REVIEW 只判断证据最多支持什么，不允许反向调参。
- Outputs：唯一 smoke JSON、最终 HTML、claim review、最终状态。
- Fidelity gate：运行 identity 与 release hash 一致；没有第二病例、全量或 prompt v5。
- Quality gate：结构门必须通过。status/value/FN/FP/confirmed hallucination 只报告，不设成功阈值；结果差不等于 Task 失败。
- Review tier：RELEASE_REVIEW + CLAIM_REVIEW。
- Checkpoint：`T4_SINGLE_SMOKE` + run/report hashes。
- Failure alternatives：
  - 首次仅 transport、contract 或 evidence 结构失败：修复确定性结构问题后可对同一 case 重试一次，必须保留首次日志；
  - 首次结构有效但质量低：禁止重跑或改 prompt，直接报告；
  - vLLM 持续不可用：完成硬阻塞审计。
- Downstream：最终总门禁。

## 5. 高杠杆审核路由

- `DESIGN_REVIEW`：T0 required；解锁 `EXECUTION_AUTHORIZED`。
- `FIDELITY_REVIEW`：T1、T2 required；实现者与 fresh 规格 reviewer 不得相同。
- `RELEASE_REVIEW`：T4 运行前 required；绑定 prompt/metric/gold/model/case/command hash。
- `CLAIM_REVIEW`：T4 报告发布前 required；不得把 metric 修正、prompt 改造和模型能力混为同一因果结论。
- `QUALITY_REVIEW`：N/A；自动测试覆盖局部逻辑，本轮无新增并发/安全/恢复机制。

同一 artifact hash 只审一次；修复后只复查开放 findings 和受影响测试。

## 6. 失败适配与 HARD_BLOCKED 审计

失败必须增加证据或改变策略：定位具体 failing test/字段 → 局部修复 → 等价 helper 拆分 → 隔离无关 dirty change → 一次结构重试 → 硬阻塞审计。禁止原样重复。

只有承重条件、合同内安全替代已穷尽且继续需要新权限/外部变化/C 级决定时，Controller 才能写 `HARD_BLOCKED` 和 `BLOCKER_PACKET.md`。Task blocked 不自动等于 Goal blocked；先完成不受影响的 ready task。

## 7. 最终总门禁

- [ ] T0-T4 全部 DONE；
- [ ] T1/T2 R2 规格审查完成；
- [ ] DESIGN_REVIEW、FIDELITY_REVIEW、RELEASE_REVIEW、CLAIM_REVIEW 均有真实独立证据；
- [ ] prompt v4、metric v2、gold/model/run identity 可回读；
- [ ] GPT-5.5 极速 v2 重评分命中冻结预期；
- [ ] 唯一 `case_005` 4B 运行结构有效，或形成合法硬阻塞；
- [ ] 未运行 6 例全量、第二病例、消融或质量重试；
- [ ] HTML 完整提示词和总报告存在；
- [ ] 未经批准的 C 级偏离为零；
- [ ] `STATUS.md` 与磁盘一致；
- [ ] Goal 完成证据全部成立。

满足全部门禁才写 `GOAL_REACHED`；否则只能持续执行或在严格条件下写 `HARD_BLOCKED`。

