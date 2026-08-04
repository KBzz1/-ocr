# 复核器分块审核实验 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把复核器请求组织从"一次全量"改为"字段级/字段簇级分组"（step6 实验），验证 A 类错读 4 条 + B 类越界 1 条仍漏的召回提升，KV cache（system 前缀缓存）不受影响；评估通过前生产复核路径行为不变。

**Architecture:** `FieldVerifier.verify` 增加 `group_by` 可选参数（None=现状一次全量 / "field"=每字段一条 / "section"=同 section_key 字段一条），分组模式每组独立 try-catch（失败组静默跳过，全组失败降级为空）；评估侧新增证据注入（现状 calibrate 路径 candidates evidence 为空，复核器实际拿的是整篇原文前 8000 字符，必须先按字段值定位到 evidence units）；prompts.py 措辞零改动（system 逐字节不变，前缀缓存前提保持）。

**Tech Stack:** Python 3.12 / Flask / pytest / vLLM OpenAI-compatible 客户端 / conda 环境 `manzufei_ocr`

## Global Constraints

- 测试命令一律：`conda run -n manzufei_ocr python -m pytest <path> -v`（在 worktree 根目录执行）
- 单测必须注入 fake LLM 客户端，不依赖真实 vLLM 服务
- Git commit message 使用中文
- **prompts.py 零改动**：system 字符串逐字节不变（2911 tokens），温度恒为 0.0；公共内容不得挪进 user
- 不改 `evidence_units.py` 切分逻辑（只消费其输出）；不改 reason_code 枚举；不动 schema 字段体系；不改输出契约（JSON 形状/verdict 枚举/checks 结构）
- `verify(group_by=None)` 行为必须与现状逐位一致（既有测试全绿 = 强制门）；实验形态只经 `group_by` 参数触发
- 分组失败语义（用户已确认）：每组独立 try，失败组静默跳过，其余组正常；全组失败降级为空列表；None 模式保持现状"整体降级为空"
- 工作区既有未提交修改（`app/backend/tests/test_review_routes.py`、`app/backend/tests/test_qwen_batch_engine_layout.py`）与本工作无关，勿动勿提交
- 全量 pytest 既有失败（test_review_routes 4 + test_qwen_batch_engine_layout 1）与本工作无关，勿修
- 实验类任务（Task 3/4）由协调者（主 agent）执行，subagent 只做代码与单测（Task 1/2）
- 评估产物（verdicts、judge 包、报告）留在 `data/evaluation/`，不进 git
- 设计权威：`docs/superpowers/specs/2026-08-02-verifier-chunked-review-experiment-design.md`

---

### Task 1: 复核器分组调用（group_by 参数 + 分组失败语义）+ 单测

**Files:**
- Modify: `app/backend/services/copd_extraction/verifier.py`（`FieldVerifier.verify`、`_collect_evidence`、新增 `_split_groups`）
- Modify: `app/backend/tests/test_copd_verifier.py`

**Interfaces:**
- 现状：`FieldVerifier.verify(candidates, document_text="") -> list[dict]`（一次请求审全字段，失败整体降级为空）
- 新：`verify(candidates, document_text="", group_by: str | None = None)`；`group_by=None`（默认）行为与现状逐位一致；`group_by="field"` / `"section"` 触发分组模式
- 新增内部函数 `_split_groups(candidates, group_by) -> list[dict]`：每组 `{"fields": [...], "units": [...]}`（units 来自各字段回填的 `evidence` 数组元素，去重保序）
- 后续 Task 2 的 `calibrate export --group-by` 依赖本 Task 的 `verify(..., group_by=...)` 签名

**背景事实（实施者须知）：** 评估路径（run_eval/calibrate）的 `_input_for` 硬编码 `evidence_units: []`（run_eval.py:81），candidates 的 `evidence` 数组为空；`verify` 走 `_collect_evidence` 的 `document_text[:8000]` 兜底——即复核器证据 = 整篇原文前 8000 字符。分组模式消费的 units 由 Task 2 注入进 candidates 的 `evidence`；本 Task 分组逻辑只读 `c["evidence"]`，为空时该组 units 为空（user 渲染"（未提供证据）"），不崩溃。

- [ ] **Step 1: 写失败测试**（test_copd_verifier.py 追加）

```python
class _RecordingClient:
    """记录每次调用 (user, system_prompt)，按序返回预设响应；raise 抛错模拟单组失败。"""
    def __init__(self, responses, fail_at=None):
        self.responses = list(responses)
        self.fail_at = fail_at
        self.calls = []
    def complete_json(self, user, system_prompt=None, **kwargs):
        self.calls.append((user, system_prompt))
        idx = len(self.calls) - 1
        if self.fail_at is not None and idx in self.fail_at:
            raise RuntimeError("模拟失败")
        return self.responses.pop(0)

def _mk_field(fk, value, units, section=None):
    return {
        "field_key": fk, "status": "found", "value": value,
        "evidence_ids": [u["id"] for u in units],
        "evidence": [dict(u, section_key=section) for u in units] if section else [dict(u) for u in units],
    }

def _mk_unit(uid, text):
    return {"id": uid, "text": text}

def test_verify_group_by_field_one_request_per_field():
    units = [_mk_unit("u001", "体温36.5℃，脉搏88次/分。")]
    candidates = [
        _mk_field("pe_temperature", "36.5℃", [units[0]]),
        _mk_field("pe_pulse", "88次/分", [units[0]]),
    ]
    client = _RecordingClient([
        {"verifications": [{"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"}]},
        {"verifications": [{"field_key": "pe_pulse", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"}]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, document_text="全文", group_by="field")
    assert len(client.calls) == 2
    # 每条请求只含自己字段的值，不含其他字段
    assert "36.5℃" in client.calls[0][0] and "88次/分" not in client.calls[0][0]
    assert "88次/分" in client.calls[1][0] and "36.5℃" not in client.calls[1][0]
    # system 逐字节相同
    assert client.calls[0][1] == client.calls[1][1]
    assert len(result) == 2

def test_verify_group_by_section_groups_same_section():
    units = [_mk_unit("u001", "颈部：颈软，气管居中。"), _mk_unit("u002", "胸部：胸廓对称。")]
    candidates = [
        _mk_field("pe_neck", "颈软", [units[0]], section="physical_examination"),
        _mk_field("pe_chest", "胸廓对称", [units[1]], section="physical_examination"),
    ]
    client = _RecordingClient([
        {"verifications": [
            {"field_key": "pe_neck", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
            {"field_key": "pe_chest", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
        ]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="section")
    assert len(client.calls) == 1  # 同 section 合并为一条请求
    assert "颈软" in client.calls[0][0] and "胸廓对称" in client.calls[0][0]
    assert len(result) == 2

def test_verify_group_failure_isolation():
    units = [_mk_unit("u001", "腹部：腹部正常。"), _mk_unit("u002", "肺部：呼吸音清。")]
    candidates = [
        _mk_field("pe_abdomen", "腹部正常", [units[0]]),
        _mk_field("pe_lung", "呼吸音清", [units[1]]),
    ]
    client = _RecordingClient(
        [{"verifications": [{"field_key": "pe_lung", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {}, "comment": "疑"}]}],
        fail_at={0},
    )
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert len(client.calls) == 2  # 失败组不中断后续组
    assert len(result) == 1 and result[0]["field_key"] == "pe_lung"

def test_verify_group_all_failed_returns_empty():
    units = [_mk_unit("u001", "体温36.5℃。"), _mk_unit("u002", "脉搏88次/分。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]]), _mk_field("pe_pulse", "88次/分", [units[1]])]
    client = _RecordingClient([], fail_at={0, 1})
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert result == []

def test_verify_group_filters_out_of_scope_fields():
    units = [_mk_unit("u001", "体温36.5℃。")]
    candidates = [_mk_field("pe_temperature", "36.5℃", [units[0]])]
    client = _RecordingClient([
        {"verifications": [
            {"field_key": "pe_temperature", "verdict": "pass", "reason_code": "none", "checks": {}, "comment": "一致"},
            {"field_key": "pe_eyes", "verdict": "suspicious", "reason_code": "ocr_quality_issue", "checks": {}, "comment": "越界"},
        ]},
    ])
    verifier = FieldVerifier(client)
    result = verifier.verify(candidates, group_by="field")
    assert [v["field_key"] for v in result] == ["pe_temperature"]  # 范围外字段按现状契约过滤
```

先读 `test_copd_verifier.py` 现有 fake client 的写法（若已有 RecordingClient 类似物则复用其风格，不要重复造新类；`FieldVerifier` 构造方式沿用现有测试）。

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: 新 5 个测试 FAIL（TypeError: verify() got an unexpected keyword argument 'group_by'）

- [ ] **Step 3: 实现 verify 分组参数**

`verifier.py` 修改：

```python
    def verify(self, candidates, document_text="", group_by=None):
        """对 found + value 非空字段执行复核，返回其意见列表；失败降级为空列表。

        group_by=None（默认）：一次请求审全部字段，任何异常整体降级为空（现状）。
        group_by="field"/"section"（实验形态）：按字段/字段簇分组，每组独立
        try-catch——失败组静默跳过、其余组正常；全组失败时 verdicts 为空（降级为空）。
        分组模式不改变输出契约；verdicts 按 field_key 合并后由调用方统一过滤。
        """
        targets = [
            c for c in candidates
            if isinstance(c, dict)
            and c.get("status") == "found"
            and (c.get("value") or "").strip()
        ]
        if not targets:
            return []
        try:
            from .prompts import build_verification_messages

            if group_by is None:
                evidence_units = _collect_evidence(targets, document_text)
                fields = _to_field_dicts(targets)
                system, user = build_verification_messages(
                    evidence_units, fields, append_reminder=self._append_reminder
                )
                payload = self._llm_client.complete_json(user, system_prompt=system)
                return [v for v in _parse_verdicts(payload)
                        if v.get("field_key") in {c.get("field_key") for c in targets}]
            # 分组模式：每组独立 try，失败组跳过，其余组正常；全组失败 → 空
            verdicts = []
            for group in _split_groups(targets, group_by):
                group_keys = {f.get("field_key") for f in group["fields"]}
                try:
                    system, user = build_verification_messages(
                        group["units"], _to_field_dicts(group["fields"]),
                        append_reminder=self._append_reminder,
                    )
                    payload = self._llm_client.complete_json(user, system_prompt=system)
                    verdicts.extend(
                        v for v in _parse_verdicts(payload) if v.get("field_key") in group_keys
                    )
                except Exception:  # noqa: BLE001 — 分组复核失败静默跳过该组
                    logger.warning("复核器分组调用失败，跳过该组（%s）", group_keys, exc_info=True)
            return verdicts
        except Exception:  # noqa: BLE001 — 复核器失败必须静默降级
            logger.warning("复核器调用失败，已降级为空意见", exc_info=True)
            return []
```

把现有 `verify` 中构造 `fields` 的列表推导抽为模块级函数 `_to_field_dicts(targets)`（`field_key`/`value`/`evidence_ids` 三键），`_collect_evidence` 保持不动（None 模式专用）；新增：

```python
def _split_groups(candidates: list[dict], group_by: str) -> list[dict]:
    """按 group_by 把字段分成若干组，每组携带该组字段的 evidence units（去重保序）。

    group_by="field"：每字段一组，units = 该字段 evidence 数组。
    group_by="section"：按字段证据首条含 section_key 的 unit 归组，同 section 一组；
    evidence 为空或全部无 section_key 的字段归 "__no_section__" 一组。
    """
    if group_by == "field":
        return [{"fields": [c], "units": _collect_units([c])} for c in candidates]
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        key = next(
            (u.get("section_key") for u in (c.get("evidence") or []) if u.get("section_key")),
            "__no_section__",
        )
        groups.setdefault(key, []).append(c)
    return [
        {"fields": fields, "units": _collect_units(fields)}
        for _, fields in sorted(groups.items())
    ]


def _collect_units(fields: list[dict]) -> list[dict]:
    """聚合一组字段的 evidence units（去重保序）；无则返回空列表。"""
    seen: set[str] = set()
    units: list[dict] = []
    for c in fields:
        for ev in c.get("evidence") or []:
            if not isinstance(ev, dict):
                continue
            key = ev.get("id") or ev.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                units.append({"id": ev.get("id") or f"e{len(units) + 1:03d}", "text": ev.get("text", "")})
    return units
```

注意：`build_verification_messages` 的字段块渲染 `引用证据 {evidence_ids}`——分组模式下 candidates 的 `evidence_ids` 可能为空（评估路径抽取输出未回填），渲染为"引用证据（无）"，但证据块仍有 units，模型可对照；prompts.py 零改动，接受该呈现。

- [ ] **Step 4: 跑测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py -v`
Expected: 全绿（既有全部 + 新 5 个）

- [ ] **Step 5: 确认 None 模式行为不变（强制门）**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_field_port.py -v`
Expected: 全绿（既有测试未触碰 verify 默认行为）

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/copd_extraction/verifier.py app/backend/tests/test_copd_verifier.py
git commit -m "feat:复核器分组调用(group_by字段级/字段簇级+分组失败隔离)+单测"
```

**验证:** test_copd_verifier.py 全绿；`verify()` 默认调用路径无行为差异。

---

### Task 2: 评估侧证据注入 + calibrate 分臂参数 + 单测

**Files:**
- Create: `app/backend/evaluation/chunked_review.py`
- Modify: `app/backend/evaluation/calibrate.py`（export 子命令加 `--group-by`）
- Create: `app/backend/tests/test_evaluation_chunked_review.py`

**Interfaces:**
- Consumes: Task 1 的 `verify(candidates, document_text="", group_by=None)`；`app/backend/services/algorithm_ports/evidence_units.py` 的 `build_evidence_units(document_result)`（输入 `{"pages": [...], "merged_text": str}`，输出带 `id`/`text`/`start_offset`/`end_offset`/可选 `page_no`/`section_key` 的 units）
- Produces: `units_from_ocr_text(ocr_text) -> list[dict]`、`inject_field_evidence(candidates, units) -> list[dict]`；`calibrate export` 新增 `--inject-evidence`（布尔）与 `--group-by {field,section}` 两个独立参数
- 实验四臂组合（Task 3 用）：基线₁ = 不注入 + 无 group-by（= step5 现状，复用不重跑）；基线₂ = `--inject-evidence`（评估口径修正：复核器吃字段证据 = 生产形态）；A = `--inject-evidence --group-by field`；B = `--inject-evidence --group-by section`
- 抽取阶段输入**必须保持现状**（`_input_for` 的 `evidence_units: []` 不动）——改它会让抽取 prompt 渲染变化、step5 基线不可比；证据注入只发生在复核调用前，不影响抽取结果与 status/value/幻觉指标
- 背景（spec §1.1）：生产链路 orchestrator 构建 evidence_units 并回填字段证据，生产复核器看到"字段证据聚合"；评估链路 `_input_for` 硬编码空 → 复核器看到"整篇原文"（当前 6 样本 < 8000 字符未触发截断，长病历会触发）——本 Task 的注入即评估口径修正

- [ ] **Step 1: 写失败测试**（test_evaluation_chunked_review.py）

```python
from app.backend.evaluation.chunked_review import units_from_ocr_text, inject_field_evidence

OCR = "主诉：反复咳嗽、咳痰20年。\n现病史：20年前患者受凉后反复出现咳嗽。\n体格检查：神清，颈软，气管居中。体温36.5℃，脉搏88次/分。\n辅助检查：血气分析示PO2 60mmHg。"

def test_units_from_ocr_text_splits_by_sentence():
    units = units_from_ocr_text(OCR)
    assert any("反复咳嗽、咳痰20年" in u["text"] for u in units)   # 主诉句成 unit
    assert any("颈软" in u["text"] for u in units)                  # 体格检查行成 unit
    assert all(u["id"].startswith("u") for u in units)
    assert all("start_offset" in u and "end_offset" in u for u in units)
    # 含章节头时给出 section_key（best-effort）
    assert any(u.get("section_key") == "chief_complaint" for u in units)

def test_inject_field_evidence_located_with_context():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_pulse", "status": "found", "value": "脉搏88次/分"}]
    result = inject_field_evidence(candidates, units)
    ev = result[0]["evidence"]
    assert ev, "值应在 units 中可定位"
    assert any("88次/分" in u["text"] for u in ev)
    # 上下文邻接：证据含命中 unit 前一个 unit（体温行）
    assert any("体温" in u["text"] for u in ev)

def test_inject_field_evidence_unlocated_falls_back_empty():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_skin", "status": "found", "value": "皮肤无异常（原文无此句）"}]
    result = inject_field_evidence(candidates, units)
    assert result[0]["evidence"] == []

def test_inject_field_evidence_skips_empty_value():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_skin", "status": "found", "value": ""}]
    result = inject_field_evidence(candidates, units)
    assert result[0]["evidence"] == []
```

（`units_from_ocr_text` 的 section_key 断言若 golden fixture 的章节头模式与 `_SECTION_PATTERNS` 不匹配，以实际输出为准调整断言——先手动跑一次看输出再定死断言。）

- [ ] **Step 2: 跑测试确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_chunked_review.py -v`
Expected: FAIL（ModuleNotFoundError: chunked_review）

- [ ] **Step 3: 实现 chunked_review.py**

```python
"""复核器分块审核实验：评估侧证据注入与分臂驱动。

背景：评估路径（run_eval/calibrate）的 _input_for 硬编码 evidence_units=[]，
candidates 的 evidence 数组为空，复核器实际拿到的是整篇原文前 8000 字符
（_collect_evidence 兜底）。本模块从纯文本 OCR 构建证据单元（复用
evidence_units 切分规则）并按字段值定位回填，使分组复核（group_by）有可
消费的证据；抽取阶段输入保持现状（基线可比），注入只发生在复核调用前。
"""
from __future__ import annotations


def units_from_ocr_text(ocr_text: str) -> list[dict]:
    """从纯文本 OCR 构建证据单元（复用 evidence_units 切分规则与 section_key 推断）。

    构造单页 document_result 喂 build_evidence_units；返回带
    id/text/start_offset/end_offset/可选 page_no/section_key 的 units。
    """
    from ..services.algorithm_ports.evidence_units import build_evidence_units

    text = ocr_text or ""
    return build_evidence_units({
        "pages": [{"text": text, "page_no": 1}],
        "merged_text": text,
    })


def inject_field_evidence(candidates: list[dict], units: list[dict]) -> list[dict]:
    """按字段值在 units 中的定位回填 evidence（命中 unit + 紧邻上下文各 1 个）。

    定位策略：值的前 8 个字符在 unit 文本中出现即命中（值开头最稳定）；
    无命中时退化为值内任意 6 字符窗口。命中后取该 unit 及其前后各 1 个
    相邻 unit 作为该字段证据（保留上下文）。未定位或值为空的字段 evidence
    置空列表——复核器按现状兜底 document_text（None 模式）或渲染
    "（未提供证据）"（分组模式），不崩溃、不凭空造证据。
    """
    if not units:
        return candidates
    for c in candidates:
        value = (c.get("value") or "").strip()
        if not value:
            c["evidence"] = []
            continue
        head = value[:8]
        idx = _locate_unit(units, head, value)
        if idx is None:
            c["evidence"] = []
            continue
        start, end = max(0, idx - 1), min(len(units), idx + 2)
        c["evidence"] = [dict(u) for u in units[start:end]]
    return candidates


def _locate_unit(units: list[dict], head: str, value: str) -> int | None:
    for i, u in enumerate(units):
        text = u.get("text", "")
        if head and head in text:
            return i
    if len(value) >= 6:
        for i, u in enumerate(units):
            text = u.get("text", "")
            if any(value[j:j + 6] in text for j in range(0, len(value) - 5)):
                return i
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_chunked_review.py -v`
Expected: 全绿

- [ ] **Step 5: calibrate.py export 加 --group-by**

`app/backend/evaluation/calibrate.py` main 的 export 分支：

```python
    p_export.add_argument("--inject-evidence", action="store_true",
                          help="复核前按字段值定位回填证据 units（评估口径修正：复核器吃字段证据=生产形态）")
    p_export.add_argument("--group-by", choices=["field", "section"], default=None,
                          help="复核器分组形态（需与 --inject-evidence 同用；None=一次全量）")
```

在 `args = parser.parse_args(argv)` 之后、export 分支之前加校验：

```python
    if args.command == "export" and args.group_by and not args.inject_evidence:
        parser.error("--group-by 需要同时指定 --inject-evidence（分组模式以字段证据为输入）")
```

export 循环体改为：

```python
        from ..services.copd_extraction.verifier import FieldVerifier
        from .chunked_review import inject_field_evidence, units_from_ocr_text
        verifier = FieldVerifier(llm_client)
        items = []
        for sample in samples:
            result = run_pipeline(_input_for(sample, schema), llm_client, verifier=verifier)
            if result.get("error"):
                continue
            candidates = result["candidates"]
            if args.inject_evidence:
                candidates = inject_field_evidence(
                    candidates, units_from_ocr_text(sample.get("ocr_text") or "")
                )
            by_key = {c["field_key"]: c for c in candidates}
            for v in verifier.verify(candidates, sample.get("ocr_text") or "", group_by=args.group_by):
                field = by_key.get(v["field_key"]) or {}
                items.append({
                    "case_id": sample.get("case_id"),
                    "field_key": v["field_key"],
                    "verdict": v["verdict"],
                    "reason_code": v["reason_code"],
                    "comment": v["comment"],
                    "value": field.get("value", ""),
                    "evidence_text": "；".join(
                        (e.get("text") or "") for e in (field.get("evidence") or [])[:3]
                    ),
                })
        export_verdicts_file(items, Path(args.out))
```

注意：① `group_by=args.group_by` 统一传参（None 时 verify 走现状分支，行为与之前完全一致）；② 未注入证据时导出 `evidence_text` 为空（基线₁ 现状行为不变），注入后带上 units 文本前 3 条（judge 包可自足）；③ 注入只影响复核调用与导出的 evidence_text，`run_pipeline` 抽取阶段不受影响（基线₁/基线₂/A/B 四臂抽取结果相同）。

- [ ] **Step 6: 回归既有测试 + Commit**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_verifier.py app/backend/tests/test_evaluation_chunked_review.py -v`
Expected: 全绿

```bash
git add app/backend/evaluation/chunked_review.py app/backend/evaluation/calibrate.py app/backend/tests/test_evaluation_chunked_review.py
git commit -m "feat:评估侧证据注入(值定位回填evidence units)+calibrate分臂参数group-by+单测"
```

**验证:** 新单测全绿；`calibrate export --help` 显示 `--group-by {field,section}`；不传 `--group-by` 时行为与 Task 1 之前一致（None 分支）。

---

### Task 3: step6 实验执行 + 增量裁定复用（协调者执行，不入 subagent）

- [ ] 基线₁ = step5 复用（不重跑）：verdicts 用 `20260802_verdicts_step5_A.json`，裁定用 `20260802_adjudications_ai_step5.json`（温度 0.0 + 同输入 → 复核器输出确定性相同）
- [ ] 三臂 verdicts 导出（每臂 1 份，口径同 step5 的 284 条）：
  - 基线₂：`conda run -n manzufei_ocr python -m app.backend.evaluation.calibrate export --schema app/config/schemas/admission_record_structured_fields.v1.yaml --model Qwen3.5-4B-AWQ-4bit --base-url http://127.0.0.1:8082/v1 --inject-evidence --out data/evaluation/calibration/20260802_verdicts_step6_base2.json`
  - A 臂：同上 + `--group-by field` → `20260802_verdicts_step6_A.json`
  - B 臂：同上 + `--group-by section` → `20260802_verdicts_step6_B.json`
- [ ] 差异核对：基线₂/A/B 三臂 verdicts 与 step5 verdicts 逐字段对比，列出 verdict 变化字段清单（基线₂ 的差异 = "证据形态"变量影响面；A/B 相对基线₂ 的差异 = "分组"变量影响面）；顺带验证基线₁ 复用前提（温度 0.0 确定性——若抽跑一次与 step5 不一致需停下说明）
- [ ] 增量裁定（spec §6.2）：只对 verdict 与 step5 不同的字段重建 judge 包 items（复用 step5 的 `judge/step5/case_*.json` 的 `ocr_text`）→ 派**同一批** 6 个 AI judge 裁定差异字段 → 合并 step5 裁定得到各臂完整裁定 `20260802_adjudications_ai_step6_{base2,A,B}.json`
- [ ] 对比指标（analyze 脚本同 step5 口径，统一 key 元组 (case_id, field_key)）：
  - kappa（基线₁ vs 基线₂ vs A vs B）
  - **基线₂ vs 基线₁**：评估口径失真量化（生产形态复核器 vs 整篇版复核器）——无论好坏如实记录
  - 漏检：A 类 4 条（吸支性/回流征性/胸状胸/古手）/ B 类 1 条（case_002 pe_eyes 越界）/ C 类 2 条（hpi 时间归属、氧合指数）逐一核对各臂修复与新增
  - 误报：与 step5 的 3 条对比，不显著增加
  - **跨字段矛盾丢失**：hpi_recent_symptoms（39.5℃ 在体温字段证据）在 A/B 臂是否仍被应标——决定是否跑第五臂 C（A/B + 一条全量兜底，spec §6.1）
  - 工程代价：每 case 请求数（分组数）、总 prompt 字符数（system+user 实测，token 按 1 汉字≈1 token 估算）、复核阶段 LLM 调用次数
- [ ] 生成 focus 页（各臂 AI 应标 + 误报 + 拿不准）给用户重点确认
- [ ] 成功标准对照 spec §6.4：A 类至少修复 2 条（A/B vs 基线₂）；B 类 pe_eyes 被标；C 类不新增漏检；误报不显著增；基线₂ vs 基线₁ 失真量化；kappa 提升

### Task 4: HTML 报告（协调者执行）

- [ ] 对比整理：step5 vs step6 三臂（指标 / kappa / 漏检逐条 / 误报 / 跨字段矛盾 / 请求数与 token 实测 / 用户确认结果）→ HTML + markdown 报告，数据留 `data/evaluation/`，不进 git
- [ ] 报告中明确给出"是否值得跑第三臂 C / 是否进入生产 plan"的建议与依据
