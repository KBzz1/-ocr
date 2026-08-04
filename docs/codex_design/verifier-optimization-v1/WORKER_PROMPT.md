# Worker 启动提示词：字段复核器优化 v1

你是本任务的主执行 Worker。请直接在指定 worktree 中完成复核器优化、聚焦测试和唯一单例冒烟。你可以自主阅读仓库、规划、编码、测试和修复；不要重新制作多层计划、五件套文档或固定 reviewer/fixer 流程。

## 项目与目标

- 项目根：`/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary`
- 最终目标：在不改变 61 个业务字段、外部字段结果、审核状态、前端和导出契约的前提下，优化当前 found 字段复核器，提升真正问题的发现能力，同时控制误报和证据装配类假警报。

本阶段只做复核器。不实现 LLM-as-Judge，不建立 rubric，不扩展为通用评价平台，也不增加 not_found omission audit。抽取漏项检测留到后续独立阶段。

## 已核实现场

- 当前分支：`worktree-prompt-refactor-field-boundary`，HEAD `9e06f34`，存在大量本轮未提交修改；全部视为用户资产，禁止 reset、checkout、clean、stash、覆盖或丢弃无关差量。
- 上一阶段报告：
  - `data/evaluation/reports/20260803-prompt-policy-metric-alignment-v1-report.html`
  - `data/evaluation/reports/20260803-prompt-v4-appendix.html`
  - `data/evaluation/reports/20260803-gpt55-v2-rescore.json`
- 唯一 4B 冒烟当时使用 `--no-verifier`，不能据此评价复核器。
- 当前实现：
  - `app/backend/services/copd_extraction/verifier.py`
  - `app/backend/services/copd_extraction/prompts.py::build_verification_messages`
  - `app/backend/services/copd_extraction/evidence_context.py`
  - `app/backend/services/copd_extraction/response_schemas.py`
  - `app/backend/evaluation/calibrate.py`
- 当前复核器只送审 `status=found` 且 value 非空字段。本阶段保持这个范围，不把提取 FN 与复核 FN 混为一谈。
- 当前请求已有：原始 `uXXX`、cited unit 前后邻接上下文、cited-ID 请求前检查、evidence-first、claims JSON、四项 checks、JSON Schema 约束解码和 section 分组。
- 当前复核 prompt 只有两个自然语言边界示例，不是完整 JSON 输出示例；约束解码只能保证结构，不能教会语义边界。
- 当前 JSON Schema 固定字段数和枚举，但不能单独保证 field_key 唯一、checks/verdict/reason 的条件一致性或 suspicious comment 真正引用本请求证据。
- `data/evaluation/calibration/adjudications_library.json` 的 287 条标签来自历史 AI 模拟裁定，不是人工金标。可以作为冻结的 provisional 校准参考，但必须保留来源说明，不得宣称人工验证。
- 历史约 kappa 0.40 来自旧证据形态；证据切分、编号和 prompt 已变化，不能作为严格可比基线。

开始前完整读取根目录、`app/backend/`、`app/backend/services/copd_extraction/` 和 `docs/` 的 AGENTS.md/CLAUDE.md，以及上述报告、现有 verifier prompt 和相关测试。

## 优化策略

### 1. 保持证据与 claim 分离

- 证据区继续先出现，使用原始 `[uXXX] 原文`，正文只展示一次。
- claim 继续使用 JSON，只包含 field_key、definition、value、cited_ids；不要在 claim 重复 cited_text。
- 不根据预测 value 反向搜索、生成或重新编号证据。
- found 字段 cited ID 缺失、为空或不存在时继续在调用前拦截，不调用 LLM，也不让模型把装配问题判成字段错误。
- section 请求只包含真实 cited units 和必要邻接上下文；不要恢复完整 OCR 重复输入。

### 2. 复核顺序保持简单但更明确

固定顺序仍为：

1. grounding_supported
2. field_scope_valid
3. ocr_text_clear
4. logic_consistent
5. verdict

明确三类边界：

- 抽取值不受证据支持、字段/时间越界、否定或数值关系错误 → `extraction_mistake`；
- 抽取忠实引用原文，但原文存在可定位且影响理解的 OCR 病句、残缺、标签或单位问题 → `ocr_quality_issue`；
- 术语陌生、写法不常见、轻微格式或正常有序聚合，不构成明确问题 → pass。

不要要求模型凭医学常识纠正 OCR，也不要让“忠实摘录”自动豁免 OCR 风险检查。

### 3. 增加少量完整 JSON 微例

用 3—4 个完整、对比式 JSON 微例替换现有自然语言示例；示例只展示一条 verification，不提供 61 字段完整输出：

1. 正确且有据字段 → pass；
2. 原文支持但字段越界 → suspicious/extraction_mistake；
3. 抽取忠实但证据存在 material OCR 病句 → suspicious/ocr_quality_issue；
4. 如需控制误报，加入“术语虽陌生但文本完整明确”的 pass 对照，例如“粗测听力正常”，强调不能因不熟悉“粗测”而标 OCR 错误。

示例使用真实格式的 field_key 和 `u9xx` 虚拟证据 ID，checks 四键完整，comment 不超过 40 字；明确示例 ID 不属于正式输入，禁止复制。

不要堆叠“胸状胸、古手、粗测”等具体词表作为规则。示例表达错误形态，避免模型看到某个字就泛化误报。

### 4. 增加后端语义契约检查

约束解码后继续做确定性验证，至少保证：

- 每个请求中的 field_key 恰好返回一次，不得重复、缺失或出现组外字段；
- pass 必须四项 checks 全 true 且 reason_code=none；
- suspicious 必须至少一项 check=false 且 reason_code 不是 none；
- `ocr_quality_issue` 必须对应 `ocr_text_clear=false`；
- `extraction_mistake` 必须对应 grounding/scope/logic 至少一项 false；
- suspicious comment 必须包含本请求实际存在的 `[uXXX]`；
- comment 长度继续不超过 40；
- 历史 `fail` 解析保持兼容，但新生成只允许 pass/suspicious。

非法或条件矛盾的单组响应按现有失败语义跳过该组并记录本地日志，不静默修补成看似合理的 verdict。

### 5. 只优化一个 prompt 版本

- 不做 A/B，不增加 reminder 变体，不连续调参。
- 完成 prompt 和语义验证后只生成一个新版本；记录 prompt 版本和哈希。
- 不改变抽取 prompt、admission_eval.v2、golden 字段或抽取结果。

## 测试要求

扩充 fake-client 单测，不依赖真实 LLM，至少覆盖：

- evidence 在 claims 前，证据正文不在 claim 中重复；
- 三类核心 JSON 微例和“粗测不误报”对照存在且结构合法；
- cited ID 缺失或为空时不调用复核 LLM；
- 重复 field_key、缺字段、组外字段被拒绝；
- pass 但 checks=false 被拒绝；
- suspicious 但四项全 true 或 reason=none 被拒绝；
- reason_code 与失败 check 不一致被拒绝；
- suspicious comment 引用不存在的 ID 被拒绝；
- 合法 pass、字段越界、OCR 病句均能解析；
- 单组失败不影响其他 section；
- 历史 fail 仍可解析；
- `apply_verdicts` 仍只增加审核标记，不改 value/status。

使用项目 conda 环境先运行：

```text
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py app/backend/tests/test_copd_prompts.py -q
```

再根据实际修改范围补充相关 evidence/contract/evaluation 测试。不要修与本任务无关的既有失败。

## 唯一真实冒烟

只运行 `case_006` 的复核器冒烟，优先复用已经冻结的抽取 payload/candidates，不重新跑抽取模型；若缺少可复用输入，先如实说明，不得暗中重跑六例抽取。

重点核对：

- `胸状胸`、`古手` 等确切 OCR 病句能进入 `ocr_quality_issue`；
- `粗测听力正常` 不因术语陌生被误报；
- pe_eyes、pe_neurological_exam 的明确字段越界能标 `extraction_mistake`；
- 氧合指数相关声称只依据请求中实际提供的血气/数值证据判断，不凭常识补证据；
- 多个原文片段的有序聚合不被误报；
- evidence ID/上下文装配误报为 0；
- JSON 和语义契约非法为 0。

只允许因结构或调用故障修复后重跑同一个病例一次；不因质量结果不理想修改第二版 prompt。

冒烟后输出复核 TP/FP/FN/TN、precision、recall、F1、kappa 和逐字段明细。若只能使用历史 provisional 裁定，报告必须显式标注；kappa 不单独作为结论。

## 报告

生成一份 HTML 报告，至少包含：

- 优化前真实 prompt 和优化后完整 prompt；
- 证据区、claims JSON、JSON Schema 和后端语义验证；
- 3—4 个 JSON 微例全文；
- 单元测试结果；
- case_006 真实运行条件、模型、输入来源和 TP/FP/FN/TN；
- 命中、漏检、误报及对应 `uXXX` 证据；
- provisional 裁定和没有正式人工金标的限制；
- 生产复核器是否仍关闭。

## 禁止项

- 不实现或预留 LLM-as-Judge；
- 不建立 rubric、加权评分或新评价平台；
- 不审核 not_found，不声称解决抽取 FN；
- 不修改抽取 prompt、61 字段、外部审核状态、前端或导出；
- 不把 legacy AI 标签称为人工金标；
- 不接入云 API或联网下载；
- 不重新运行 6 例抽取或做消融；
- 不把复核器接入生产活动路径；
- 不 commit、push、reset、checkout、clean 或 stash；
- 不生成 DESIGN、EXECUTION_PLAN、STATUS 或 REVIEW_PACKET。

## 上下文隔离

你持有最终取舍、共享文件修改、集成测试和结论。只有在阅读历史校准明细会显著污染主上下文时，才使用一个只读 subagent 汇总已知 FN/FP 形态；不要固定创建 implementer/reviewer/fixer，也不要让多个 Agent 修改相同文件。

## 最终回传

简洁但证据化地报告：

- 实际修改文件和复核语义变化；
- 新 prompt 版本、哈希和完整报告路径；
- 测试命令及通过/失败数量；
- case_006 是否真实运行、输入是否复用、模型和 TP/FP/FN/TN；
- 仍存在的复核 FN/FP、provisional 标签限制；
- 生产复核器仍关闭的证据；
- 未完成项和残余风险。

不要使用特殊终局词代替事实报告。现在开始执行。
