# COPD Field Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the incorrect generic medical-record field extraction path with an in-repo COPD/respiratory admission-record extraction pipeline based on `data/temp/Medical_Text3`.

**Architecture:** The backend owns a focused `copd_extraction` module that performs section splitting, prompt-harnessed LLM extraction, thin rule quality checks, verifier orchestration, field-result validation, and review metadata preservation. The extractor returns one full field result per schema field, including empty/not-found fields, verification status, quality flags, and OCR correction audit metadata.

**Tech Stack:** Python 3, Flask backend, pytest, YAML schema config, `llama-cpp-python` behind an injectable adapter, existing JSON storage and task/review services.

**Required Working Directory:** `/home/kbzz1/manzufei_ocr/.claude/worktrees/llm-extraction`. Do not implement this plan in `/home/kbzz1/manzufei_ocr` directly.

---

## File Structure

- Modify `AGENTS.md` and `CLAUDE.md`: update repository boundary to allow in-repo COPD-specialty rule extraction while keeping OCR/image processing out of scope.
- Modify `docs/产品PRD.md`, `docs/PRD任务清单.md`, `docs/Backend/Backend_BDD/algorithm-integration.md`, `docs/Backend/Backend_TDD/02-algorithm-ports.md`, `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`, `docs/Backend/Backend_TDD/08-schema-management.md`, `docs/Shared/state-enums.md`: align docs with full field results, field-level risk flags, and in-repo COPD extraction.
- Create `app/config/schemas/copd_admission_record.v1.yaml`: authoritative COPD schema.
- Modify `app/backend/__init__.py`: load COPD schema and wire COPD field extraction port.
- Modify `app/backend/services/review_service.py`: preserve extraction metadata, verification status, quality flags, and OCR correction audit data.
- Modify `app/backend/services/algorithm_ports/field_extraction.py`: validate full field result contract.
- Modify `app/backend/services/algorithm_ports/orchestrator.py`: treat full field results as non-empty success if at least one extracted/uncertain field is present; keep task-level failure for invalid/full-empty output.
- Create `app/backend/services/copd_extraction/__init__.py`
- Create `app/backend/services/copd_extraction/schema_mapping.py`: field definitions and nested-to-flat mapping.
- Create `app/backend/services/copd_extraction/section_splitter.py`: normalize and split OCR text into medical sections.
- Create `app/backend/services/copd_extraction/prompts.py`: extraction and verification prompt builders.
- Create `app/backend/services/copd_extraction/llm_client.py`: thin injectable interface for llama.cpp.
- Create `app/backend/services/copd_extraction/field_result.py`: result normalization and validation helpers.
- Create `app/backend/services/copd_extraction/quality_checks.py`: thin rule quality checks.
- Create `app/backend/services/copd_extraction/extractor.py`: orchestrates split -> prompt -> parse -> quality checks -> verifier -> full results.
- Create `app/backend/tests/fixtures/copd_ocr_samples.py`: hand-authored OCR-like sample texts and expected field snapshots.
- Create tests under `app/backend/tests/test_copd_*.py`.
- Modify frontend review display files only after backend contract is stable: likely `app/frontend/src/components/review/FieldList.tsx` and tests.

## Task 1: Documentation Boundary Update

**Files:**
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/Backend/AGENTS.md`
- Modify: `docs/Backend/CLAUDE.md`
- Test: manual `rg` check

- [ ] **Step 1: Update root boundary wording**

Replace the old absolute rule:

```markdown
本仓库不得实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则抽取。
```

with:

```markdown
本仓库不得实现 OCR、图像预处理、裁剪或透视矫正。慢阻肺/呼吸系统入院记录的专病字段抽取、规则分段、薄规则质量核验和本地 LLM prompt harness 属于本仓库核心业务代码；其他病种或通用医学规则引擎不在当前范围内。
```

- [ ] **Step 2: Update backend boundary wording**

In `docs/Backend/AGENTS.md` and `docs/Backend/CLAUDE.md`, replace backend "不负责规则抽取" wording with:

```markdown
后端允许实现慢阻肺/呼吸系统入院记录专病字段抽取，包括规则分段、字段结果归一化、prompt harness、薄规则质量核验和本地 LLM 调用编排。后端仍不实现 OCR、图像预处理、医学诊断建议或通用病种规则引擎。
```

- [ ] **Step 3: Verify no conflicting absolute ban remains**

Run:

```bash
rg -n "不得实现.*规则抽取|不得实现 OCR、LLM 字段抽取|后端不实现.*规则抽取" AGENTS.md CLAUDE.md docs app
```

Expected: no remaining absolute ban that contradicts COPD in-repo extraction.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md CLAUDE.md docs/Backend/AGENTS.md docs/Backend/CLAUDE.md
git commit -m "更新慢阻肺抽取仓库边界"
```

## Task 2: COPD Schema

**Files:**
- Create: `app/config/schemas/copd_admission_record.v1.yaml`
- Modify: `app/backend/__init__.py`
- Test: `app/backend/tests/test_schema_loader.py`

- [ ] **Step 1: Write failing schema loader test**

Add to `app/backend/tests/test_schema_loader.py`:

```python
def test_load_copd_admission_schema_from_repo():
    from app.backend.config import PROJECT_ROOT
    from app.backend.services.schema_loader import load_schema
    import os

    path = os.path.join(PROJECT_ROOT, "app", "config", "schemas", "copd_admission_record.v1.yaml")

    schema = load_schema(path)

    assert schema["document_type"] == "copd_admission_record"
    keys = [
        field["field_key"]
        for group in schema["field_groups"]
        for field in group["fields"]
    ]
    assert "copd_history_years" in keys
    assert "blood_gas_pao2" in keys
    assert "ct_features" in keys
    assert len(keys) == len(set(keys))
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py::test_load_copd_admission_schema_from_repo -q
```

Expected: FAIL because `copd_admission_record.v1.yaml` does not exist.

- [ ] **Step 3: Add COPD schema**

Create `app/config/schemas/copd_admission_record.v1.yaml`:

```yaml
version: "1.0.0"
document_type: copd_admission_record
field_groups:
  - group_key: patient_profile
    group_label: 患者背景
    fields:
      - field_key: occupation
        label: 职业
        type: string
      - field_key: smoking_history_raw_text
        label: 吸烟史原文
        type: string
      - field_key: smoking_history_status
        label: 吸烟状态
        type: string
      - field_key: copd_history_years
        label: 慢阻肺/慢性咳喘病程
        type: string
      - field_key: baseline_lung_function
        label: 基线肺功能
        type: string
      - field_key: maintenance_therapy
        label: 长期维持治疗
        type: string
  - group_key: exacerbation_signals
    group_label: 急性加重信号
    fields:
      - field_key: cough_sputum_change
        label: 咳嗽咳痰变化
        type: string
      - field_key: dyspnea_grade_mMRC
        label: 呼吸困难程度/mMRC
        type: string
      - field_key: treatment_failure
        label: 既往或本次治疗效果不佳
        type: string
      - field_key: weight_loss
        label: 体重下降
        type: string
      - field_key: gi_symptoms
        label: 胃肠道症状
        type: string
      - field_key: comorbidities
        label: 合并症
        type: string
  - group_key: physical_exam
    group_label: 体格检查
    fields:
      - field_key: temperature
        label: 体温
        type: string
      - field_key: pulse
        label: 脉搏
        type: string
      - field_key: respiration
        label: 呼吸
        type: string
      - field_key: blood_pressure
        label: 血压
        type: string
      - field_key: bmi
        label: BMI
        type: string
      - field_key: positive_signs
        label: 阳性体征
        type: string
  - group_key: auxiliary_exam
    group_label: 辅助检查
    fields:
      - field_key: blood_gas_ph
        label: 血气 pH
        type: string
      - field_key: blood_gas_pao2
        label: 血气 PaO2/PO2
        type: string
      - field_key: blood_gas_paco2
        label: 血气 PaCO2/PCO2
        type: string
      - field_key: electrolyte_imbalance
        label: 电解质异常
        type: string
      - field_key: wbc
        label: 白细胞
        type: string
      - field_key: crp
        label: C 反应蛋白
        type: string
      - field_key: ct_features
        label: 胸部 CT 语义
        type: string
```

- [ ] **Step 4: Wire default schema path**

In `app/backend/__init__.py`, change the schema file name from:

```python
"medical_record.v1.yaml"
```

to:

```python
"copd_admission_record.v1.yaml"
```

- [ ] **Step 5: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py::test_load_copd_admission_schema_from_repo -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/config/schemas/copd_admission_record.v1.yaml app/backend/__init__.py app/backend/tests/test_schema_loader.py
git commit -m "新增慢阻肺专病字段 schema"
```

## Task 3: Field Result Contract

**Files:**
- Modify: `app/backend/services/algorithm_ports/field_extraction.py`
- Test: `app/backend/tests/test_field_extraction_port.py`

- [ ] **Step 1: Write failing tests for full field result metadata**

Add to `app/backend/tests/test_field_extraction_port.py`:

```python
import pytest


def _valid_field_result():
    return {
        "field_key": "copd_history_years",
        "original_value": "15年",
        "evidence": "反复咳嗽、咳痰15年",
        "confidence": 0.9,
        "source_section": "主诉",
        "extraction_status": "extracted",
        "verification_status": "passed",
        "quality_flags": [],
        "ocr_correction": {
            "applied": False,
            "raw": "反复咳嗽、咳痰15年",
            "normalized": "反复咳嗽、咳痰15年",
            "reason": "",
        },
    }


def test_validate_field_result_accepts_full_metadata():
    from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates

    validate_field_candidates([_valid_field_result()])


def test_validate_field_result_rejects_missing_ocr_correction():
    from app.backend.errors import AppError
    from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates

    item = _valid_field_result()
    del item["ocr_correction"]

    with pytest.raises(AppError):
        validate_field_candidates([item])


def test_validate_field_result_rejects_invalid_status():
    from app.backend.errors import AppError
    from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates

    item = _valid_field_result()
    item["verification_status"] = "maybe"

    with pytest.raises(AppError):
        validate_field_candidates([item])
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py -q
```

Expected: FAIL because current validator does not require new fields.

- [ ] **Step 3: Implement minimal validator extension**

In `app/backend/services/algorithm_ports/field_extraction.py`, add constants:

```python
EXTRACTION_STATUSES = {"extracted", "not_found", "uncertain"}
VERIFICATION_STATUSES = {"passed", "suspicious", "failed", "not_checked"}
```

Inside `validate_field_candidates`, after `field_key` and `original_value` checks, add:

```python
        extraction_status = item.get("extraction_status")
        if extraction_status not in EXTRACTION_STATUSES:
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="extraction_status 非法")

        verification_status = item.get("verification_status")
        if verification_status not in VERIFICATION_STATUSES:
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="verification_status 非法")

        quality_flags = item.get("quality_flags")
        if not isinstance(quality_flags, list):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="quality_flags 必须是列表")

        source_section = item.get("source_section")
        if source_section is not None and not isinstance(source_section, str):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="source_section 必须是字符串或 None")

        ocr_correction = item.get("ocr_correction")
        if not isinstance(ocr_correction, dict):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="ocr_correction 必须是对象")
        if not isinstance(ocr_correction.get("applied"), bool):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="ocr_correction.applied 必须是布尔值")
        for key in ("raw", "normalized", "reason"):
            if not isinstance(ocr_correction.get(key), str):
                raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message=f"ocr_correction.{key} 必须是字符串")
        if extraction_status == "extracted" and (not original_value or not item.get("evidence")):
            raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID, message="extracted 字段必须包含值和 evidence")
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/field_extraction.py app/backend/tests/test_field_extraction_port.py
git commit -m "扩展慢阻肺字段结果契约校验"
```

## Task 4: Hand-Written OCR Regression Fixtures

**Files:**
- Create: `app/backend/tests/fixtures/copd_ocr_samples.py`
- Test: `app/backend/tests/test_copd_samples.py`

- [ ] **Step 1: Write failing fixture tests**

Create `app/backend/tests/test_copd_samples.py`:

```python
def test_copd_ocr_samples_cover_required_error_families():
    from app.backend.tests.fixtures.copd_ocr_samples import COPD_OCR_SAMPLES

    families = {family for sample in COPD_OCR_SAMPLES for family in sample["error_families"]}

    assert "indicator_label_ocr" in families
    assert "medication_or_medical_term_ocr" in families
    assert "numeric_unit_range_anomaly" in families
    assert "date_or_institution_ocr" in families
    assert "duplicate_or_stitching" in families
    assert "negation_or_uncertainty" in families
    assert len(COPD_OCR_SAMPLES) >= 5
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_samples.py -q
```

Expected: FAIL because fixture file does not exist.

- [ ] **Step 3: Create sample fixture**

Create `app/backend/tests/fixtures/copd_ocr_samples.py`:

```python
COPD_OCR_SAMPLES = [
    {
        "name": "blood_gas_label_ocr",
        "error_families": ["indicator_label_ocr", "numeric_unit_range_anomaly"],
        "text": "辅助检查: 血气分析：pH 7.40、P8276.00mmHg、PCO2 36.00mmHg、F102 21.00、502 98.10%。",
        "expected_flags": ["value_not_in_evidence"],
    },
    {
        "name": "medication_terms_ocr",
        "error_families": ["medication_or_medical_term_ocr"],
        "text": "现病史: 予硫酸氨氯吡格雷片、氨酸氨溴索注射液、复方异丙托溴安溶液治疗后症状缓解不明显。",
        "expected_flags": [],
    },
    {
        "name": "duplicate_stitching",
        "error_families": ["duplicate_or_stitching"],
        "text": "体格检查: 腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。杵状指(趾)，四/部左右对称。",
        "expected_flags": ["possible_duplicate_or_stitching"],
    },
    {
        "name": "date_institution_ocr",
        "error_families": ["date_or_institution_ocr"],
        "text": "既往史: 20天前于合川区人名医院就诊。2028-04-30执行胸部CT检查。",
        "expected_flags": ["suspicious_date"],
    },
    {
        "name": "negation_uncertainty",
        "error_families": ["negation_or_uncertainty"],
        "text": "现病史: 无发热，否认咯血，胸部CT提示炎性结节或增殖灶可能，建议治疗后复查。",
        "expected_flags": ["negation_or_uncertainty_risk"],
    },
]
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_samples.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/fixtures/copd_ocr_samples.py app/backend/tests/test_copd_samples.py
git commit -m "新增慢阻肺 OCR 回归样本"
```

## Task 5: Section Splitter

**Files:**
- Create: `app/backend/services/copd_extraction/__init__.py`
- Create: `app/backend/services/copd_extraction/section_splitter.py`
- Test: `app/backend/tests/test_copd_section_splitter.py`

- [ ] **Step 1: Write failing tests**

Create `app/backend/tests/test_copd_section_splitter.py`:

```python
def test_split_sections_handles_inline_headings():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    text = "主诉:咳嗽15年。现病史:1月前加重。体格检查\n体温:36.7°脉搏:99次/分"

    sections = split_sections(text)

    assert sections["主诉"] == "咳嗽15年。"
    assert sections["现病史"] == "1月前加重。"
    assert "体温:36.7" in sections["体格检查"]


def test_split_sections_returns_full_text_when_no_heading():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    sections = split_sections("反复咳嗽咳痰15年")

    assert sections["全文"] == "反复咳嗽咳痰15年"
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_section_splitter.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement section splitter**

Create `app/backend/services/copd_extraction/__init__.py` as empty file.

Create `app/backend/services/copd_extraction/section_splitter.py`:

```python
import re

HEADINGS = ["主诉", "现病史", "既往史", "个人史", "婚育史", "家族史", "体格检查", "辅助检查"]


def normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(raw_text: str) -> dict[str, str]:
    text = normalize_text(raw_text)
    pattern = re.compile(rf"(?P<title>{'|'.join(map(re.escape, HEADINGS))})(?:[:：]|\n)")
    matches = list(pattern.finditer(text))
    if not matches:
        return {"全文": text}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group("title")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_section_splitter.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction app/backend/tests/test_copd_section_splitter.py
git commit -m "新增慢阻肺文本分段"
```

## Task 6: Thin Rule Quality Checks

**Files:**
- Create: `app/backend/services/copd_extraction/quality_checks.py`
- Test: `app/backend/tests/test_copd_quality_checks.py`

- [ ] **Step 1: Write failing tests**

Create `app/backend/tests/test_copd_quality_checks.py`:

```python
def _field(field_key: str, value: str, evidence: str):
    return {
        "field_key": field_key,
        "original_value": value,
        "evidence": evidence,
        "confidence": 0.8,
        "source_section": "辅助检查",
        "extraction_status": "extracted",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": evidence, "normalized": evidence, "reason": ""},
    }


def test_quality_check_flags_value_not_in_evidence():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("blood_gas_pao2", "PO2 76.00mmHg", "P8276.00mmHg")]

    result = apply_quality_checks(fields, "辅助检查: P8276.00mmHg")

    assert result[0]["verification_status"] == "suspicious"
    assert result[0]["quality_flags"][0]["flag"] == "value_not_in_evidence"


def test_quality_check_flags_duplicate_stitching():
    from app.backend.services.copd_extraction.quality_checks import document_quality_flags

    text = "腹部软无压痛，四肢活动自如。腹部软无压痛，四肢活动自如。"

    flags = document_quality_flags(text)

    assert any(flag["flag"] == "possible_duplicate_or_stitching" for flag in flags)


def test_quality_check_flags_future_date():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("exam_date", "2028-04-30", "2028-04-30执行胸部CT")]

    result = apply_quality_checks(fields, "2028-04-30执行胸部CT")

    assert result[0]["quality_flags"][0]["flag"] == "suspicious_date"


def test_quality_check_flags_negation_risk():
    from app.backend.services.copd_extraction.quality_checks import apply_quality_checks

    fields = [_field("positive_signs", "咯血", "否认咯血")]

    result = apply_quality_checks(fields, "否认咯血")

    assert result[0]["quality_flags"][0]["flag"] == "negation_or_uncertainty_risk"
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_quality_checks.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement thin checks**

Create `app/backend/services/copd_extraction/quality_checks.py`:

```python
import copy
import re
from datetime import date

NEGATION_OR_UNCERTAIN = ("无", "否认", "未见", "可能", "考虑", "建议复查")


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def _flag(flag: str, message: str, severity: str = "warning") -> dict:
    return {"flag": flag, "severity": severity, "message": message}


def document_quality_flags(text: str) -> list[dict]:
    flags = []
    sentences = [item.strip() for item in re.split(r"[。；;\n]", text or "") if item.strip()]
    seen = set()
    for sentence in sentences:
        if len(sentence) >= 8 and sentence in seen:
            flags.append(_flag("possible_duplicate_or_stitching", "文本中存在高相似重复片段"))
            break
        seen.add(sentence)
    return flags


def _has_suspicious_date(text: str) -> bool:
    current_year = date.today().year
    for year in re.findall(r"(20\d{2})[-年]", text or ""):
        if int(year) > current_year:
            return True
    return False


def apply_quality_checks(fields: list[dict], full_text: str) -> list[dict]:
    checked = copy.deepcopy(fields)
    doc_flags = document_quality_flags(full_text)
    for item in checked:
        item.setdefault("quality_flags", [])
        value = item.get("original_value") or ""
        evidence = item.get("evidence") or ""

        for number in _numbers(value):
            if number not in evidence:
                item["quality_flags"].append(_flag("value_not_in_evidence", "字段值中的数字未能在 evidence 中直接找到"))
                break

        if _has_suspicious_date(value) or _has_suspicious_date(evidence):
            item["quality_flags"].append(_flag("suspicious_date", "日期明显晚于当前日期或与上下文不一致"))

        if any(word in evidence for word in NEGATION_OR_UNCERTAIN) and value and value not in ("", "无", "未见", "否认"):
            item["quality_flags"].append(_flag("negation_or_uncertainty_risk", "evidence 附近存在否定或不确定语气"))

        if doc_flags:
            item["quality_flags"].extend(doc_flags)

        if item["quality_flags"] and item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
    return checked
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_quality_checks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/quality_checks.py app/backend/tests/test_copd_quality_checks.py
git commit -m "新增慢阻肺薄规则质量核验"
```

## Task 7: Prompt Harness Builders

**Files:**
- Create: `app/backend/services/copd_extraction/prompts.py`
- Test: `app/backend/tests/test_copd_prompts.py`

- [ ] **Step 1: Write failing tests**

Create `app/backend/tests/test_copd_prompts.py`:

```python
def test_extraction_prompt_contains_ocr_constraints_and_schema_keys():
    from app.backend.services.copd_extraction.prompts import build_extraction_prompt

    prompt = build_extraction_prompt({"主诉": "咳嗽15年"}, ["copd_history_years", "bmi"])

    assert "不得静默修正 OCR" in prompt
    assert "ocr_correction" in prompt
    assert "copd_history_years" in prompt
    assert "bmi" in prompt
    assert "1/I/l" in prompt
    assert "0/O/o" in prompt


def test_verification_prompt_requires_structured_field_verdicts():
    from app.backend.services.copd_extraction.prompts import build_verification_prompt

    prompt = build_verification_prompt("原文", [{"field_key": "bmi", "original_value": "24.2"}])

    assert "verdict" in prompt
    assert "evidence_supported" in prompt
    assert "numeric_value_preserved" in prompt
    assert "ocr_correction_reasonable" in prompt
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement prompt builders**

Create `app/backend/services/copd_extraction/prompts.py`:

```python
import json


def build_extraction_prompt(sections: dict[str, str], field_keys: list[str]) -> str:
    return f"""
你是慢阻肺/呼吸系统入院记录结构化抽取引擎。
只从 OCR 原文中抽取字段，不得推断原文未写的信息。
字段 key 必须完整覆盖：{json.dumps(field_keys, ensure_ascii=False)}

OCR 风险提示：1/I/l、0/O/o、BHI/BMI、cT/CT/Ct、单位断裂、表格错位、项目和值跨行、冒号和空格丢失、小数点和逗号异常、常见错别字。
硬约束：不得静默修正 OCR；不得改写数值；不得医学换算；不得把“无、否认、未见、可能、考虑、建议复查”等表达改成确定阳性。
如果按上下文理解了 OCR 疑似错误，必须输出 ocr_correction.applied=true、raw、normalized、reason。

输出必须是 JSON 对象，顶层键为 `fields`，`fields` 是数组。每个字段包含：
field_key, original_value, evidence, confidence, source_section, extraction_status, verification_status, quality_flags, ocr_correction。

规则：
- 未抽到字段 original_value=""、evidence=null、extraction_status="not_found"。
- 抽到字段必须保留 OCR 原文 evidence。
- verification_status 初始为 "not_checked"。

OCR 分段文本：
{json.dumps(sections, ensure_ascii=False)}
""".strip()


def build_verification_prompt(original_text: str, field_results: list[dict]) -> str:
    return f"""
你是字段级复核器。逐字段检查 value/evidence/OCR 纠偏是否可靠。
输出 JSON 对象，顶层键为 `verifications`，`verifications` 是数组。每项包含 field_key, verdict, checks, comment。
verdict 只能是 pass、suspicious、fail。
checks 必须包含 evidence_supported、ocr_correction_reasonable、numeric_value_preserved、negation_preserved、section_assignment_reasonable。

原始 OCR 文本：
{original_text}

字段结果：
{json.dumps(field_results, ensure_ascii=False)}
""".strip()
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "新增慢阻肺抽取提示词构建"
```

## Task 8: Field Result Builder

**Files:**
- Create: `app/backend/services/copd_extraction/field_result.py`
- Test: `app/backend/tests/test_copd_field_result.py`

- [ ] **Step 1: Write failing tests**

Create `app/backend/tests/test_copd_field_result.py`:

```python
def test_complete_field_results_fills_not_found_fields():
    from app.backend.services.copd_extraction.field_result import complete_field_results

    results = complete_field_results(
        [{"field_key": "bmi", "original_value": "24.2", "evidence": "BHI:24.2kg/m2"}],
        ["bmi", "crp"],
    )

    by_key = {item["field_key"]: item for item in results}
    assert by_key["bmi"]["extraction_status"] == "extracted"
    assert by_key["crp"]["extraction_status"] == "not_found"
    assert by_key["crp"]["original_value"] == ""
    assert by_key["crp"]["evidence"] is None
    assert by_key["crp"]["ocr_correction"]["applied"] is False


def test_all_empty_detects_full_empty_result():
    from app.backend.services.copd_extraction.field_result import all_fields_empty

    assert all_fields_empty([
        {"field_key": "bmi", "original_value": "", "extraction_status": "not_found"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_result.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement field result builder**

Create `app/backend/services/copd_extraction/field_result.py`:

```python
def _default_result(field_key: str) -> dict:
    return {
        "field_key": field_key,
        "original_value": "",
        "evidence": None,
        "confidence": 0,
        "source_section": None,
        "extraction_status": "not_found",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    }


def _normalize_extracted(item: dict) -> dict:
    result = _default_result(item["field_key"])
    result.update(item)
    if result.get("original_value"):
        result["extraction_status"] = result.get("extraction_status") or "extracted"
    result.setdefault("quality_flags", [])
    result.setdefault("verification_status", "not_checked")
    result.setdefault("ocr_correction", {"applied": False, "raw": "", "normalized": "", "reason": ""})
    return result


def complete_field_results(raw_results: list[dict], field_keys: list[str]) -> list[dict]:
    by_key = {item["field_key"]: _normalize_extracted(item) for item in raw_results if item.get("field_key") in field_keys}
    return [by_key.get(key, _default_result(key)) for key in field_keys]


def all_fields_empty(field_results: list[dict]) -> bool:
    return all(not (item.get("original_value") or "").strip() for item in field_results)
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_result.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/field_result.py app/backend/tests/test_copd_field_result.py
git commit -m "新增慢阻肺全量字段结果构建"
```

## Task 9: LLM Client and Extractor with Fake Client

**Files:**
- Create: `app/backend/services/copd_extraction/llm_client.py`
- Create: `app/backend/services/copd_extraction/extractor.py`
- Test: `app/backend/tests/test_copd_extractor.py`

- [ ] **Step 1: Write failing tests using a fake LLM**

Create `app/backend/tests/test_copd_extractor.py`:

```python
import json


class FakeLlmClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, prompt: str):
        self.calls.append(prompt)
        if "字段级复核器" in prompt:
            return {"verifications": [
                {
                    "field_key": "bmi",
                    "verdict": "pass",
                    "checks": {
                        "evidence_supported": True,
                        "ocr_correction_reasonable": True,
                        "numeric_value_preserved": True,
                        "negation_preserved": True,
                        "section_assignment_reasonable": True,
                    },
                    "comment": "",
                }
            ]}
        return {"fields": [
            {
                "field_key": "bmi",
                "original_value": "24.2kg/m2",
                "evidence": "BHI:24.2kg/m2",
                "confidence": 0.78,
                "source_section": "体格检查",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {
                    "applied": True,
                    "raw": "BHI",
                    "normalized": "BMI",
                    "reason": "位于身高体重之后且单位为 kg/m2",
                },
            }
        ]}


def test_copd_extractor_returns_full_field_results():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    extractor = COPDFieldExtractor(llm_client=FakeLlmClient(), field_keys=["bmi", "crp"])

    results = extractor.extract("体格检查\n身高:175cm体重:74kg。BHI:24.2kg/m2.")

    by_key = {item["field_key"]: item for item in results}
    assert by_key["bmi"]["verification_status"] == "passed"
    assert by_key["bmi"]["ocr_correction"]["applied"] is True
    assert by_key["crp"]["extraction_status"] == "not_found"
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -q
```

Expected: FAIL because extractor does not exist.

- [ ] **Step 3: Implement LLM client interface and extractor**

Create `app/backend/services/copd_extraction/llm_client.py`:

```python
import json


class LlmClient:
    def complete_json(self, prompt: str):
        raise NotImplementedError


def parse_json_response(content: str):
    return json.loads(content)
```

Create `app/backend/services/copd_extraction/extractor.py`:

```python
from .field_result import all_fields_empty, complete_field_results
from .prompts import build_extraction_prompt, build_verification_prompt
from .quality_checks import apply_quality_checks
from .section_splitter import split_sections


class COPDFieldExtractor:
    def __init__(self, llm_client, field_keys: list[str]):
        self._llm_client = llm_client
        self._field_keys = field_keys

    def extract(self, text: str) -> list[dict]:
        sections = split_sections(text)
        extraction_payload = self._llm_client.complete_json(build_extraction_prompt(sections, self._field_keys))
        raw_results = extraction_payload.get("fields") if isinstance(extraction_payload, dict) else None
        if not isinstance(raw_results, list):
            raise ValueError("LLM extraction response must contain fields list")
        results = complete_field_results(raw_results, self._field_keys)
        if all_fields_empty(results):
            return results

        results = apply_quality_checks(results, text)
        verification_payload = self._llm_client.complete_json(build_verification_prompt(text, results))
        verdicts = verification_payload.get("verifications") if isinstance(verification_payload, dict) else None
        if not isinstance(verdicts, list):
            raise ValueError("LLM verification response must contain verifications list")
        return self._merge_verdicts(results, verdicts)

    def _merge_verdicts(self, results: list[dict], verdicts: list[dict]) -> list[dict]:
        verdict_by_key = {item.get("field_key"): item for item in verdicts if isinstance(item, dict)}
        merged = []
        for item in results:
            verdict = verdict_by_key.get(item["field_key"])
            if verdict:
                value = verdict.get("verdict")
                if value == "pass" and not item.get("quality_flags"):
                    item["verification_status"] = "passed"
                elif value == "fail":
                    item["verification_status"] = "failed"
                elif value == "suspicious":
                    item["verification_status"] = "suspicious"
            merged.append(item)
        return merged
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_extractor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/llm_client.py app/backend/services/copd_extraction/extractor.py app/backend/tests/test_copd_extractor.py
git commit -m "新增慢阻肺字段抽取编排"
```

## Task 10: Review Metadata Preservation

**Files:**
- Modify: `app/backend/services/review_service.py`
- Test: `app/backend/tests/test_review_service.py`

- [ ] **Step 1: Write failing review metadata test**

Add to `app/backend/tests/test_review_service.py`:

```python
def test_review_fields_preserve_extraction_metadata(tmp_path):
    from app.backend.services.review_service import ReviewService
    from app.backend.storage.json_store import JsonStore

    class TaskService:
        def get_task(self, task_id):
            return {"task_id": task_id, "status": "review", "schema_version": "1.0.0", "document_type": "copd_admission_record"}

    store = JsonStore(str(tmp_path))
    store.write("results/t1/field_candidates.json", {
        "candidates": [
            {
                "field_key": "bmi",
                "original_value": "24.2kg/m2",
                "evidence": "BHI:24.2kg/m2",
                "confidence": 0.78,
                "source_section": "体格检查",
                "extraction_status": "extracted",
                "verification_status": "suspicious",
                "quality_flags": [{"flag": "value_not_in_evidence", "severity": "warning", "message": "risk"}],
                "ocr_correction": {"applied": True, "raw": "BHI", "normalized": "BMI", "reason": "unit kg/m2"},
            }
        ]
    })
    schema = {"version": "1.0.0", "document_type": "copd_admission_record", "field_groups": [
        {"fields": [{"field_key": "bmi", "label": "BMI"}]}
    ]}
    service = ReviewService(store, TaskService(), schema_provider=lambda: schema)

    review = service.get_or_init("t1")
    field = review["fields"][0]

    assert field["extraction_status"] == "extracted"
    assert field["verification_status"] == "suspicious"
    assert field["quality_flags"][0]["flag"] == "value_not_in_evidence"
    assert field["ocr_correction"]["normalized"] == "BMI"
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py::test_review_fields_preserve_extraction_metadata -q
```

Expected: FAIL because review fields do not preserve metadata.

- [ ] **Step 3: Preserve metadata**

In `ReviewService._build_fields`, add keys to the field dict:

```python
                    "source_section": item.get("source_section"),
                    "extraction_status": item.get("extraction_status", "extracted"),
                    "verification_status": item.get("verification_status", "not_checked"),
                    "quality_flags": item.get("quality_flags", []),
                    "ocr_correction": item.get("ocr_correction"),
```

Add summary counts in `_build_summary`:

```python
            "suspicious_count": sum(1 for f in fields if f.get("verification_status") == "suspicious"),
            "failed_verification_count": sum(1 for f in fields if f.get("verification_status") == "failed"),
            "not_found_count": sum(1 for f in fields if f.get("extraction_status") == "not_found"),
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py::test_review_fields_preserve_extraction_metadata -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/review_service.py app/backend/tests/test_review_service.py
git commit -m "保留慢阻肺字段复核元数据"
```

## Task 11: Orchestrator Full-Empty Failure

**Files:**
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Test: `app/backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing orchestrator helper tests**

Add to `app/backend/tests/test_orchestrator.py`:

```python
def test_orchestrator_detects_all_empty_field_results(tmp_path):
    from app.backend.services.algorithm_ports.orchestrator import _all_field_results_empty

    assert _all_field_results_empty([
        {"field_key": "bmi", "original_value": "", "extraction_status": "not_found"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])
    assert not _all_field_results_empty([
        {"field_key": "bmi", "original_value": "24.2", "extraction_status": "extracted"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py::test_orchestrator_detects_all_empty_field_results -q
```

Expected: FAIL because helper does not exist.

- [ ] **Step 3: Implement helper and use it**

In `app/backend/services/algorithm_ports/orchestrator.py`, add module helper:

```python
def _all_field_results_empty(candidates: list[dict]) -> bool:
    return all(not (item.get("original_value") or "").strip() for item in candidates)
```

Replace the existing `if not candidates:` branch with:

```python
        if not candidates or _all_field_results_empty(candidates):
            return task_service.mark_failed(
                task_id, ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "字段结果为空",
                stage="field_extraction",
                details={"stage": "field_extraction", "reason": "empty_field_results"},
            )
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py::test_orchestrator_detects_all_empty_field_results app/backend/tests/test_task_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/orchestrator.py app/backend/tests/test_orchestrator.py
git commit -m "按全字段空值阻断任务"
```

## Task 12: Backend Wiring With Fake Port First

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/backend/__init__.py`
- Create: `app/backend/services/copd_extraction/port.py`
- Test: `app/backend/tests/test_config.py`
- Test: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write failing config test**

Add to `app/backend/tests/test_config.py`:

```python
def test_load_config_supports_copd_extractor_settings(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  enable_copd_extractor: true
  llm_model_path: ./models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["enable_copd_extractor"] is True
    assert config["llm_model_path"].endswith("qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf")
```

- [ ] **Step 2: Run config RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_supports_copd_extractor_settings -q
```

Expected: FAIL because config loader does not flatten `algorithms`.

- [ ] **Step 3: Implement config support**

In `app/backend/config.py`, add defaults:

```python
    "enable_copd_extractor": False,
    "llm_model_path": "./models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
```

In `_flatten_config`, add:

```python
    algorithms_config = raw.get("algorithms", {})
    if "enable_copd_extractor" in algorithms_config:
        flattened["enable_copd_extractor"] = algorithms_config["enable_copd_extractor"]
    if "llm_model_path" in algorithms_config:
        flattened["llm_model_path"] = algorithms_config["llm_model_path"]
```

In `_normalize_paths`, normalize `llm_model_path` if it is relative:

```python
    model_path = config.get("llm_model_path")
    if model_path and not os.path.isabs(model_path):
        config["llm_model_path"] = os.path.normpath(os.path.join(PROJECT_ROOT, model_path))
```

- [ ] **Step 4: Run config GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_supports_copd_extractor_settings -q
```

Expected: PASS.

- [ ] **Step 5: Write failing wiring test**

Add to `app/backend/tests/test_backend_e2e.py`:

```python
def test_backend_configures_copd_field_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class FakeClient:
        def complete_json(self, prompt):
            return []

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
paths:
  data_dir: ./data
  log_dir: ./logs
  model_dir: ./models
  export_dir: ./exports
  static_dir: ./dist
algorithms:
  enable_copd_extractor: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.backend.services.copd_extraction.port.build_default_copd_field_port",
        lambda config, schema_provider: object(),
    )

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._field_port is not None
```

- [ ] **Step 6: Run wiring RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_backend_configures_copd_field_port -q
```

Expected: FAIL because no field port is wired.

- [ ] **Step 7: Create field port wrapper and builder**

Create `app/backend/services/copd_extraction/port.py`:

```python
from .extractor import COPDFieldExtractor


class COPDFieldPort:
    def __init__(self, extractor):
        self._extractor = extractor

    def extract(self, input: dict) -> list[dict]:
        document_result = input.get("document_result") or {}
        text = document_result.get("merged_text") or ""
        return self._extractor.extract(text)


def _schema_field_keys(schema: dict) -> list[str]:
    return [
        field["field_key"]
        for group in schema.get("field_groups", [])
        for field in group.get("fields", [])
    ]


def build_default_copd_field_port(config: dict, schema_provider):
    from .llm_client import build_llama_cpp_client

    schema = schema_provider()
    llm_client = build_llama_cpp_client(config["llm_model_path"])
    extractor = COPDFieldExtractor(llm_client=llm_client, field_keys=_schema_field_keys(schema))
    return COPDFieldPort(extractor)
```

- [ ] **Step 8: Wire port behind config**

In `app/backend/__init__.py`, before constructing `ProcessingOrchestrator`, add:

```python
    field_port = None
    if config.get("enable_copd_extractor"):
        from .services.copd_extraction.port import build_default_copd_field_port
        field_port = build_default_copd_field_port(config, schema_service.get_current)
```

Pass `field_port=field_port` into `ProcessingOrchestrator`.

- [ ] **Step 9: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_supports_copd_extractor_settings app/backend/tests/test_backend_e2e.py::test_backend_configures_copd_field_port -q
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add app/backend/config.py app/backend/__init__.py app/backend/services/copd_extraction/port.py app/backend/tests/test_config.py app/backend/tests/test_backend_e2e.py
git commit -m "接入慢阻肺字段抽取端口"
```

## Task 13: Real llama.cpp Client

**Files:**
- Modify: `app/backend/services/copd_extraction/llm_client.py`
- Test: `app/backend/tests/test_copd_llm_client.py`

- [ ] **Step 1: Write unit test with fake llama object**

Create `app/backend/tests/test_copd_llm_client.py`:

```python
def test_llama_cpp_client_parses_json_response():
    from app.backend.services.copd_extraction.llm_client import LlamaCppClient

    class FakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens, response_format=None):
            return {"choices": [{"message": {"content": "{\"fields\":[{\"field_key\":\"bmi\"}]}"}}]}

    client = LlamaCppClient(llama=FakeLlama())

    assert client.complete_json("prompt") == {"fields": [{"field_key": "bmi"}]}
```

- [ ] **Step 2: Run RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_llm_client.py -q
```

Expected: FAIL because `LlamaCppClient` does not exist.

- [ ] **Step 3: Implement client**

Add to `llm_client.py`:

```python
class LlamaCppClient(LlmClient):
    def __init__(self, llama):
        self._llama = llama

    def complete_json(self, prompt: str):
        response = self._llama.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        return parse_json_response(content)
```

Add a factory only if `llama_cpp` import is available:

```python
def build_llama_cpp_client(model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1):
    from llama_cpp import Llama

    return LlamaCppClient(Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False))
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_llm_client.py -q
```

Expected: PASS without loading the real model.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/llm_client.py app/backend/tests/test_copd_llm_client.py
git commit -m "新增慢阻肺 llama.cpp 客户端"
```

## Task 14: Frontend Review Risk Display

**Files:**
- Modify: `app/frontend/src/components/review/FieldList.tsx`
- Modify or create test near existing review tests.

- [ ] **Step 1: Write failing frontend test**

Locate existing field list/review tests. Add a fixture field:

```ts
{
  field_key: 'bmi',
  field_name: 'BMI',
  auto_value: '24.2kg/m2',
  final_value: '24.2kg/m2',
  status: 'unreviewed',
  extraction_status: 'extracted',
  verification_status: 'suspicious',
  quality_flags: [{ flag: 'value_not_in_evidence', severity: 'warning', message: '字段值中的数字未能在 evidence 中直接找到' }],
  ocr_correction: { applied: true, raw: 'BHI', normalized: 'BMI', reason: '单位 kg/m2' }
}
```

Assert the UI shows a risk marker and OCR correction reason.

- [ ] **Step 2: Run RED**

Run:

```bash
npm --prefix app/frontend test -- FieldList
```

Expected: FAIL because UI does not display new metadata.

- [ ] **Step 3: Add compact risk display**

In `FieldList.tsx`, render:

```tsx
{field.verification_status === 'suspicious' && <span className="field-risk">需重点核验</span>}
{field.quality_flags?.map((flag) => (
  <small key={flag.flag} className="field-risk-detail">{flag.message}</small>
))}
{field.ocr_correction?.applied && (
  <small className="field-ocr-correction">
    OCR: {field.ocr_correction.raw} -> {field.ocr_correction.normalized}，{field.ocr_correction.reason}
  </small>
)}
```

Use existing CSS naming style in review components.

- [ ] **Step 4: Run GREEN**

Run:

```bash
npm --prefix app/frontend test -- FieldList
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/components/review/FieldList.tsx app/frontend/src/**/*.test.tsx
git commit -m "展示慢阻肺字段核验风险"
```

## Task 15: Documentation Sync

**Files:**
- Modify docs listed in the spec.
- Test: `rg` checks.

- [ ] **Step 1: Update PRD and Backend BDD/TDD docs**

Apply the spec decisions:

- COPD specialty schema is the MVP field source.
- In-repo COPD extraction is allowed.
- Full field results include `extraction_status`, `verification_status`, `quality_flags`, `ocr_correction`.
- Single-field risk goes to review, whole-task failure is reserved for invalid/full-empty/unparseable outputs.

- [ ] **Step 2: Update shared state docs**

In `docs/Shared/state-enums.md`, keep existing manual review statuses, but add field result metadata section:

```markdown
## 字段抽取元数据

`extraction_status`: `extracted`、`not_found`、`uncertain`
`verification_status`: `passed`、`suspicious`、`failed`、`not_checked`
`quality_flags`: 规则化质量核验风险标记列表
`ocr_correction`: OCR 纠偏审计信息

这些不是人工审核状态；人工审核状态仍使用 `unreviewed`、`confirmed`、`modified`。
```

- [ ] **Step 3: Verify docs do not conflict**

Run:

```bash
rg -n "通用病历|不得实现.*规则抽取|空候选|字段候选为空|ready_for_review" docs AGENTS.md CLAUDE.md
```

Expected: no stale statement that contradicts the COPD design.

- [ ] **Step 4: Commit**

```bash
git add docs AGENTS.md CLAUDE.md
git commit -m "同步慢阻肺抽取产品和契约文档"
```

## Task 16: Full Verification

**Files:** no required edits unless failures expose bugs.

- [ ] **Step 1: Run backend focused tests**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_*.py app/backend/tests/test_field_extraction_port.py app/backend/tests/test_review_service.py app/backend/tests/test_orchestrator.py -q
```

Expected: PASS.

- [ ] **Step 2: Run backend suite**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend tests touched by review UI**

```bash
npm --prefix app/frontend test -- --run
```

Expected: PASS.

- [ ] **Step 4: Manual real-model smoke test**

Run a small script or test harness using:

```text
models/llm/qwen2.5-7b-instruct-gguf/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
```

Input: one hand-authored sample from `app/backend/tests/fixtures/copd_ocr_samples.py`.

Expected:

- JSON parses.
- Every schema field appears once.
- At least one field is `extracted` or `uncertain`.
- OCR correction, if present, includes reason.
- Quality flags appear for known risky sample.

- [ ] **Step 5: Final commit if verification fixes were needed**

```bash
git status --short
git add <fixed-files>
git commit -m "修复慢阻肺抽取验证问题"
```

---

## Self-Review

- Spec coverage: plan covers docs boundary, COPD schema, full field result contract, prompt harness, thin rule quality checks, handwritten OCR regression samples, review metadata, backend failure semantics, frontend risk display, and verification.
- Placeholder scan: no TBD/TODO placeholders; config wiring is specified in Task 12 with concrete `algorithms.enable_copd_extractor` and `algorithms.llm_model_path` settings.
- Type consistency: field metadata names are consistent across tasks: `extraction_status`, `verification_status`, `quality_flags`, `ocr_correction`.
