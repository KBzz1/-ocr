# verifier.v3 实施计划：非标准表述契约 + 判别细则 + 字段级调用

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把复核器升级为 verifier.v3：`reason_code`/check 契约改名（`nonstandard_expression`/`text_standard`）、prompt 补"术语陌生 vs 非标准表述"判别细则与对照微例、拆句边界扩展到逗号级、复核调用改为字段级分组串行，并在 6 例全量冒烟中对照冻结预期 V1-V8。

**Architecture:** 契约层（`response_schemas.py` + `verifier.py` 解析/语义验证，历史键兼容）→ prompt 层（`prompts.py` v3 文本）→ 调用层（`runner.py`/`calibrate.py` 改 `group_by="field"`）→ 6 例抽取+复核冒烟（真实 LLM）→ 版本登记与报告同步。每层独立可测，TDD 推进。

**Tech Stack:** Python 3（Flask 后端）、pytest（fake LLM client 单测）、Qwen3.5-4B-AWQ vLLM（冒烟）、conda 环境 `manzufei_ocr`。

## Global Constraints

- 测试命令统一：`conda run -n manzufei_ocr python -m pytest <path> -q`（CLAUDE.md）。
- 单元测试必须使用可注入 fake LLM client，不依赖真实 LLM。
- 契约变更必须保持历史数据解析兼容（`ocr_quality_issue` / `ocr_text_clear` 旧值仅解析、不生成）。
- 复核 system 文本逐字节定稿后不可随意改动（vLLM 前缀缓存前提）；本轮由 v2 → v3 一次性替换。
- 冒烟真实调用仅限本 spec 授权范围：6 例抽取（extractor.v4）+ 6 例复核（v3，字段级串行）。
- Git commit message 使用中文。
- 冒烟产物冻结到 `data/evaluation/reports/`，不提交。

---

### Task 1: 契约改名（response_schemas + verifier 解析/语义验证）

**Files:**
- Modify: `app/backend/services/copd_extraction/response_schemas.py:70-100`（build_verification_json_schema 的 checks 与 reason_code 枚举）
- Modify: `app/backend/services/copd_extraction/verifier.py:13-21,253-265,286-302`（常量、语义验证、解析归一化）
- Modify: `app/backend/tests/test_copd_verifier.py`（helper `_four_checks` 与全部旧键/旧 reason 断言；新增历史兼容测试）
- Test: `app/backend/tests/test_copd_verifier.py`

**Interfaces:**
- Consumes: 无（纯契约层）。
- Produces:
  - `build_verification_json_schema(fields)` — checks 键含 `text_standard`；`reason_code` 枚举 `["extraction_mistake", "nonstandard_expression", "none"]`。
  - `FieldVerifier.verify(...)` — 解析时把旧 checks 键 `ocr_text_clear` 归一化为 `text_standard`（值不变）；`_ALLOWED_REASONS` 同时接受新旧值；语义验证对新旧 reason 值均要求 `text_standard=false`。

- [ ] **Step 1: 改 helper 并写失败测试（旧键拒绝 + 新键通过 + 历史兼容）**

```python
# test_copd_verifier.py —— 替换 _four_checks 定义（336-341 行）：
def _four_checks(grounding=True, scope=True, text=True, logic=True):
    return {
        "grounding_supported": grounding,
        "field_scope_valid": scope,
        "text_standard": text,
        "logic_consistent": logic,
    }


# 新增测试（追加到文件末尾，语义契约区块之后）：

def test_v3_contract_new_keys_accepted():
    """verifier.v3：新 checks 键 text_standard + 新 reason nonstandard_expression 可解析。"""
    units = [_mk_unit("u001", "胸状胸。")]
    candidates = [_mk_field("pe_chest", "胸状胸", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_chest", "verdict": "suspicious",
        "reason_code": "nonstandard_expression",
        "checks": _four_checks(text=False), "comment": "u001 胸状胸非标准表述"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert result[0]["reason_code"] == "nonstandard_expression"
    assert result[0]["checks"]["text_standard"] is False


def test_v3_contract_old_check_key_renormalized():
    """历史数据：旧 checks 键 ocr_text_clear 解析时归一化为 text_standard。"""
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    payload = {"verifications": [{"field_key": "pe_temperature", "verdict": "pass",
        "reason_code": "none",
        "checks": {"grounding_supported": True, "field_scope_valid": True,
                   "ocr_text_clear": True, "logic_consistent": True},
        "comment": "一致"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert "text_standard" in result[0]["checks"] and "ocr_text_clear" not in result[0]["checks"]


def test_v3_contract_legacy_reason_still_parsed_with_old_check():
    """历史数据：reason=ocr_quality_issue + 旧键 ocr_text_clear=false 组合可解析（不误拒）。"""
    units = [_mk_unit("u001", "古手中指断指再植术后5年。")]
    candidates = [_mk_field("pmh_surgery_history", "古手中指断指再植术后5年", [units[0]])]
    payload = {"verifications": [{"field_key": "pmh_surgery_history", "verdict": "suspicious",
        "reason_code": "ocr_quality_issue",
        "checks": {"grounding_supported": True, "field_scope_valid": True,
                   "ocr_text_clear": False, "logic_consistent": True},
        "comment": "u001 古手疑为左手错读"}]}
    result = FieldVerifier(FakeLlmClient(payload)).verify(candidates, document_text="")
    assert len(result) == 1
    assert result[0]["reason_code"] == "ocr_quality_issue"
    assert result[0]["checks"]["text_standard"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -q`
Expected: 新测试失败（缺 text_standard 键 / 旧键未归一化）；存量测试也失败（`_four_checks` 键名已改但实现未改）。

- [ ] **Step 3: 修改 response_schemas.py**

```python
# response_schemas.py build_verification_json_schema 内（70-100 行）：
    checks = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "grounding_supported",
            "field_scope_valid",
            "text_standard",
            "logic_consistent",
        ],
        "properties": {
            "grounding_supported": {"type": "boolean"},
            "field_scope_valid": {"type": "boolean"},
            "text_standard": {"type": "boolean"},
            "logic_consistent": {"type": "boolean"},
        },
    }
    # ...
            "reason_code": {
                "type": "string",
                "enum": ["extraction_mistake", "nonstandard_expression", "none"],
            },
```

- [ ] **Step 4: 修改 verifier.py 常量与语义验证**

```python
# verifier.py 13-21 行：
_ALLOWED_REASONS = {
    "none", "extraction_mistake", "nonstandard_expression",
    "evidence_insufficient", "ocr_quality_issue",  # ocr_quality_issue 仅历史解析兼容
}
_CHECK_KEYS = (
    "grounding_supported", "field_scope_valid", "text_standard", "logic_consistent",
)

# _parse_verdicts 内（293-295 行），checks 归一化：
        checks = item.get("checks") or {}
        if not isinstance(checks, dict):
            checks = {}
        # 历史键归一：verifier.v2 的 ocr_text_clear → v3 的 text_standard（布尔语义不变）
        checks = {
            "text_standard" if key == "ocr_text_clear" else key: value
            for key, value in checks.items()
        }

# _semantic_violations 内（256-257 行），reason↔check 对应更新：
            if v.get("reason_code") in ("nonstandard_expression", "ocr_quality_issue") \
                    and checks.get("text_standard") is not False:
                violations.append(
                    f"{field_key} {v.get('reason_code')} 但 text_standard 非 false")
```

- [ ] **Step 5: 更新存量测试断言（旧键名 → 新键名）**

把 `test_copd_verifier.py` 中其余 `"ocr_text_clear"` 全部改为 `"text_standard"`、`"ocr_quality_issue"` 全部改为 `"nonstandard_expression"`（除 Step 1 历史兼容测试中刻意保留旧值的两处）。涉及 `test_verify_group_by_field_one_request_per_field`（251-262 行）、`test_semantic_contract_reason_check_mismatch_rejected`（431-442 行）、`test_semantic_contract_legit_pass_scope_ocr_parsed`（453-470 行）等。

- [ ] **Step 6: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -q`
Expected: 全部 PASS（含新增 3 个测试）。

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/copd_extraction/response_schemas.py app/backend/services/copd_extraction/verifier.py app/backend/tests/test_copd_verifier.py
git commit -m "refactor:复核契约改名(reason nonstandard_expression+check text_standard)+历史键归一+单测"
```

---

### Task 2: prompt v3 文本（判别细则 + 对照微例 + 拆句扩展）

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py:20-22,112-164`（版本常量、_VERIFIER_EXAMPLES、build_verification_messages system 文本）
- Modify: `app/backend/tests/test_copd_prompts.py`（拆句文字断言、微例断言更新）
- Modify: `app/backend/tests/test_copd_verifier.py:30`（`test_verification_messages_claim_manifest_keeps_evidence_once` 的拆句文字断言）
- Test: `app/backend/tests/test_copd_prompts.py`、`app/backend/tests/test_copd_verifier.py`

**Interfaces:**
- Consumes: Task 1 的契约（prompt 文字与契约一致：`nonstandard_expression`/`text_standard`）。
- Produces: `build_verification_messages(...)` 的 system 为 v3 文本（含 5 条 JSON 微例 u911-u913）；`VERIFIER_PROMPT_VERSION == "verifier.v3"`。

- [ ] **Step 1: 写失败测试（v3 文本要素 + 微例可解析）**

```python
# test_copd_prompts.py 追加：

def test_verifier_v3_system_has_expression_standard_rule():
    """v3：表述规范性检查不归因 OCR、不要求修正词；术语陌生 vs 非标准表述判别细则存在。"""
    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "胸状胸。"}],
        fields=[{"field_key": "pe_chest", "value": "胸状胸", "evidence_ids": ["e001"]}],
    )
    assert "表述规范性" in system
    assert "不归因于 OCR" in system and "不要求给出修正词" in system
    assert "术语陌生" in system and "非标准表述" in system
    assert "nonstandard_expression" in system
    assert "text_standard" in system
    assert "ocr_quality_issue" not in system  # 新生成不再提旧 reason


def test_verifier_v3_grounding_split_extended_to_comma():
    """v3：拆句边界扩展到逗号/顿号（value>40 字），含否定豁免。"""
    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "x。"}],
        fields=[{"field_key": "pe_chest", "value": "x", "evidence_ids": ["e001"]}],
    )
    assert "超过 40 字时，按逗号、顿号补充拆分" in system
    assert "否认、无、未见" in system  # 否定豁免


def test_verifier_v3_five_micro_examples_parseable():
    """v3：5 条 JSON 微例（含对照：错读形似规范词）全部可解析，顶层仅 verifications。"""
    import re
    system, _ = build_verification_messages(
        evidence_units=[{"id": "e001", "text": "x。"}],
        fields=[{"field_key": "pe_chest", "value": "x", "evidence_ids": ["e001"]}],
    )
    blocks = re.findall(r"```json\n(.*?)\n```", system, re.S)
    assert len(blocks) == 5
    for block in blocks:
        parsed = json.loads(block)
        assert set(parsed.keys()) == {"verifications"}
        for v in parsed["verifications"]:
            assert set(v["checks"].keys()) == {
                "grounding_supported", "field_scope_valid", "text_standard", "logic_consistent"}
    assert "胸状胸" in system  # 对照微例含错读形似规范词
    assert "粗测听力正常" in system  # 术语陌生 pass 示例保留
```

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -q`
Expected: 新测试失败（v3 文字不存在、微例仍为 4 条旧键）。

- [ ] **Step 3: 修改 prompts.py 版本常量与微例**

```python
# prompts.py 20-22 行：
# 复核器 prompt 版本（2026-08-04 verifier.v3 定稿：表述规范性契约 + 术语陌生判别 + 对照微例 + 逗号级拆句；仅作追踪标识，不渲染进 prompt）。
VERIFIER_PROMPT_VERSION = "verifier.v3"

# prompts.py 112-132 行整体替换为：
# verifier.v3 五例 JSON 微例：三类核心 + 术语陌生 pass + 错读形似规范词对照；示例
# ID u911-u913 为虚拟证据 ID，不属于正式输入；每个示例只展示一条 verification，
# 不提供 61 字段完整输出。示例表达错误形态，不构成"见到某字就标"的词表规则。
_VERIFIER_EXAMPLES = """1. 正确且有据 → pass
```json
{"verifications":[{"field_key":"pe_respiratory_exam","verdict":"pass","reason_code":"none","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":true,"logic_consistent":true},"comment":"一致"}]}
```
2. 原文支持但字段越界 → suspicious/extraction_mistake
```json
{"verifications":[{"field_key":"pe_eyes","verdict":"suspicious","reason_code":"extraction_mistake","checks":{"grounding_supported":true,"field_scope_valid":false,"text_standard":true,"logic_consistent":true},"comment":"u911 原文属一般情况，不属眼部"}]}
```
3. 抽取忠实但证据存在可定位非标准表述 → suspicious/nonstandard_expression
```json
{"verifications":[{"field_key":"pe_neurological_exam","verdict":"suspicious","reason_code":"nonstandard_expression","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":false,"logic_consistent":true},"comment":"u912 原文'古手'非标准表述，疑为'左手'错读"}]}
```
4. 术语陌生（如"粗测听力正常"，规范用词但少见）但文本完整明确，不因不熟悉用词误报 → pass
```json
{"verifications":[{"field_key":"pe_ears","verdict":"pass","reason_code":"none","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":true,"logic_consistent":true},"comment":"一致"}]}
```
5. 对照：错读但形似规范词（如"胸状胸"疑为"桶状胸"）→ suspicious/nonstandard_expression
```json
{"verifications":[{"field_key":"pe_chest","verdict":"suspicious","reason_code":"nonstandard_expression","checks":{"grounding_supported":true,"field_scope_valid":true,"text_standard":false,"logic_consistent":true},"comment":"u913 原文'胸状胸'非标准表述，疑为'桶状胸'错读"}]}
```

示例仅展示结构与裁定边界；示例 ID u911-u913 不属于正式输入，禁止复制到输出。"""
```

- [ ] **Step 4: 修改 build_verification_messages 的 system 文本（v2 → v3）**

把 `system = """..."""` 整体替换为（139-164 行）：

```python
    system = """你是慢阻肺入院记录的字段级复核器。你只核验给定字段是否被给定 OCR 证据支持，不改写字段值、不补造证据、不提供医学建议。

【固定审核顺序】
1. grounding：先在 cited evidence 中核对声称值；完整值不连续时按句号、分号或换行拆成事实片段，再逐片段核对。value 超过 40 字时，按逗号、顿号补充拆分；含"否认、无、未见"的片段不拆。普通短 value 的逗号、顿号列表不拆开。
2. field scope：检查内容是否属于该字段定义的部位、项目和时间范围；原文支持但字段越界仍应标记。
3. 表述规范性：只检查证据中确实可定位的非标准表述（错读、病句、残缺、标签或单位问题），不归因于 OCR、不要求给出修正词。术语陌生（规范医学/日常用词但少见，如"粗测听力"）不构成问题；非任何标准用词或形近/音近标准词 → 必须标记。正确用字、符合规范的表述不得标记；值忠实摘录原文不豁免表述检查——值一致只证明抄得对，不证明文本本身没问题。
4. logic consistency：检查否定/不确定、时间归属、数值关系和字段内部是否自相矛盾；值与他句/他证据矛盾（时间归属错误、否定翻转、体征互斥、数值关系不合理）→ 均应标记；不能从常识补出证据不存在的事实。
5. verdict：四项检查全部通过才 pass；任何一项明确失败才 suspicious。调用方已在请求前检查 cited ID 是否完整，证据装配缺失不归因于字段。

【判定与原因】
- grounding、字段越界、时间归属、否定翻转或逻辑矛盾 → reason_code=extraction_mistake。
- 可定位的非标准表述 → reason_code=nonstandard_expression。
- 术语陌生（规范用词但少见）、写法不常见、轻微格式或正常有序聚合，不构成明确问题 → pass。
- 术语陌生与非标准表述的判别：术语陌生是规范医学/日常用词（如"粗测"），不标；非任何标准用词或形近/音近标准词（如"胸状胸"→"桶状胸"、"古手"→"左手"），是错读 → 必须标，标注时不需要给出正确词。
- pass 的 reason_code 必须为 none；不要把语义等价、多个有序证据片段聚合或正常族归一误报为问题。
- 只生成 pass 或 suspicious。历史数据可能含 fail，解析器会兼容，但本次不要生成 fail。

【输出契约】
输出单个 JSON 对象，顶层只有 verifications。数组与输入字段一一对应，不能重复、遗漏或新增字段。每项固定包含：
- field_key：输入字段 key；verdict：pass 或 suspicious；reason_code：extraction_mistake、nonstandard_expression 或 none。
- checks：只包含 grounding_supported、field_scope_valid、text_standard、logic_consistent 四个布尔值。
- pass 必须四项 checks 全 true 且 reason_code=none；suspicious 必须至少一项 check=false 且 reason_code 不是 none。
- nonstandard_expression 必须对应 text_standard=false；extraction_mistake 必须对应 grounding_supported/field_scope_valid/logic_consistent 至少一项 false。
- comment：不超过 40 个汉字。pass 写"一致"；suspicious 必须引用本请求实际存在的 uXXX 和具体疑点。

【示例】
""" + _VERIFIER_EXAMPLES
```

- [ ] **Step 5: 更新存量测试断言**

- `test_copd_verifier.py:30` 的 `assert "普通逗号、顿号列表不拆开" in system` → 改为 `assert "value 超过 40 字时，按逗号、顿号补充拆分" in system`。
- `test_copd_verifier.py` 中 `test_verifier_v2_four_json_micro_examples_present_and_parseable`（347-365 行）→ 改名 `test_verifier_v3_five_json_micro_examples_present_and_parseable`，断言数改 5、checks 键改 `text_standard`、新增 `"胸状胸" in system`。
- `test_copd_prompts.py` 中任何含 `ocr_quality_issue` / `ocr_text_clear` 的断言改新值（grep 后逐个改）。

- [ ] **Step 6: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py app/backend/tests/test_copd_prompts.py -q`
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_verifier.py
git commit -m "refactor:复核器verifier.v3(表述规范性契约+术语陌生判别+对照微例+逗号级拆句)+单测同步"
```

---

### Task 3: 调用侧字段级分组（串行）

**Files:**
- Modify: `app/backend/evaluation/runner.py:81-84`（`_verify_with_context` 的 group_by）
- Modify: `app/backend/evaluation/calibrate.py:150`（默认 group_by）
- Modify: `app/backend/tests/test_evaluation_runner.py`（385-420 行附近，若断言 group_by）
- Test: `app/backend/tests/test_evaluation_runner.py`

**Interfaces:**
- Consumes: Task 1-2 的 `FieldVerifier.verify(candidates, document_text, group_by, evidence_units)`（已支持 `"field"`）。
- Produces: 评估管线复核默认 `group_by="field"` 串行。

- [ ] **Step 1: 写失败测试**

```python
# test_evaluation_runner.py 追加（用既有 pipeline/mock 模式；若无现成 fake verifier，
# 用 recorder 包装 FieldVerifier 断言每组仅 1 字段）：

def test_apply_verify_default_groups_by_field():
    """评估管线默认复核按字段级分组（单组 1 字段，串行多次调用）。"""
    from app.backend.evaluation.runner import run_pipeline
    # ...按该文件既有 run_pipeline 测试写法构造 sample_input，
    # 注入 recording FieldVerifier 子类，断言每次 verify 调用 group_by=="field"
```

（注：若该文件已有 `test_apply_verify_default_runs_verifier` 断言 `group_by=="section"`，改为 `"field"` 即可，新增测试可省。）

- [ ] **Step 2: 运行测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py -q`
Expected: 新断言失败（现为 section）。

- [ ] **Step 3: 修改 runner.py 与 calibrate.py**

```python
# runner.py _verify_with_context（84 行附近）：
        return verifier.verify(
            candidates,
            document_text,
            group_by="field",          # verifier.v3：字段级分组，单字段一请求
            evidence_units=evidence_units,
        )

# calibrate.py 150 行：
                group_by=args.group_by or "field",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add app/backend/evaluation/runner.py app/backend/evaluation/calibrate.py app/backend/tests/test_evaluation_runner.py
git commit -m "feat:复核调用改字段级分组串行(单字段一请求,注意力集中)+测试"
```

---

### Task 4: 6 例抽取 + verifier.v3 全量复核冒烟

**Files:**
- Create（运行产物，不提交）：`data/evaluation/reports/20260804-verifier-v3-case*-candidates.json`、`-smoke.json`、`20260804-verifier-v3-full-smoke-summary.json`
- Run（临时脚本，放 /tmp）：抽取 6 例 → 复核 6 例 → V1-V8 对照

**Interfaces:**
- Consumes: Task 1-3 全部产物；`data/evaluation/golden/case_001~006.json`；`data/evaluation/calibration/adjudications_library.json`（kappa 用）。
- Produces: 冒烟数据与对照结果（V1-V8 命中表）。

- [ ] **Step 1: 重跑 6 例抽取（extractor.v4，真实 LLM）**

Run:
```bash
for c in case_001 case_002 case_003 case_004 case_005 case_006; do
  conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval \
    --schema app/config/schemas/admission_record_structured_fields.v1.yaml \
    --base-url http://127.0.0.1:8082/v1 --model Qwen3.5-4B-AWQ-4bit \
    --golden-dir data/evaluation/golden --report-dir data/evaluation/reports \
    --case-id "$c" --no-verifier --no-quality-flags 2>&1 | tail -3
done
```
Expected: 6 例各生成 `20260804-...-report.json`（或按 run_eval 实际命名）；核对 candidates 61 字段全覆盖、error=None。

- [ ] **Step 2: 写复核冒烟脚本（/tmp/verify_v3_smoke.py）**

```python
# -*- coding: utf-8 -*-
"""6 例 verifier.v3 字段级串行复核 + V1-V8 对照。"""
import json, sys, time
REPO = "/home/kbzz1/manzufei_ocr/.claude/worktrees/prompt-refactor-field-boundary"
sys.path.insert(0, REPO); sys.path.insert(0, REPO + "/app/backend")
from app.backend.evaluation.chunked_review import units_from_ocr_text
from app.backend.services.copd_extraction.verifier import FieldVerifier
from app.backend.services.algorithm_ports.qwen_vllm_client import QwenVLLMClient

client = QwenVLLMClient(base_url="http://127.0.0.1:8082/v1", model="Qwen3.5-4B-AWQ-4bit")
verifier = FieldVerifier(client)
library = json.load(open(REPO + "/data/evaluation/calibration/adjudications_library.json"))
out = {}
for ci in range(1, 7):
    cid = f"case_{ci:03d}"
    case = json.load(open(REPO + f"/data/evaluation/golden/{cid}.json"))
    cands = json.load(open(REPO + f"/data/evaluation/reports/20260804-{cid}-candidates.json"))
    # 若 run_eval 产物结构不同，按实际键调整；candidates 取 61 字段 found 列表
    units = units_from_ocr_text(case["ocr_text"])
    t0 = time.perf_counter()
    verdicts = verifier.verify(cands, "", group_by="field", evidence_units=units)
    dt = time.perf_counter() - t0
    # 对照 adjudications_library 该 case 的裁定（should_flag），算 2×2 与 kappa（用
    # metrics.py 或 sklearn-free 手算，口径与 08-03 冒烟一致：suspicious|fail vs pass）
    out[cid] = {"seconds": round(dt, 2), "verdicts": verdicts}
    print(cid, f"{dt:.1f}s", flush=True)
json.dump(out, open(REPO + "/data/evaluation/reports/20260804-verifier-v3-full-smoke-summary.json", "w"), ensure_ascii=False, indent=1)
```

- [ ] **Step 3: 运行冒烟并输出 V1-V8 对照**

Run: `conda run -n manzufei_ocr python /tmp/verify_v3_smoke.py`
Expected: 6 例全部完成；随后跑一个对照脚本（或手工核对 summary）输出：

| # | 预期 | 结果 |
|---|---|---|
| V1 | case_006 pe_chest suspicious（胸状胸/乳房越界） | ? |
| V2 | case_006 pe_neurological_exam suspicious（越界） | ? |
| V3 | case_006 pmh_surgery_history suspicious（古手） | ? |
| V4 | 6 例正常短字段无新增误报；上轮 3 FP 不回归必标 | ? |
| V5 | 语义契约 0 违规（6 例） | ? |
| V6 | 单例 ≤90s、6 例总耗时 | ? |
| V7 | 历史数据解析兼容（单测已覆盖） | pass |
| V8 | 6 例 kappa 变化方向 | ? |

- [ ] **Step 4: 记录结果**

把对照表与逐例 verdicts 写入 `data/evaluation/reports/20260804-verifier-v3-full-smoke-summary.json`（追加 `checklist` 键）。未命中项如实记录，不回改。

- [ ] **Step 5: Commit（仅代码侧若冒烟暴露 bug；产物不提交）**

若有失败项需要修：回到对应 Task 修；无失败项则无提交。

---

### Task 5: 版本登记 + 报告同步

**Files:**
- Modify: `docs/Shared/version-registry.md`（复核器行 + 迭代表加 verifier.v3）
- Regenerate: `data/evaluation/reports/20260803-prompt-refactor-v3-full-prompts.html`（prompts.py 已变 v3，重新生成；含实际案例区）
- Create（不提交）：`data/evaluation/reports/20260804-verifier-v3-report.html`（冒烟汇总报告，参考 20260803-verifier-opt-v1-report.html 风格）

**Interfaces:**
- Consumes: Task 4 的 summary；`sha256sum app/backend/services/copd_extraction/prompts.py app/backend/services/copd_extraction/verifier.py`。

- [ ] **Step 1: 登记版本**

```markdown
# docs/Shared/version-registry.md —— 复核器迭代表追加：
| `verifier.v3` | prompts.py（v3 文本）+ verifier.py（新契约） | sha256（实际值） | 2026-08-04 定稿 | 表述规范性契约 + 术语陌生判别 + 字段级分组 |
```

- [ ] **Step 2: 重新生成 full-prompts 报告**

复用本次会话的生成逻辑（抽取/复核 system 从当前代码渲染，case_006 实际案例区保留），输出到同名文件。核对：标题版本行改 `extractor.v4 + verifier.v3`；复核 system 区为 v3 文本；微例数 5。

- [ ] **Step 3: 生成 v3 冒烟报告 HTML**

简化版（header 指标卡 + V1-V8 对照表 + 逐例逐字段 verdicts 表 + 残余问题说明），风格对齐 `20260803-verifier-opt-v1-report.html`。

- [ ] **Step 4: Commit**

```bash
git add docs/Shared/version-registry.md
git commit -m "docs:复核器verifier.v3版本登记"
```

（full-prompts 与冒烟报告在 data/ 下，不提交。）

---

## Self-Review 记录

- **Spec 覆盖**：§3.1/3.2 → Task 1；§3.3 → Task 2；§3.4 → Task 3；§4 V1-V8 → Task 4；§5 测试 → Task 1-3 内嵌；版本登记 → Task 5。§2 边界（不改切分器/不调 judge/不动服务端）无需任务，符合。
- **占位符扫描**：Task 4 Step 2 脚本中 `cands` 读取路径依赖 run_eval 实际产物键，已注明"按实际键调整"——这是运行时的适配说明，不是未定义接口。
- **类型一致性**：`text_standard`/`nonstandard_expression` 贯穿 Task 1-2 与测试；`group_by="field"` 贯穿 Task 3；微例 ID u911-u913 与 v2 的 u911-u914 有重叠（u914 不再使用），注释已更新为"u911-u913"。
