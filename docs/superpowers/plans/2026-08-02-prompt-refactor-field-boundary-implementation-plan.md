# 提示词精简重构 + 字段边界 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按四步消融执行：①精简重构抽取/复核器两段 prompt（宁少勿滥、统一骨架，产出变体 A/B 对比 user 尾部提醒句）②重跑实验验证指标不回退 ③加字段越界（各一句话）④再跑实验验证越界归零与增益。

**Architecture:** 两段 prompt 统一骨架（角色/任务/输出契约/通用原则/领域规则/附录）；`append_reminder` 布尔参数控制 user 尾部结构提醒句（变体 B），默认 False 保持向后兼容；system 保持完全固定（前缀缓存命中，已实测 22.5% 累计命中、同前缀 100% 命中）；字段越界落为抽取领域规则一句 + 复核器通用原则一句，reason_code 复用现有 `extraction_mistake`。

**Tech Stack:** Python 3.12 / Flask / pytest / vLLM OpenAI-compatible 客户端 / conda 环境 `manzufei_ocr`

## Global Constraints

- 测试命令一律：`conda run -n manzufei_ocr python -m pytest <path> -v`（在 worktree 根目录执行）
- 单测必须注入 fake LLM 客户端，不依赖真实 vLLM 服务
- Git commit message 使用中文
- 温度恒为 0.0；system 文本必须完全固定（不含任何 evidence/document_text 变量数据），变量数据只进 user
- prompt 改动视为契约变更：每次改动同步更新对应单测断言
- 不新增 schema 字段、不改复核器 reason_code 枚举、不改 evidence_units 切分逻辑
- 越界/边界表述各一句话，不列 case 级示例堆（宁少勿滥）
- `data/`、`exports/`、`logs/` 中的运行数据不得提交；评估产物留在 `data/evaluation/`
- 工作区已有未提交修改（`app/backend/tests/test_review_routes.py`、`app/backend/tests/test_qwen_batch_engine_layout.py`）与本工作无关，勿动勿提交
- 全量 pytest 既有失败（test_review_routes 4 + test_qwen_batch_engine_layout 1）与本工作无关，勿修
- 实验类任务（Task 3/5/6）由协调者（主 agent）执行，subagent 只做代码与单测

---

### Task 1: 抽取 prompt 精简重构（变体 A/B）+ 单测更新

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`（`build_admission_structured_fields_messages`）
- Modify: `app/backend/tests/test_copd_prompts.py`
- Modify: `app/backend/evaluation/run_eval.py`（新增 `--append-reminder` 透传）
- Modify: `app/backend/evaluation/runner.py`（`run_pipeline` 透传）
- Modify: `app/backend/services/copd_extraction/port.py`（`COPDAdmissionQwenFieldPort.extract` 透传）

**Interfaces:**
- `build_admission_structured_fields_messages(schema, evidence_units, document_text="", append_reminder=False) -> tuple[str, str]`——新参数默认 False（变体 A）；True 时 user 末尾追加一行"请严格遵守 system prompt 中的【输出契约】【通用原则】【领域规则】。"（变体 B，位于前缀之后不影响前缀缓存）
- `run_eval --append-reminder` → `run_pipeline(..., append_reminder=...)` → `extract(..., append_reminder=...)` → `build_admission_structured_fields_messages(...)`——全程默认 False，向后兼容
- 兼容包装 `build_admission_structured_fields_prompt` 行为不变

**重构要求（spec 5.2）：**
- 骨架 6 段：角色与任务（2 句）→ 输出契约（JSON 形状 + 状态枚举 + 四键 + 1 示例）→ 通用原则（5-6 条一句话：可定位摘录/不静默修正 OCR/保留否定词/诊断只摘录/共享证据单元）→ 领域规则（J 型判定压缩措辞）→ 固定字段表
- 删【再次强调】整段；删 `_OCR_RISK_WARNINGS` 独立段（压缩为通用原则一条，保留 P62/P02、10^9/L 例）
- 预期 system 7199 → 约 4000-4500 字符

**验证:** `test_copd_prompts.py` 断言适配新结构（输出契约/通用原则/领域规则各段存在、J 型规则存在、否定词规则存在）；新增 `append_reminder` 两态断言（默认无提醒句、True 时有且提醒句在 user 末尾）。

### Task 2: 复核器 prompt 精简重构（变体 A/B）+ 单测更新

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`（`build_verification_messages`）
- Modify: `app/backend/tests/test_copd_verifier.py`
- Modify: `app/backend/services/copd_extraction/verifier.py`（`FieldVerifier` 接受 `append_reminder` 透传）
- Modify: `app/backend/evaluation/runner.py`（构造 `FieldVerifier` 时透传）

**Interfaces:**
- `build_verification_messages(evidence_units, fields, append_reminder=False) -> tuple[str, str]`——默认 False；True 时 user 末尾追加提醒句
- `FieldVerifier(llm_client, append_reminder=False)`——透传给 `build_verification_messages`

**重构要求（spec 5.3）：**
- 骨架：角色+任务（2 句）→ 核验规则 5-6 条一句话（值证一致即 pass/确凿问题必须标记/只标记可逐字定位（全文 1 处）/长文本逐句扫读/OCR 错读含 1 行 3 例常见模式）→ verdict 契约（枚举 + checks + comment ≤40 字）→ 1 个输出示例 + 1 个反例
- 删"必须可逐字定位"重复（3 处 → 1 处）；"双向标准"改直白一句话；错读模式列表 4 行 8 例 → 1 行 3 例（注明"常见模式而非全部"）
- 预期 system 2988 → 约 1800-2000 字符

**验证:** `test_copd_verifier.py` 既有断言适配（OCR 职责、逐句扫读、双向标准措辞、反例保留）；新增 `append_reminder` 两态断言。

### Task 3: step0 基线确认 + step2 A/B 实验（协调者执行，不入 subagent）

- 基线资产确认：`data/evaluation/reports/20260802_032255_*.json`（抽取指标）、`data/evaluation/calibration/20260802_verdicts_v3.json`（295 条，11 suspicious）；缺失则先补跑
- 变体 A 与 B 各跑：`conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval --schema app/config/schemas/admission_record_structured_fields.v1.yaml --model Qwen3.5-4B-AWQ-4bit --base-url http://127.0.0.1:8082/v1`（A 不带 flag / B 带 `--append-reminder`）
- verdicts：`python -m app.backend.evaluation.calibrate export --golden-dir data/evaluation/golden --schema app/config/schemas/admission_record_structured_fields.v1.yaml --model Qwen3.5-4B-AWQ-4bit --base-url http://127.0.0.1:8082/v1 --out data/evaluation/calibration/20260802_verdicts_refactor_{A,B}.json`
- 对比：status/value 准确率、幻觉数、契约非法数、suspicious 分布（vs 基线 11）、token 缩减实测；噪声带宽内不选型；**数据定夺主线形态 A 或 B**

### Task 4: 字段越界（A 抽取一句 + B 复核器一句）+ 单测更新

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`（抽取领域规则加"字段边界"一句；复核器通用原则加"字段越界"一句）
- Modify: `app/backend/tests/test_copd_prompts.py`、`app/backend/tests/test_copd_verifier.py`

**要求（spec 6.1/6.2）：**
- 抽取领域规则新增一句："字段边界：每个字段只抽取字段表对应部位/项目的内容；字段表未收录的内容（如一般情况：发育/营养/体型/神志/表情/体位）不写入任何字段、不引用为证据。"
- 复核器通用原则新增一句："字段越界：值的内容域与字段对应部位明显不符（如眼部字段出现一般情况内容）→ 标记为 extraction_mistake，引用原文片段即可。"
- 各一句话，无示例堆；不动 verdict 契约与 reason_code 枚举

**验证:** 单测新增断言（system 含"字段边界"/"字段越界"表述）。

### Task 5: step4 实验（协调者执行，不入 subagent）

- 在 step2 选定形态（A 或 B）上跑 run_eval + calibrate export（`--append-reminder` 按选定形态传）
- 越界统计脚本（协调者）：pe_* 字段 value 含一般情况关键词（发育|营养|体型|神志|表情|体位|步态）的字段数 vs 基线 4-6；pe_eyes value 长度 vs 基线 max 909
- 对比 step2 指标：不回退 + 越界归零/显著下降

### Task 6: 报告整理（协调者执行）

- 对比结果整理（0 基线 / step2 A / step2 B / step4）→ markdown 或 HTML 报告，数据留 `data/evaluation/`
- 记录 token 缩减实测（重构前后 system 字符数对比）
