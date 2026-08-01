# 评估体系实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立"金标比对 + 字段级指标 + 回归基线"的最小评估闭环，让 prompt / 模型变更可度量。

**Architecture:** 新增 `app/backend/evaluation/` 三个模块（`metrics.py` 确定性比对指标、`runner.py` 管线组装与报告生成、`run_eval.py` CLI），复用现有 `COPDAdmissionQwenFieldPort` 的组件函数（prompt 构建、契约校验、evidence 回填、quality_checks），不改动 `copd_extraction/` 业务代码。金标从 `data/text_data/ground_truth/` 提炼，放 `data/evaluation/golden/`，报告落 `data/evaluation/reports/`。

**Tech Stack:** Python 3.12、pytest、argparse、difflib（标准库）、现有 Qwen vLLM 客户端（`services/algorithm_ports/qwen_vllm_client.py`）。

## Global Constraints

- 系统离线：评估脚本只调用本地 vLLM（`QwenVLLMClient`），不联网、不调云 API。
- 金标/报告放 `data/evaluation/` 下（`data/` 已被 .gitignore / .git/info/exclude 排除，不提交 git）。
- **不改动**：`copd_extraction/` 业务代码、既有 pytest 测试、schema、prompt 契约（`prompts.py` 只读）。
- 评估时 `evidence_units` 传空列表（evidence 生成是算法子系统职责，本计划不涉及）；金标 JSON 不包含 `evidence_ids` 字段。
- 命令统一 `conda run -n manzufei_ocr python ...`；测试不依赖真实 LLM 推理。
- 金标 `status` 只允许 `found` / `not_found` / `uncertain`，与抽取契约一致（见 `docs/Shared/state-enums.md` 与 `admission_contract.py` 的 `_STATUS_TO_EXTRACTION`）。

---

### Task 1: 金标提炼辅助脚本（OCR 差异清单 + 章节切分）

**Files:**
- Create: `scripts/maintenance/extract_golden_helpers.py`
- Create: `data/evaluation/README.md`（说明金标/报告目录用途，仅此一个文件放仓库内文档说明，目录本身不进 git）

**Interfaces:**
- Produces: 命令行工具 `extract_golden_helpers.py --case N --action diff|sections`：
  - `--action diff`：对比 `data/text_data/ground_truth/N.txt` 与 `data/text_data/ocr_results/N.txt`，用 `difflib.SequenceMatcher` 输出错读处清单（逐处：原文片段 → OCR 片段），供人工复核金标时快速定位 OCR 错读。
  - `--action sections`：把 ground_truth 文本按章节标题（主诉/现病史/既往史/个人史/婚育史/月经史/家族史/体温/辅助检查/初步诊断/最后诊断）切分，输出 markdown，供提炼金标时逐段对照 61 字段表。
- Consumes: `data/text_data/ground_truth/*.txt`、`data/text_data/ocr_results/*.txt`（N = 1..6）。

- [ ] **Step 1: 写辅助脚本**

```python
"""金标提炼辅助工具（一次性）：OCR 差异清单 + 章节切分。

用法:
    python scripts/maintenance/extract_golden_helpers.py --case 1 --action diff
    python scripts/maintenance/extract_golden_helpers.py --case 1 --action sections
"""
import argparse
import difflib
import re
from pathlib import Path

GROUND_TRUTH_DIR = Path("data/text_data/ground_truth")
OCR_RESULTS_DIR = Path("data/text_data/ocr_results")

SECTION_TITLES = [
    "主诉", "现病史", "既往史", "个人史", "婚育史", "月经史", "家族史",
    "体温", "辅助检查", "初步诊断", "最后诊断",
]


def load_pair(case: int) -> tuple[str, str]:
    gt = (GROUND_TRUTH_DIR / f"{case}.txt").read_text(encoding="utf-8")
    ocr = (OCR_RESULTS_DIR / f"{case}.txt").read_text(encoding="utf-8")
    return gt, ocr


def print_diff(case: int) -> None:
    gt, ocr = load_pair(case)
    matcher = difflib.SequenceMatcher(None, gt, ocr, autojunk=False)
    print(f"=== case_{case} OCR 差异清单（金标原文 → OCR 读成） ===")
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        left = gt[i1:i2].replace("\n", "⏎")
        right = ocr[j1:j2].replace("\n", "⏎")
        print(f"- 原文「{left[:60]}」 → OCR「{right[:60]}」")


def print_sections(case: int) -> None:
    gt, _ = load_pair(case)
    lines = gt.splitlines()
    print(f"=== case_{case} 章节切分 ===")
    for title in SECTION_TITLES:
        for i, line in enumerate(lines):
            if re.match(rf"^{re.escape(title)}[:：]", line):
                print(f"\n## {title}\n")
                print(line)
                break


def main() -> None:
    parser = argparse.ArgumentParser(description="金标提炼辅助工具")
    parser.add_argument("--case", type=int, required=True, help="病历编号 1..6")
    parser.add_argument("--action", choices=["diff", "sections"], required=True)
    args = parser.parse_args()
    if args.action == "diff":
        print_diff(args.case)
    else:
        print_sections(args.case)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 冒烟运行验证**

Run: `conda run -n manzufei_ocr python scripts/maintenance/extract_golden_helpers.py --case 1 --action diff`
Expected: 输出若干行"原文「…」 → OCR「…」"（例如"沙美特罗替卡松 → 沙美特罗普卡松"级别的内容差异；若个别 case 无差异则输出空清单也算通过）

Run: `conda run -n manzufei_ocr python scripts/maintenance/extract_golden_helpers.py --case 1 --action sections`
Expected: 按章节标题输出 markdown，每章对应 ground_truth 中的一行

- [ ] **Step 3: 写 data/evaluation/README.md**

```markdown
# data/evaluation/

评估体系的运行数据目录（不进 git）：

- `golden/`：字段级金标样本 `case_001.json` ~ `case_006.json`，格式见
  `docs/superpowers/specs/2026-08-01-evaluation-harness-design.md` 第 3 节。
- `reports/`：评估报告 `<日期>_<prompt版本>_<模型>.json`，首次跑通后另存
  `baseline_<prompt版本>.json` 作为回归基线。
```

- [ ] **Step 3b: 把 data/evaluation/ 加入 .gitignore**（与 data/uploads/ 等现有模式一致）

修改 `.gitignore` 第 39 行 `data/algorithm_jobs/*` 之后追加：

```
data/evaluation/*
!data/evaluation/README.md
```

- [ ] **Step 4: 提交**

```bash
git add scripts/maintenance/extract_golden_helpers.py data/evaluation/README.md .gitignore
git commit -m "feat:金标提炼辅助脚本(OCR差异清单/章节切分) 忽略data/evaluation"
```

---

### Task 2: 指标比对模块 metrics.py

**Files:**
- Create: `app/backend/evaluation/__init__.py`（空文件，使 `python -m app.backend.evaluation.*` 可运行）
- Create: `app/backend/evaluation/metrics.py`
- Test: `app/backend/tests/test_evaluation_metrics.py`

**Interfaces:**
- Consumes: 无（纯函数模块）。
- Produces:
  - `normalize_text(text: str) -> str`：全角→半角、去空白、去标点（保留汉字/字母/数字/`·`/`-`/`/`/`%`/`.`）。
  - `compare_value(golden_value: str, predicted_value: str) -> str`：返回 `"exact" | "substring" | "mismatch"`（空值对空值 = `"exact"`）。
  - `value_located_in_text(value: str, ocr_text: str, ocr_correction_applied: bool = False) -> bool`：value 是否在 ocr_text 中可定位；空 value 恒为 True；`ocr_correction_applied=True` 时豁免判定（受控纠偏不记幻觉）。
  - `status_matches(golden_status: str, predicted_status: str) -> bool`：`found/not_found/uncertain` 严格相等；`uncertain` 金标只比对 status（value 不判）。

- [ ] **Step 1: 写失败测试**

```python
"""评估指标模块单测（合成数据，不依赖真实 LLM）。"""
import pytest

from app.backend.evaluation.metrics import (
    compare_value,
    normalize_text,
    status_matches,
    value_located_in_text,
)


class TestNormalizeText:
    def test_fullwidth_to_halfwidth(self):
        assert normalize_text("血压：１３６/６８ｍｍＨｇ") == normalize_text("血压:136/68mmHg")

    def test_strip_whitespace_and_punctuation(self):
        assert normalize_text(" 反复咳嗽，咳痰20年。 ") == normalize_text("反复咳嗽咳痰20年")

    def test_keep_crucial_symbols(self):
        # 数值相关符号 / - % . 必须保留，否则数值比对失真
        assert normalize_text("136/68mmHg") == normalize_text("136/68mmHg")
        assert normalize_text("10-20口/日") == normalize_text("10-20口/日")
        assert normalize_text("+10^9/L") == normalize_text("+109/L")  # ^ 视为标点去掉

    def test_blank_inputs(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestCompareValue:
    def test_exact_after_normalize(self):
        assert compare_value("反复咳嗽、咳痰20年", "反复咳嗽，咳痰20年") == "exact"

    def test_substring_both_directions(self):
        assert compare_value("反复咳嗽、咳痰20年，喘累2年", "反复咳嗽、咳痰20年") == "substring"
        assert compare_value("高血压", "有高血压病史1年余") == "substring"

    def test_mismatch(self):
        assert compare_value("否认糖尿病病史", "有糖尿病病史") == "mismatch"

    def test_empty_both_exact(self):
        assert compare_value("", "") == "exact"


class TestValueLocatedInText:
    OCR = "体温:36.6℃ 脉搏:99次/分 呼吸:20次/分 血压:136/68mmHg"

    def test_value_in_ocr(self):
        assert value_located_in_text("脉搏:99次/分", self.OCR)

    def test_value_not_in_ocr_is_hallucination(self):
        assert not value_located_in_text("胸痛3天", self.OCR)

    def test_empty_value_never_hallucination(self):
        assert value_located_in_text("", self.OCR)

    def test_ocr_correction_exempts(self):
        assert value_located_in_text("沙美特罗替卡松", "沙美特罗普卡松", ocr_correction_applied=True)


class TestStatusMatches:
    def test_equal_statuses(self):
        assert status_matches("found", "found")
        assert status_matches("not_found", "not_found")

    def test_different_statuses(self):
        assert not status_matches("found", "not_found")
        assert not status_matches("not_found", "found")
        assert not status_matches("uncertain", "found")

    def test_uncertain_golden_compares_status_only(self):
        # uncertain 金标的 value 不做严格比对，仅 status 计入（spec 第 4 节）
        assert status_matches("uncertain", "uncertain")
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_metrics.py -q`
Expected: FAIL（ModuleNotFoundError: app.backend.evaluation.metrics）

- [ ] **Step 3: 实现 metrics.py**

```python
"""评估指标模块：确定性金标比对（不依赖 LLM 打分）。

指标语义见 docs/superpowers/specs/2026-08-01-evaluation-harness-design.md 第 4 节：
- compare_value: 归一化一致 → exact；互为子串 → substring；否则 mismatch。
- value_located_in_text: 幻觉判定（value 必须在 ocr_text 中可定位）。
- status_matches: found/not_found/uncertain 严格比对。
"""
import re
import unicodedata

_KEEP = r"\w一-鿿·\-/%.+"


def normalize_text(text: str | None) -> str:
    """归一化：全角→半角、去空白、去标点。

    保留汉字、字母、数字与数值关键符号（· - / % . +），
    使数值类字段（136/68mmHg、10-20口/日）比对不失真。
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\s　]+", "", t)
    t = re.sub(rf"[^{_KEEP}]+", "", t)
    return t


def compare_value(golden_value: str | None, predicted_value: str | None) -> str:
    """value 两级判定：exact / substring / mismatch。"""
    g = normalize_text(golden_value)
    p = normalize_text(predicted_value)
    if g == p:
        return "exact"
    if g and p and (g in p or p in g):
        return "substring"
    return "mismatch"


def value_located_in_text(
    value: str | None,
    ocr_text: str | None,
    ocr_correction_applied: bool = False,
) -> bool:
    """幻觉判定：value 必须在 OCR 原文中可定位。

    空 value 恒 True（not_found 不判幻觉）；应用了 ocr_correction
    的字段豁免（受控纠偏，spec 第 4 节指标 3 例外）。
    """
    if not value:
        return True
    if ocr_correction_applied:
        return True
    v = normalize_text(value)
    return bool(v) and v in normalize_text(ocr_text or "")


def status_matches(golden_status: str, predicted_status: str) -> bool:
    """status 严格比对（found/not_found/uncertain）。"""
    return golden_status == predicted_status
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_metrics.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/backend/evaluation/__init__.py app/backend/evaluation/metrics.py app/backend/tests/test_evaluation_metrics.py
git commit -m "feat:评估指标模块(归一化/两级value判定/幻觉定位/status比对)"
```

---

### Task 3: 管线组装与报告生成 runner.py

**Files:**
- Create: `app/backend/evaluation/runner.py`
- Test: `app/backend/tests/test_evaluation_runner.py`

**Interfaces:**
- Consumes:
  - Task 2: `metrics.py` 全部函数。
  - 现有：`copd_extraction.prompts.build_admission_structured_fields_prompt`、`copd_extraction.admission_contract.validate_qwen_payload`、`map_qwen_fields_to_review_candidates`、`copd_extraction.quality_checks.apply_quality_checks`、`copd_extraction.llm_client.LlmClient`、`errors.AppError`。
- Produces:
  - `run_pipeline(input: dict, llm_client, *, check_contract: bool = True, apply_quality: bool = True) -> dict`：返回 `{"payload": dict, "candidates": list[dict], "error": dict | None}`；契约失败时 `error = {"code": str, "message": str}` 且 `candidates = []`。
  - `evaluate_sample(sample: dict, result: dict) -> dict`：单样本指标分量，结构见下文代码。
  - `build_report(sample_results: list[dict], meta: dict) -> dict`：五指标汇总 + 按字段分组 + 按陷阱类别分组 + 错误明细。

- [ ] **Step 1: 写失败测试**

```python
"""评估 runner 单测：管线组装、消融变体、报告生成（fake client，不依赖真实 LLM）。"""
import json
import pytest

from app.backend.evaluation.runner import build_report, evaluate_sample, run_pipeline


def make_schema():
    return {
        "version": "1.0.0",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": "chief_complaint",
                "group_label": "主诉",
                "fields": [{"field_key": "chief_complaint", "label": "主诉", "review_control": "text"}],
            }
        ],
    }


def make_golden_payload():
    return {
        "schema_version": "1.0.0",
        "document_type": "copd_admission_record",
        "fields": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年", "evidence_ids": []}],
    }


class FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt: str, **kwargs):
        return json.loads(json.dumps(self._payload))


SAMPLE = {
    "case_id": "case_001",
    "ocr_text": "主诉：反复咳嗽、咳痰20年，加重10余天。",
    "pitfalls": ["negation"],
    "golden": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年，加重10余天"}],
}


class TestRunPipeline:
    def test_happy_path_returns_payload_and_candidates(self):
        schema = make_schema()
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
        )
        assert result["error"] is None
        assert result["candidates"][0]["field_key"] == "chief_complaint"
        assert result["candidates"][0]["status"] == "found"

    def test_contract_failure_captured_not_raised(self):
        schema = make_schema()
        bad_payload = {"fields": []}  # 契约非法
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
        )
        assert result["error"] is not None
        assert result["error"]["code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["candidates"] == []

    def test_no_contract_skips_validation(self):
        schema = make_schema()
        bad_payload = {"fields": []}
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
            check_contract=False,
        )
        assert result["error"] is None


class TestEvaluateSample:
    def test_perfect_match(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "反复咳嗽、咳痰20年，加重10余天", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["value_correct"] == 1
        assert result["metrics"]["value_total"] == 1
        assert result["metrics"]["status_correct"] == 1
        assert result["metrics"]["hallucination"] == 0

    def test_status_mismatch_counts(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "not_found",
                "value": "", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["status_correct"] == 0
        assert result["metrics"]["value_correct"] == 0

    def test_contract_error_counts_as_contract_invalid(self):
        result = evaluate_sample(SAMPLE, {
            "payload": {}, "candidates": [],
            "error": {"code": "ALGORITHM_CONTRACT_INVALID", "message": "bad"},
        })
        assert result["metrics"]["contract_invalid"] == 1


class TestBuildReport:
    def test_summary_and_grouping(self):
        report = build_report([evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "完全错误的值", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })], {"model": "qwen", "prompt_version": "v1", "sample_count": 1})
        assert report["metrics"]["value_accuracy"] == 0.0
        assert report["metrics"]["status_accuracy"] == 1.0
        assert report["metrics"]["hallucination_count"] == 1
        assert report["by_field"]["chief_complaint"]["value_total"] == 1
        assert report["by_pitfall"]["negation"]["value_total"] == 1
        assert report["errors"] == [{"case_id": "case_001", "field_key": "chief_complaint", "kind": "value_mismatch"}]
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py -q`
Expected: FAIL（ModuleNotFoundError: app.backend.evaluation.runner）

- [ ] **Step 3: 实现 runner.py**

```python
"""评估管线组装与报告生成。

默认管线与 COPDAdmissionQwenFieldPort.extract 行为一致（prompt → LLM →
契约校验 → evidence 回填 → quality_checks）；消融变体通过 check_contract /
apply_quality 开关控制（spec 第 5 节）。契约失败不抛出，捕获为 error。
"""
from dataclasses import asdict

from ..services.copd_extraction.admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)
from ..services.copd_extraction.prompts import build_admission_structured_fields_prompt
from ..services.copd_extraction.quality_checks import apply_quality_checks
from ...errors import AppError
from .metrics import compare_value, status_matches, value_located_in_text

FIELD_STATUSES = ("found", "not_found", "uncertain")


def run_pipeline(
    input: dict,
    llm_client,
    *,
    check_contract: bool = True,
    apply_quality: bool = True,
) -> dict:
    """跑单条样本的抽取管线，返回 payload / candidates / error。"""
    schema = input.get("schema") or {}
    document_result = input.get("document_result") or {}
    evidence_units = input.get("evidence_units") or []
    document_text = document_result.get("merged_text") or ""

    prompt = build_admission_structured_fields_prompt(
        schema=schema,
        evidence_units=evidence_units,
        document_text=document_text,
    )
    try:
        payload = llm_client.complete_json(prompt)
    except AppError as exc:
        return {"payload": {}, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    if check_contract:
        try:
            validate_qwen_payload(payload, schema)
        except AppError as exc:
            return {"payload": payload, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    candidates = map_qwen_fields_to_review_candidates(payload, schema, evidence_units=evidence_units)
    if apply_quality:
        candidates = apply_quality_checks(
            candidates, document_text, include_document_flags=False
        )
    return {"payload": payload, "candidates": candidates, "error": None}


def evaluate_sample(sample: dict, result: dict) -> dict:
    """单样本指标分量。candidates 与金标按 field_key 对齐。"""
    golden_by_key = {f["field_key"]: f for f in sample.get("golden", [])}
    candidates_by_key = {c["field_key"]: c for c in result.get("candidates", [])}
    ocr_text = sample.get("ocr_text") or ""

    sample_metrics = {
        "case_id": sample.get("case_id"),
        "value_correct": 0, "value_total": 0,
        "status_correct": 0, "status_total": 0,
        "hallucination": 0, "contract_invalid": 0, "errors": [],
    }
    if result.get("error"):
        sample_metrics["contract_invalid"] = 1
        return sample_metrics

    for field_key, golden in golden_by_key.items():
        candidate = candidates_by_key.get(field_key)
        if candidate is None:
            continue
        golden_status = golden.get("status")
        predicted_status = candidate.get("status")
        if golden_status not in FIELD_STATUSES:
            continue
        # status 指标
        sample_metrics["status_total"] += 1
        if status_matches(golden_status, predicted_status):
            sample_metrics["status_correct"] += 1
        else:
            sample_metrics["errors"].append(
                {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "status_mismatch"}
            )
        # value 指标（not_found 金标不做 value 比对；uncertain 仅 status）
        golden_value = golden.get("value", "")
        predicted_value = candidate.get("value", "")
        correction_applied = bool((candidate.get("ocr_correction") or {}).get("applied"))
        if golden_status == "not_found":
            if predicted_value != "":
                sample_metrics["errors"].append(
                    {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_not_empty_when_not_found"}
                )
            continue
        if golden_status == "uncertain":
            continue
        sample_metrics["value_total"] += 1
        verdict = compare_value(golden_value, predicted_value)
        if verdict in ("exact", "substring"):
            sample_metrics["value_correct"] += 1
        else:
            sample_metrics["errors"].append(
                {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_mismatch"}
            )
        # 幻觉（veto）：value 必须在 OCR 原文可定位
        if not value_located_in_text(predicted_value, ocr_text, correction_applied):
            sample_metrics["hallucination"] += 1
            sample_metrics["errors"].append(
                {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "hallucination"}
            )
    return sample_metrics


def build_report(sample_results: list[dict], meta: dict) -> dict:
    """汇总五指标 + 按字段分组 + 按陷阱类别分组 + 错误明细。"""
    total = {
        "value_correct": 0, "value_total": 0,
        "status_correct": 0, "status_total": 0,
        "hallucination": 0, "contract_invalid": 0,
    }
    by_field: dict[str, dict] = {}
    by_pitfall: dict[str, dict] = {}
    errors: list[dict] = []

    # sample_results 需要携带 sample（case_id/pitfalls）与指标分量；由调用方在
    # evaluate_sample 后补上 pitfalls 再传入，见 run_eval 的组装（Task 4）。
    for r in sample_results:
        metrics = r["metrics"]
        for key in total:
            total[key] += metrics.get(key, 0)
        errors.extend(metrics.get("errors", []))
        for f in r.get("field_totals", []):
            d = by_field.setdefault(f["field_key"], {"value_correct": 0, "value_total": 0})
            d["value_total"] += f["value_total"]
            d["value_correct"] += f["value_correct"]
        for pitfall in r.get("pitfalls", []):
            d = by_pitfall.setdefault(pitfall, {"value_correct": 0, "value_total": 0})
            d["value_total"] += r["metrics"]["value_total"]
            d["value_correct"] += r["metrics"]["value_correct"]

    return {
        "meta": meta,
        "metrics": {
            "status_accuracy": _safe_div(total["status_correct"], total["status_total"]),
            "value_accuracy": _safe_div(total["value_correct"], total["value_total"]),
            "hallucination_count": total["hallucination"],
            "contract_invalid_count": total["contract_invalid"],
            "task_success_count": sum(
                1 for r in sample_results
                if r["metrics"]["contract_invalid"] == 0
                and r["metrics"]["status_total"] > 0
                and r["metrics"]["status_correct"] == r["metrics"]["status_total"]
                and r["metrics"]["value_correct"] == r["metrics"]["value_total"]
                and r["metrics"]["hallucination"] == 0
            ),
            "sample_count": len(sample_results),
            "noise_bandwidth": _noise_bandwidth(len(sample_results)),
        },
        "by_field": by_field,
        "by_pitfall": by_pitfall,
        "errors": errors,
    }


def _safe_div(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _noise_bandwidth(n: int) -> float:
    """√(p(1-p)/n) 取 p=0.5 的最大带宽，标注样本量级噪声。"""
    return round(0.5 / (n ** 0.5), 4) if n else 0.0
```

`evaluate_sample` 返回包裹结构 `{"metrics": {...}, "field_totals": [...], "pitfalls": [...]}`，`build_report` 消费该结构。实现如下（与 Step 1 测试断言一致）：

```python
def evaluate_sample(sample: dict, result: dict) -> dict:
    golden_by_key = {f["field_key"]: f for f in sample.get("golden", [])}
    candidates_by_key = {c["field_key"]: c for c in result.get("candidates", [])}
    ocr_text = sample.get("ocr_text") or ""
    metrics = {
        "value_correct": 0, "value_total": 0,
        "status_correct": 0, "status_total": 0,
        "hallucination": 0, "contract_invalid": 0, "errors": [],
    }
    field_totals: list[dict] = []
    if result.get("error"):
        metrics["contract_invalid"] = 1
        return {"metrics": metrics, "field_totals": field_totals, "pitfalls": sample.get("pitfalls", [])}
    for field_key, golden in golden_by_key.items():
        candidate = candidates_by_key.get(field_key)
        if candidate is None:
            continue
        golden_status = golden.get("status")
        predicted_status = candidate.get("status")
        if golden_status not in FIELD_STATUSES:
            continue
        metrics["status_total"] += 1
        if status_matches(golden_status, predicted_status):
            metrics["status_correct"] += 1
        else:
            metrics["errors"].append({"case_id": sample.get("case_id"), "field_key": field_key, "kind": "status_mismatch"})
        golden_value = golden.get("value", "")
        predicted_value = candidate.get("value", "")
        correction_applied = bool((candidate.get("ocr_correction") or {}).get("applied"))
        if golden_status == "not_found":
            if predicted_value != "":
                metrics["errors"].append({"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_not_empty_when_not_found"})
            continue
        if golden_status == "uncertain":
            continue
        metrics["value_total"] += 1
        field_totals.append({"field_key": field_key, "value_correct": 0, "value_total": 1})
        verdict = compare_value(golden_value, predicted_value)
        if verdict in ("exact", "substring"):
            metrics["value_correct"] += 1
            field_totals[-1]["value_correct"] = 1
        else:
            metrics["errors"].append({"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_mismatch"})
        if not value_located_in_text(predicted_value, ocr_text, correction_applied):
            metrics["hallucination"] += 1
            metrics["errors"].append({"case_id": sample.get("case_id"), "field_key": field_key, "kind": "hallucination"})
    return {"metrics": metrics, "field_totals": field_totals, "pitfalls": sample.get("pitfalls", [])}
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_runner.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/backend/evaluation/runner.py app/backend/tests/test_evaluation_runner.py
git commit -m "feat:评估管线组装与报告生成(消融开关/五指标汇总/分组诊断)"
```

---

### Task 4: run_eval CLI

**Files:**
- Create: `app/backend/evaluation/run_eval.py`
- Test: `app/backend/tests/test_evaluation_run_eval.py`

**Interfaces:**
- Consumes: Task 3 `run_pipeline` / `evaluate_sample` / `build_report`；现有 `QwenVLLMClient`（`services/algorithm_ports/qwen_vllm_client.py`）、`OpenAICompatibleJsonClient`、`copd_extraction.prompts.ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION`、`services.schema_loader.load_schema`。
- Produces: CLI：
  ```
  python -m app.backend.evaluation.run_eval \
      --golden-dir data/evaluation/golden \
      --base-url http://localhost:8000/v1 \
      --model Qwen/Qwen3-14B \
      [--max-tokens 8192] [--temperature 0.0]
      [--no-quality-flags] [--no-contract]
      [--report-dir data/evaluation/reports]
      [--compare <基线报告.json>]
  ```
  报告落盘 `<report-dir>/<日期>_<prompt版本>_<模型>.json`；`--compare` 时额外输出指标 diff 表。

- [ ] **Step 1: 写失败测试（冒烟，不真实推理）**

```python
"""run_eval CLI 冒烟：fake client 注入验证脚本链路，不依赖真实 LLM。"""
import json

from app.backend.evaluation import run_eval


def test_cli_end_to_end_with_fake_client(tmp_path, monkeypatch):
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(
        "version: 1.0.0\n"
        "document_type: copd_admission_record\n"
        "field_groups:\n"
        "  - group_key: chief_complaint\n"
        "    group_label: 主诉\n"
        "    fields:\n"
        "      - field_key: chief_complaint\n"
        "        label: 主诉\n",
        encoding="utf-8",
    )
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    (golden_dir / "case_001.json").write_text(json.dumps({
        "case_id": "case_001",
        "ocr_text": "主诉：反复咳嗽、咳痰20年。",
        "pitfalls": ["negation"],
        "golden": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年"}],
    }, ensure_ascii=False), encoding="utf-8")
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    class FakeClient:
        def complete_json(self, prompt, **kwargs):
            return {"schema_version": "1.0.0", "document_type": "copd_admission_record",
                    "fields": [{"field_key": "chief_complaint", "status": "found",
                                "value": "反复咳嗽、咳痰20年", "evidence_ids": []}]}
        def close(self):
            pass

    monkeypatch.setattr(run_eval, "build_llm_client", lambda args: FakeClient())
    report_path = run_eval.main([
        "--golden-dir", str(golden_dir),
        "--schema", str(schema_path),
        "--model", "fake-model",
        "--report-dir", str(report_dir),
    ])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["value_accuracy"] == 1.0
    assert report["meta"]["model"] == "fake-model"
```

- [ ] **Step 2: 运行确认失败**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_run_eval.py -q`
Expected: FAIL（ModuleNotFoundError: app.backend.evaluation.run_eval）

- [ ] **Step 3: 实现 run_eval.py**

```python
"""评估 CLI：跑金标样本、出报告、支持消融与基线对比。

用法见模块 docstring 与 docs/superpowers/plans/2026-08-01-evaluation-harness-implementation-plan.md
Task 4。默认管线与 COPDAdmissionQwenFieldPort.extract 一致；消融参数
--no-quality-flags / --no-contract 走 run_pipeline 变体。
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
from ..services.copd_extraction.llm_client import OpenAICompatibleJsonClient
from ..services.copd_extraction.prompts import ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION
from ..services.schema_loader import load_schema
from .runner import build_report, evaluate_sample, run_pipeline


def build_llm_client(args) -> OpenAICompatibleJsonClient:
    qwen_client = QwenVLLMClient(
        base_url=args.base_url,
        model=args.model,
        api_key="not-needed",
        timeout_seconds=360,
    )
    return OpenAICompatibleJsonClient(qwen_client, max_tokens=args.max_tokens, temperature=args.temperature)


def load_golden_samples(golden_dir: Path) -> list[dict]:
    samples = []
    for path in sorted(golden_dir.glob("case_*.json")):
        samples.append(json.loads(path.read_text(encoding="utf-8")))
    return samples


def _input_for(sample: dict, schema: dict) -> dict:
    return {
        "schema": schema,
        "document_result": {"merged_text": sample.get("ocr_text") or ""},
        "evidence_units": [],
    }


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="COPD 病历抽取评估")
    parser.add_argument("--golden-dir", default="data/evaluation/golden")
    parser.add_argument("--schema", required=True, help="admission_record_structured_fields.v1.yaml 路径")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--report-dir", default="data/evaluation/reports")
    parser.add_argument("--no-quality-flags", action="store_true")
    parser.add_argument("--no-contract", action="store_true")
    parser.add_argument("--compare", default=None, help="基线报告 JSON 路径，输出指标 diff")
    args = parser.parse_args(argv)

    schema = load_schema(args.schema)
    samples = load_golden_samples(Path(args.golden_dir))
    if not samples:
        print(f"未找到金标样本: {args.golden_dir}", file=sys.stderr)
        raise SystemExit(1)

    llm_client = build_llm_client(args)
    sample_results = []
    for sample in samples:
        result = run_pipeline(
            _input_for(sample, schema),
            llm_client,
            check_contract=not args.no_contract,
            apply_quality=not args.no_quality_flags,
        )
        sample_results.append(evaluate_sample(sample, result))

    meta = {
        "model": args.model,
        "prompt_version": ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION,
        "schema_version": schema.get("version", ""),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "ablation": {"quality_flags": not args.no_quality_flags, "contract": not args.no_contract},
        "sample_count": len(samples),
    }
    report = build_report(sample_results, meta)

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{stamp}_{meta['prompt_version']}_{args.model.replace('/', '_')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_console_summary(report)
    if args.compare:
        _print_compare(Path(args.compare), report)
    print(f"\n报告已写入: {report_path}")
    return report_path


def _print_console_summary(report: dict) -> None:
    m = report["metrics"]
    print("=" * 46)
    print(f"评估报告  {report['meta']['model']} / {report['meta']['prompt_version']}")
    print("=" * 46)
    print(f"样本数          : {m['sample_count']}   (噪声带宽 ±{m['noise_bandwidth']})")
    print(f"status 准确率   : {m['status_accuracy']:.2%}")
    print(f"value 准确率    : {m['value_accuracy']:.2%}")
    print(f"幻觉数(veto)    : {m['hallucination_count']}")
    print(f"契约非法数      : {m['contract_invalid_count']}")
    print(f"任务级成功      : {m['task_success_count']}/{m['sample_count']}")
    if report["by_field"]:
        worst = sorted(report["by_field"].items(), key=lambda kv: kv[1]["value_total"] - kv[1]["value_correct"], reverse=True)[:5]
        print("\n最差字段 top5:")
        for key, d in worst:
            print(f"  {key}: {d['value_correct']}/{d['value_total']}")


def _print_compare(baseline_path: Path, report: dict) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    bm, nm = baseline["metrics"], report["metrics"]
    print("\n=== 与基线对比 ===")
    print(f"基线: {baseline_path.name}")
    for k in ("status_accuracy", "value_accuracy"):
        diff = nm[k] - bm[k]
        print(f"  {k}: {bm[k]:.2%} → {nm[k]:.2%} ({diff:+.2%})")
    for k in ("hallucination_count", "contract_invalid_count"):
        print(f"  {k}: {bm[k]} → {nm[k]} ({nm[k] - bm[k]:+d})")
    b_errs = {(e['case_id'], e['field_key']) for e in baseline.get("errors", [])}
    n_errs = {(e['case_id'], e['field_key']) for e in report.get("errors", [])}
    new_errs = sorted(n_errs - b_errs)
    fixed = sorted(b_errs - n_errs)
    print(f"  新增错误: {len(new_errs)}  已修复: {len(fixed)}")
    for e in new_errs:
        print(f"    + {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evaluation_run_eval.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/backend/evaluation/run_eval.py app/backend/tests/test_evaluation_run_eval.py
git commit -m "feat:评估CLI(金标加载/模型替换/消融参数/报告落盘/基线对比)"
```

---

### Task 5: 提炼 6 份字段级金标

**Files:**
- Create: `data/evaluation/golden/case_001.json` ~ `case_006.json`（data/ 下，不进 git）

**Interfaces:**
- Consumes: Task 1 辅助脚本（OCR 差异清单 + 章节切分）；`data/text_data/ground_truth/1-6.txt`；`data/text_data/ocr_results/1-6.txt`；schema 61 字段表。
- Produces: 6 份完整金标（覆盖 schema 全部 61 字段；`status` 只允许 found/not_found/uncertain；value 为 OCR 原文可定位的摘录；不含 evidence_ids）。

- [ ] **Step 1: 生成辅助产物**

Run: `for i in 1 2 3 4 5 6; do conda run -n manzufei_ocr python scripts/maintenance/extract_golden_helpers.py --case $i --action diff; done > /tmp/ocr_diffs.txt`
Expected: 6 份 OCR 差异清单（错读处逐条列出）

Run: `for i in 1 2 3 4 5 6; do conda run -n manzufei_ocr python scripts/maintenance/extract_golden_helpers.py --case $i --action sections; done > /tmp/sections.txt`
Expected: 6 份章节切分 markdown

- [ ] **Step 2: 提炼金标初稿（实施者语义提炼）**

实施者逐份读 ground_truth 全文 + 章节切分 + OCR 差异清单，按 61 字段表提炼 JSON：
- `found`：原文明确出现该字段语义，value 从 OCR 原文摘录（错读处保留 OCR 原文写法）；
- `not_found`：原文未提及，value 为空字符串；
- `uncertain`：疑似找到但 OCR/上下文不确定（医生需重点核验的场景）；
- 否定表达字段（pmh_diabetes 等）必须保留否定词（如"否认糖尿病病史"）；
- 诊断字段按编号分行保留；
- 每份标注 `pitfalls`（见 spec 第 3 节六类）。
每份写完运行 JSON 校验：

Run: `conda run -n manzufei_ocr python -c "import json; [json.load(open(f'data/evaluation/golden/case_{i:03d}.json')) for i in range(1,7)]; print('JSON 合法')"`

- [ ] **Step 3: 用户复核 gate（暂停点）**

将 6 份金标 + OCR 差异清单交给用户复核，重点裁定：OCR 错读处的预期输出（保留原文 / uncertain / ocr_correction 豁免）。裁定结果回写金标，以裁定为准。
**本步骤必须由用户明确确认后才继续。**

- [ ] **Step 4: 提交**

金标在 `data/evaluation/golden/` 不进 git，无需 commit；如复核过程修改了辅助脚本，单独提交脚本改动。

---

### Task 6: 真实运行与基线快照

**Files:**
- Create: `data/evaluation/reports/baseline_<prompt版本>.json`

**前置条件：** 本地 vLLM 服务可用（`qwen-vision-vllm-server`，base_url 与 run_eval `--base-url` 一致）。

- [ ] **Step 1: 跑真实评估**

Run: `conda run -n manzufei_ocr python -m app.backend.evaluation.run_eval --golden-dir data/evaluation/golden --schema app/config/schemas/admission_record_structured_fields.v1.yaml --base-url http://localhost:8000/v1 --model <实际模型名>`
Expected: 控制台输出五指标汇总；报告 JSON 落盘 reports/

- [ ] **Step 2: 存基线**

Run: `cp data/evaluation/reports/<最新报告>.json data/evaluation/reports/baseline_<prompt版本>.json`
Expected: 基线文件存在

- [ ] **Step 3: 观察报告并记录**（不提交 git）

阅读报告：value 准确率、status 准确率、幻觉数、契约非法数；按字段分组定位最差字段；按陷阱类别分组定位最难病历类别。记录到任务说明中，供第二步"验证器规范化"参考。

---

## Self-Review 记录

- **Spec 覆盖**：第 3 节评估集 → Task 1（辅助）+ Task 5（金标）；第 4 节五指标 → Task 2/3；第 5 节执行与消融 → Task 3/4；第 6 节报告与回归 → Task 4（--compare）+ Task 6（基线）；第 7 节复用与不改动 → Global Constraints；第 8 节测试约定 → Task 2/3/4 的 pytest。金标 source 标注（manual|review）在第一步不实施（边界决定），后续第二步启用。
- **占位符扫描**：无 TBD/TODO；Task 5 的语义提炼步骤明确"实施者逐份读文本提炼"的规则清单（错读保留原文、否定保留否定词、诊断编号分行）。
- **类型一致性**：`evaluate_sample` 返回包裹结构 `{"metrics", "field_totals", "pitfalls"}`，`build_report` 消费同结构；`run_pipeline` 返回 `{"payload", "candidates", "error"}`；CLI 测试与实现签名一致。
