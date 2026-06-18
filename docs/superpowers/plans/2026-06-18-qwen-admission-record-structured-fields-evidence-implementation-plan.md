# Qwen Admission Record Structured Fields Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old small COPD field extraction path with the new admission-record “section -> fixed fields” contract from `data/temp/结构化字段(2).md`, and add lightweight evidence-unit based OCR highlighting without correcting or reordering raw OCR text.

**Architecture:** Keep the existing workstation task/review/export flow and `copd_admission_record` document profile stable for the UI, but switch the active schema to `admission_record_structured_fields.v1`. Backend creates `evidence_units` from raw OCR text, sends numbered units plus the fixed field table to the Qwen prompt, validates the Qwen `fields + evidence_ids` contract, maps it into the existing review candidate layer, and derives doctor-facing attention flags. As each replacement lands, remove the superseded old small-field schema, prompt, section-group extractor, and tests so the codebase does not carry two competing field systems. Frontend consumes schema-ordered sections, complete field results, evidence offsets/text, and doctor-facing attention metadata; it does not infer fields from OCR text.

**Tech Stack:** Python 3 + Flask + pytest + YAML schema config; existing injectable LLM field extraction port; TypeScript + React + Vitest + React Testing Library; no runtime cloud API, CDN, telemetry, model download, or new network dependency.

---

## Spec Review

The spec is broadly self-consistent and should be implemented in its current direction. It explicitly rejects the three main risks: old `copd_admission_record.v1.yaml` small-field semantics, sample-specific OCR/page-order rules, and heavy document-layout work such as bounding boxes, page reordering, title correction, or section-tree reconstruction.

Non-blocking issues to handle in implementation:

- The spec example uses algorithm `document_type: "admission_record"`, while the current app creates tasks with `document_type: "copd_admission_record"`. This plan keeps the public task/profile document type as `copd_admission_record` and makes the active schema version `admission_record_structured_fields.v1`; the Qwen payload `document_type` is validated as informational, not used to route tasks.
- `data/temp/结构化字段(2).md` exists locally but is under `data/`, which is not a durable contract location. This plan creates a committed schema file under `app/config/schemas/` and uses the temp file only as the field-source reference.
- Current code still contains old `original_value/evidence/source_hint/evidence_phrase/ocr_correction` prompt and review metadata. This plan inserts an adapter boundary: Qwen outputs only `status/value/evidence_ids`, while backend derives old review fields, evidence arrays, and doctor-facing attention messages.
- The spec says `not_found` is normal but also says all-empty/all-`not_found` can fail. This plan preserves current task-level failure only when every field is empty/not-found; mixed `found` plus many `not_found` fields enters review normally.
- The qwen runtime package is outside this repository. This plan updates backend prompt/config/adapter contracts and tests, but does not vendor `/mnt/c/Users/97949/Desktop/qwen`, model weights, or real patient samples.

## Implementation Constraints

- Do not modify or delete unrelated dirty worktree changes.
- Do not commit `data/`, `exports/`, `logs/`, model weights, runtime caches, real patient data, local private paths, or secrets.
- Do not add sample-special rules such as replacing `品后诊断` with `最后诊断` or reordering pages because `主诉` appears after a diagnosis block.
- Do not add image bounding boxes, page-layout coordinates, complex section recovery, OCR title correction, OCR text rewriting, or automatic page order repair.
- Keep raw OCR visible exactly as saved by the backend; schema field sections remain ordered by schema.
- Do not leave the legacy `copd_admission_record.v1.yaml` small-field schema or old free-key section-group extraction path active after the fixed-field path is wired. Remove or isolate legacy code in the same task that replaces it, and delete legacy tests that assert old field keys such as `copd_history_years`, `blood_gas_pao2`, `ct_features`, or old prompt keys such as `source_hint` / `evidence_phrase`.

---

## File Structure

| Path | Role | Change |
| --- | --- | --- |
| `app/config/schemas/admission_record_structured_fields.v1.yaml` | New committed schema generated from `data/temp/结构化字段(2).md` and the spec field table | Create |
| `app/config/schemas/copd_admission_record.v1.yaml` | Legacy small-field schema; remove active references in Task 1 and delete in Task 11 | Delete in Task 11 |
| `app/backend/__init__.py` | Load the new active schema and prompt version while preserving `copd_admission_record` profile routing | Modify |
| `app/backend/services/schema_loader.py` | Existing schema loader remains the reference for `field_groups`; no new parser format is introduced | Reference |
| `app/backend/services/algorithm_ports/evidence_units.py` | Build lightweight text evidence units with offsets and optional page numbers | Create |
| `app/backend/services/algorithm_ports/results.py` | Persist `evidence_units` with `document_result.json` and return them on OCR retry | Modify |
| `app/backend/services/algorithm_ports/orchestrator.py` | Generate evidence units after OCR, pass them to field extraction, validate complete results | Modify |
| `app/backend/services/algorithm_ports/field_extraction.py` | Accept evidence arrays, complete fixed-field candidates, and doctor-facing attention metadata | Modify |
| `app/backend/services/copd_extraction/prompts.py` | Replace old free-key prompt builders with the fixed-field admission-record prompt | Modify |
| `app/backend/services/copd_extraction/admission_contract.py` | Validate Qwen raw output and map statuses/evidence to review candidates | Create |
| `app/backend/services/copd_extraction/port.py` | Wire default extractor to the new fixed-field prompt/adapter path and remove legacy section-group entrypoints from active use | Modify |
| `app/backend/services/copd_extraction/extractor.py` | Legacy section-group/field-batch extractor implementation; replace active path with fixed-field adapter and clean remnants in Task 11 | Modify |
| `app/backend/services/copd_extraction/section_splitter.py` | Legacy title-based section splitter that must not drive fixed-field evidence定位 | Delete in Task 11 |
| `app/backend/services/reextraction_service.py` | Reuse saved OCR text and evidence units for OCR-only re-extraction | Modify |
| `app/backend/services/_review_field_factory.py` | Preserve evidence arrays and derive `attention_required` / `attention_message` | Modify |
| `app/backend/services/review_service.py` | Return schema groups, raw OCR pages, evidence arrays, and attention metadata | Modify |
| `app/backend/services/export_service.py` | Export schema-ordered fixed fields and evidence arrays without blocking on `not_found` | Modify |
| `app/backend/config.py` | Add OCR `temperature=0.0` config and validation | Modify |
| `app/backend/services/algorithm_ports/paddleocr_vlm_server.py` | Pass OCR temperature to the local OCR predict call and diagnostics | Modify |
| `app/config/default.yaml` | Add safe OCR temperature default | Modify |
| `app/config/vlm_backend_config.yaml` | Keep 8GB-safe `max_model_len` and test against `30000` regression | Modify only if current value regresses |
| `app/config/algorithm-modules.README.md` | Document fixed-field Qwen contract, safe OCR temperature, max model length, and original-image immutability | Modify |
| `docs/Backend/Backend_TDD/02-algorithm-ports.md` | Document `evidence_units -> evidence_ids -> evidence` backend contract | Modify |
| `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md` | Document fixed fields, not-found normal behavior, and task failure boundaries | Modify |
| `docs/Front/Front_TDD/09-field-evidence.md` | Document evidence offset/text highlighter and yellow attention semantics | Modify |
| `app/frontend/src/api/review.ts` | Type evidence offsets and doctor-facing attention metadata | Modify |
| `app/frontend/src/components/review/ReviewSourcePanel.tsx` | Highlight by offset first, then text fallback, without raw OCR correction | Modify |
| `app/frontend/src/components/review/FieldList.tsx` | Schema sections, single-field section display, `not_found` copy, yellow exclamation | Modify |
| `app/frontend/src/pages/review/ReviewPage.tsx` | Select evidence/page by raw OCR location; keep field order schema-driven | Modify |
| `app/frontend/src/pages/review/demoReviewSample.ts` | Update demo to fixed admission-record schema shape with raw OCR evidence | Modify |

---

### Task 1: Commit the New Fixed Field Schema

**Files:**
- Create: `app/config/schemas/admission_record_structured_fields.v1.yaml`
- Modify: `app/backend/__init__.py`
- Modify: `docs/Backend/Backend_TDD/02-algorithm-ports.md`
- Modify: `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`
- Test: `app/backend/tests/test_schema_loader.py`
- Test: `app/backend/tests/test_schema_api.py`
- Test: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write failing test**

Add tests that require the active schema to come from the new fixed-field table:

- `app/backend/tests/test_schema_loader.py::test_load_admission_record_structured_schema_from_repo`
  - Loads `app/config/schemas/admission_record_structured_fields.v1.yaml`.
  - Expects `version == "admission_record_structured_fields.v1"`.
  - Expects exactly 61 unique field keys.
  - Expects these required keys: `chief_complaint`, `hpi_urine_status`, `pmh_blood_product_history`, `pe_respiration_rate`, `pe_respiratory_exam`, `pe_cardiac_exam`, `aux_blood_gas_ph`, `aux_blood_gas_pco2`, `aux_blood_gas_po2`, `aux_blood_gas_na`, `aux_blood_gas_fio2`, `aux_blood_gas_oxygenation_index`, `diagnosis_preliminary`, `diagnosis_final`.
  - Expects old small-field keys absent: `copd_history_years`, `blood_gas_pao2`, `ct_features`, `positive_signs`.
- `app/backend/tests/test_schema_api.py::test_schema_api_returns_admission_record_structured_fields`
  - Calls the schema API and expects groups in this order: 主诉, 现病史, 既往史, 个人史, 家族史, 体格检查, 辅助检查, 诊断.
- `app/backend/tests/test_backend_e2e.py::test_backend_default_profile_uses_admission_record_structured_schema`
  - Creates the app and expects the default profile schema version to be `admission_record_structured_fields.v1`.
- Replace or remove any old schema-loader assertions that require `copd_history_years`, `blood_gas_pao2`, `ct_features`, or other legacy small-field keys.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py::test_load_admission_record_structured_schema_from_repo app/backend/tests/test_schema_api.py::test_schema_api_returns_admission_record_structured_fields app/backend/tests/test_backend_e2e.py::test_backend_default_profile_uses_admission_record_structured_schema -q
```

Expected: FAIL because the new schema file does not exist and the app still loads the old small COPD schema.

- [ ] **Step 3: Implement minimal code**

Create `app/config/schemas/admission_record_structured_fields.v1.yaml` using the spec field table and labels from `data/temp/结构化字段(2).md`. Use existing schema shape:

- `version: "admission_record_structured_fields.v1"`
- `document_type: copd_admission_record`
- `field_groups` with `group_key/group_label/fields`
- Every field has `field_key`, `label`, and `type: string`

Modify `app/backend/__init__.py` so `SchemaService` loads the new schema file. Keep `DocumentProfile.document_type="copd_admission_record"` and label `入院记录`.

Remove active references to `app/config/schemas/copd_admission_record.v1.yaml` after switching to the new schema file. Do not keep it as a fallback because it can silently reintroduce the old small-field context. The physical deletion is deferred to Task 11 after processing, re-extraction, review, export, and frontend tests are all moved to the new schema.

Update `docs/Backend/Backend_TDD/02-algorithm-ports.md` and `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md` to describe the new fixed-field schema, `found/not_found/uncertain` algorithm statuses, and backend mapping to existing review metadata.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py::test_load_admission_record_structured_schema_from_repo app/backend/tests/test_schema_api.py::test_schema_api_returns_admission_record_structured_fields app/backend/tests/test_backend_e2e.py::test_backend_default_profile_uses_admission_record_structured_schema -q
```

Expected: PASS; schema has 61 fields, old small keys are absent, app default schema version is `admission_record_structured_fields.v1`.

- [ ] **Step 5: Commit**

```bash
git add app/config/schemas/admission_record_structured_fields.v1.yaml app/backend/__init__.py app/backend/tests/test_schema_loader.py app/backend/tests/test_schema_api.py app/backend/tests/test_backend_e2e.py docs/Backend/Backend_TDD/02-algorithm-ports.md docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md
git commit -m "feat: 接入入院记录固定字段 schema"
```

---

### Task 2: Generate and Persist Lightweight Evidence Units

**Files:**
- Create: `app/backend/services/algorithm_ports/evidence_units.py`
- Modify: `app/backend/services/algorithm_ports/results.py`
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Test: `app/backend/tests/test_evidence_units.py`
- Test: `app/backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test**

Add `app/backend/tests/test_evidence_units.py` with tests for:

- `test_build_evidence_units_preserves_raw_ocr_title_typos`
  - Input contains `## 品后诊断`.
  - Expected unit text still contains `品后诊断`; no replacement with `最后诊断`.
- `test_build_evidence_units_keeps_blood_gas_group_together`
  - Input contains `血气：pH 7.40、pCO2 36.00mmHg、pO2 76.00mmHg、Na+ 130.00mmol/L、FIO2 21.00、氧合指数：361`.
  - Expected exactly one unit containing all six blood gas labels.
- `test_build_evidence_units_keeps_diagnosis_items_together`
  - Input diagnosis block contains multiple diagnosis lines.
  - Expected units are diagnosis-line or diagnosis-block level, not comma-level fragments.
- `test_build_evidence_units_offsets_match_merged_text`
  - For every unit, `merged_text[start_offset:end_offset] == unit["text"]`.
- `test_build_evidence_units_uses_saved_page_order`
  - Pages are passed in page number order from backend saved metadata; output offsets follow that order even if content looks naturally out of order.

Add `app/backend/tests/test_orchestrator.py::test_orchestrator_passes_evidence_units_to_field_port_and_persists_them`:

- Fake doc port returns pages and merged text.
- Capturing field port asserts `input["evidence_units"]` is a non-empty list.
- Store `results/task_001/document_result.json` contains `evidence_units`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evidence_units.py app/backend/tests/test_orchestrator.py::test_orchestrator_passes_evidence_units_to_field_port_and_persists_them -q
```

Expected: FAIL because `evidence_units.py` does not exist and orchestrator does not pass or persist evidence units.

- [ ] **Step 3: Implement minimal code**

Create `build_evidence_units(document_result: dict) -> list[dict]` in `app/backend/services/algorithm_ports/evidence_units.py`:

- Combine page text in backend page order using the same separator as `merged_text`.
- Produce IDs `u001`, `u002`, ...
- Store `text`, `start_offset`, `end_offset`, optional `page_no`, optional `section_key`.
- Split primarily by newline, Chinese period, semicolon, and controlled long comma fallback.
- Keep vital-sign rows as one unit.
- Keep blood-gas groups as one unit.
- Keep diagnosis lines or diagnosis block units coarse enough to avoid diagnosis/value错位.
- Never correct OCR text and never infer page order.

Modify `AlgorithmResultStore.write_document_result()` and `read_success_document_result()` to include `evidence_units`.

Modify `ProcessingOrchestrator.run()` to call `build_evidence_units(doc_result)` after successful OCR, persist units, and pass `evidence_units` into `field_input`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_evidence_units.py app/backend/tests/test_orchestrator.py::test_orchestrator_passes_evidence_units_to_field_port_and_persists_them -q
```

Expected: PASS; units are persisted and passed to field extraction without OCR correction.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/evidence_units.py app/backend/services/algorithm_ports/results.py app/backend/services/algorithm_ports/orchestrator.py app/backend/tests/test_evidence_units.py app/backend/tests/test_orchestrator.py
git commit -m "feat: 生成并传递 OCR evidence units"
```

---

### Task 3: Add the Fixed-Field Qwen Prompt Contract

**Files:**
- Modify: `app/backend/services/copd_extraction/prompts.py`
- Test: `app/backend/tests/test_copd_prompts.py`

- [ ] **Step 1: Write failing test**

Add prompt tests:

- `test_admission_prompt_requires_fixed_schema_fields_and_not_free_keys`
  - Builds prompt from the new schema and two evidence units.
  - Expects all schema field keys to appear in a fixed table section.
  - Expects text requiring every field exactly once.
  - Expects prompt to forbid schema外字段 and自由生成二级 key.
  - Expects prompt to include `evidence_ids` as a list.
  - Expects prompt to exclude old output keys `source_hint`, `evidence_phrase`, `ocr_correction`, `quality_flags`.
- `test_admission_prompt_requires_not_found_for_missing_fields`
  - Expects explicit `status="not_found"`, `value=""`, `evidence_ids=[]`.
- `test_admission_prompt_forbids_subjective_diagnosis`
  - Expects wording that `diagnosis_preliminary` and `diagnosis_final` can only extract diagnosis text from OCR evidence and must not infer, rewrite, or add diagnosis.
- `test_admission_prompt_allows_shared_evidence_ids`
  - Expects prompt to say multiple fields may share one evidence unit, especially blood gas fields.
- `test_admission_prompt_does_not_instruct_title_correction_or_page_reorder`
  - Expects prompt to preserve raw OCR evidence units and not correct titles such as `品后诊断` or reorder pages.
- Rewrite old prompt tests that assert `source_hint`, `evidence_phrase`, old COPD field keys, or "找不到的字段可以省略" so they instead assert the fixed-field `evidence_ids` contract.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -k "admission_prompt" -q
```

Expected: FAIL because no fixed-field admission prompt builder exists and current prompts still use old evidence/source metadata.

- [ ] **Step 3: Implement minimal code**

Add:

- Constant `ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION = "admission_record_structured_fields_prompt.v1"`.
- Function `build_admission_structured_fields_prompt(schema: dict, evidence_units: list[dict], document_text: str = "") -> str`.

The prompt must require this JSON shape:

```json
{
  "schema_version": "admission_record_structured_fields.v1",
  "document_type": "admission_record",
  "fields": [
    {
      "section_key": "chief_complaint",
      "section_label": "主诉",
      "field_key": "chief_complaint",
      "field_label": "主诉",
      "status": "found",
      "value": "反复咳嗽、咳痰15年",
      "evidence_ids": ["u001"]
    }
  ]
}
```

The prompt must instruct Qwen:

- Output one item per schema field.
- Use only schema field keys.
- Use `found`, `not_found`, or `uncertain`.
- Select evidence IDs only from the numbered `evidence_units`.
- Do not generate evidence text.
- Do not infer diagnosis or medical advice.
- Do not correct OCR text or reorder pages.
- Use shared evidence IDs when one evidence unit supports multiple fields.

Remove or quarantine old prompt builders that still encourage free secondary keys, section-title source hints, `evidence_phrase`, or omitted not-found fields once Task 5 switches callers to the new builder. Do not keep them exported from `prompts.py` for the active extraction path.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_prompts.py -k "admission_prompt" -q
```

Expected: PASS; prompt uses fixed schema table and `evidence_ids`, not old free evidence metadata.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/prompts.py app/backend/tests/test_copd_prompts.py
git commit -m "feat: 新增固定字段 Qwen prompt 契约"
```

---

### Task 4: Validate Qwen Output and Refill Evidence

**Files:**
- Create: `app/backend/services/copd_extraction/admission_contract.py`
- Modify: `app/backend/services/algorithm_ports/field_extraction.py`
- Test: `app/backend/tests/test_admission_contract.py`
- Test: `app/backend/tests/test_field_extraction_port.py`

- [ ] **Step 1: Write failing test**

Add `app/backend/tests/test_admission_contract.py` with tests:

- `test_validate_qwen_payload_requires_all_schema_fields`
  - Missing one field raises `AppError` with `ALGORITHM_CONTRACT_INVALID`.
- `test_validate_qwen_payload_rejects_schema_outside_field`
  - Unknown `field_key` raises contract invalid.
- `test_validate_qwen_payload_rejects_duplicate_field`
  - Duplicate `field_key` raises contract invalid.
- `test_validate_qwen_payload_accepts_not_found_without_attention`
  - A `not_found` field maps to `extraction_status="not_found"`, `original_value=""`, `evidence=[]`, `attention_required=False`.
- `test_validate_qwen_payload_maps_found_with_evidence_array`
  - `status="found"` and valid `evidence_ids=["u001"]` maps to `extraction_status="extracted"`, `original_value=value`, and `evidence` as an array containing id/text/start/end/page.
- `test_found_missing_evidence_becomes_attention_not_task_contract_failure`
  - `found` with empty `evidence_ids` maps to `verification_status="suspicious"`, `attention_required=True`, `attention_message="缺少来源证据，请核对原文"`.
- `test_unknown_evidence_id_becomes_attention_not_fake_highlight`
  - Unknown evidence ID maps to `attention_required=True`, `attention_message="来源片段未在 OCR 文本中定位，请核对"`, and no fabricated evidence.
- `test_diagnosis_output_is_not_rewritten_by_adapter`
  - Adapter preserves raw diagnosis value from Qwen output and does not normalize or add diagnosis text.

Update `app/backend/tests/test_field_extraction_port.py`:

- Add `test_validate_field_candidates_accepts_evidence_array_with_offsets`.
- Add `test_validate_field_candidates_accepts_attention_metadata`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_admission_contract.py app/backend/tests/test_field_extraction_port.py::test_validate_field_candidates_accepts_evidence_array_with_offsets app/backend/tests/test_field_extraction_port.py::test_validate_field_candidates_accepts_attention_metadata -q
```

Expected: FAIL because `admission_contract.py` does not exist and `validate_field_candidates` rejects evidence arrays or lacks attention metadata validation.

- [ ] **Step 3: Implement minimal code**

Create `app/backend/services/copd_extraction/admission_contract.py`:

- `validate_qwen_payload(payload: dict, schema: dict) -> list[dict]`
- `map_qwen_fields_to_review_candidates(payload: dict, schema: dict, evidence_units: list[dict]) -> list[dict]`

Mapping rules:

- `found -> extraction_status="extracted"`.
- `not_found -> extraction_status="not_found"`.
- `uncertain -> extraction_status="uncertain"`.
- `value -> original_value`.
- Valid `evidence_ids -> evidence` array with original unit text and offsets.
- Unknown or missing evidence for `found` does not fabricate highlight; it sets `verification_status="suspicious"` and doctor-facing `attention_required=True`.
- `not_found` sets `attention_required=False`.
- Internal flag names may remain in stored `quality_flags` for audit, but doctor-facing `attention_message` must be plain Chinese.

Modify `validate_field_candidates()` so `evidence` accepts `None`, string, or list of dicts with `id`, `text`, `start_offset`, `end_offset`, and optional `page_no`. Validate `attention_required` as optional boolean and `attention_message` as optional string.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_admission_contract.py app/backend/tests/test_field_extraction_port.py::test_validate_field_candidates_accepts_evidence_array_with_offsets app/backend/tests/test_field_extraction_port.py::test_validate_field_candidates_accepts_attention_metadata -q
```

Expected: PASS; Qwen output is strictly fixed-field, evidence is refilled from backend units, and field-level attention does not fail the task.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/admission_contract.py app/backend/services/algorithm_ports/field_extraction.py app/backend/tests/test_admission_contract.py app/backend/tests/test_field_extraction_port.py
git commit -m "feat: 校验并回填 Qwen 字段证据"
```

---

### Task 5: Wire the New Qwen Field Port into Processing and Re-extraction

**Files:**
- Modify: `app/backend/services/copd_extraction/port.py`
- Modify: `app/backend/services/copd_extraction/extractor.py`
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Modify: `app/backend/services/reextraction_service.py`
- Modify: `app/backend/services/algorithm_ports/results.py`
- Test: `app/backend/tests/test_copd_field_port.py`
- Test: `app/backend/tests/test_orchestrator.py`
- Test: `app/backend/tests/test_reextraction_service.py`

- [ ] **Step 1: Write failing test**

Add tests:

- `app/backend/tests/test_copd_field_port.py::test_qwen_admission_port_sends_schema_and_evidence_units`
  - Fake LLM client captures the prompt.
  - Port input includes schema and evidence units.
  - Port returns 61 schema fields mapped through `admission_contract`.
- `app/backend/tests/test_orchestrator.py::test_orchestrator_allows_many_not_found_fields_when_one_field_found`
  - Field port returns full schema with one `found` and 60 `not_found`.
  - Expected task enters `review`.
- `app/backend/tests/test_orchestrator.py::test_orchestrator_rejects_all_not_found_field_results`
  - Field port returns full schema but every field is `not_found`.
  - Expected task enters `failed` with `ALGORITHM_CONTRACT_INVALID`.
- `app/backend/tests/test_reextraction_service.py::test_reextract_passes_saved_evidence_units_to_field_port`
  - Saved successful `document_result.json` includes `evidence_units`.
  - Re-extraction field port receives those units.
- `app/backend/tests/test_reextraction_service.py::test_reextract_generates_evidence_units_when_legacy_document_result_lacks_them`
  - Saved OCR text has no units.
  - Re-extraction builds units from raw OCR and passes them to field port.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_port.py::test_qwen_admission_port_sends_schema_and_evidence_units app/backend/tests/test_orchestrator.py::test_orchestrator_allows_many_not_found_fields_when_one_field_found app/backend/tests/test_orchestrator.py::test_orchestrator_rejects_all_not_found_field_results app/backend/tests/test_reextraction_service.py::test_reextract_passes_saved_evidence_units_to_field_port app/backend/tests/test_reextraction_service.py::test_reextract_generates_evidence_units_when_legacy_document_result_lacks_them -q
```

Expected: FAIL because the port still uses old section-group extraction and re-extraction does not pass evidence units.

- [ ] **Step 3: Implement minimal code**

Modify the default field port path:

- Build the new fixed-field prompt with schema and evidence units.
- Call the injectable LLM JSON client.
- Validate and map Qwen output through `admission_contract`.
- Keep the legacy class names only where needed for compatibility, but do not let the default admission-record path use free secondary keys.

Modify orchestrator/re-extraction:

- Pass `evidence_units` into field extraction during initial processing and OCR-only re-extraction.
- Treat all-empty/all-not-found candidates as task-level failure.
- Treat single-field suspicious evidence as review-level attention.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_field_port.py::test_qwen_admission_port_sends_schema_and_evidence_units app/backend/tests/test_orchestrator.py::test_orchestrator_allows_many_not_found_fields_when_one_field_found app/backend/tests/test_orchestrator.py::test_orchestrator_rejects_all_not_found_field_results app/backend/tests/test_reextraction_service.py::test_reextract_passes_saved_evidence_units_to_field_port app/backend/tests/test_reextraction_service.py::test_reextract_generates_evidence_units_when_legacy_document_result_lacks_them -q
```

Expected: PASS; processing and re-extraction use the new evidence-unit Qwen contract.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/port.py app/backend/services/copd_extraction/extractor.py app/backend/services/algorithm_ports/orchestrator.py app/backend/services/reextraction_service.py app/backend/services/algorithm_ports/results.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_orchestrator.py app/backend/tests/test_reextraction_service.py
git commit -m "feat: 处理流程接入固定字段 Qwen 抽取"
```

---

### Task 6: Return Review Fields with Evidence Arrays and Doctor-Facing Attention

**Files:**
- Modify: `app/backend/services/_review_field_factory.py`
- Modify: `app/backend/services/review_service.py`
- Modify: `app/backend/services/export_service.py`
- Test: `app/backend/tests/test_review_service.py`
- Test: `app/backend/tests/test_review_routes.py`
- Test: `app/backend/tests/test_export_service.py`

- [ ] **Step 1: Write failing test**

Add tests:

- `app/backend/tests/test_review_service.py::test_review_field_preserves_evidence_array_and_attention_message`
  - Candidate has `evidence=[{"id":"u001","text":"主诉：咳嗽","start_offset":0,"end_offset":5,"page_no":1}]`, `attention_required=True`, and doctor-facing `attention_message`.
  - Review field preserves the evidence array and attention fields.
- `app/backend/tests/test_review_service.py::test_not_found_review_field_is_not_attention`
  - Candidate status is `not_found`.
  - Review field has `attention_required=False`, empty final value, and `extraction_status="not_found"`.
- `app/backend/tests/test_review_routes.py::test_review_route_returns_schema_ordered_admission_fields`
  - Route response includes `field_groups` and 61 fields ordered by schema.
- `app/backend/tests/test_review_routes.py::test_review_route_does_not_expose_internal_attention_flag_names_as_messages`
  - Response visible attention messages do not contain `source_section_not_found`, `evidence_missing_fallback`, or `source_hint=`.
- `app/backend/tests/test_export_service.py::test_export_keeps_admission_schema_order_and_evidence_array`
  - Export model follows schema order and keeps evidence arrays; `not_found` fields do not block export when final value is empty.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py::test_review_field_preserves_evidence_array_and_attention_message app/backend/tests/test_review_service.py::test_not_found_review_field_is_not_attention app/backend/tests/test_review_routes.py::test_review_route_returns_schema_ordered_admission_fields app/backend/tests/test_review_routes.py::test_review_route_does_not_expose_internal_attention_flag_names_as_messages app/backend/tests/test_export_service.py::test_export_keeps_admission_schema_order_and_evidence_array -q
```

Expected: FAIL because review/export currently expect string evidence and infer risk from old metadata.

- [ ] **Step 3: Implement minimal code**

Modify review field construction:

- Copy `evidence` arrays without flattening.
- Add `attention_required` and `attention_message` to review fields.
- Default `not_found` fields to `attention_required=False`.
- Preserve internal `quality_flags` for audit, but do not derive frontend-visible messages from internal flag names.
- Keep `auto_value/final_value` empty for not-found fields.

Modify export schema view so evidence arrays survive JSON and Excel export model building. Do not make empty `not_found` fields blocking.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py::test_review_field_preserves_evidence_array_and_attention_message app/backend/tests/test_review_service.py::test_not_found_review_field_is_not_attention app/backend/tests/test_review_routes.py::test_review_route_returns_schema_ordered_admission_fields app/backend/tests/test_review_routes.py::test_review_route_does_not_expose_internal_attention_flag_names_as_messages app/backend/tests/test_export_service.py::test_export_keeps_admission_schema_order_and_evidence_array -q
```

Expected: PASS; review API is schema ordered, evidence arrays are preserved, and yellow-attention metadata is doctor-facing.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/_review_field_factory.py app/backend/services/review_service.py app/backend/services/export_service.py app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py app/backend/tests/test_export_service.py
git commit -m "feat: 审核结果返回证据数组和核验提示"
```

---

### Task 7: Highlight OCR Evidence by Offset, Then Text Fallback

**Files:**
- Modify: `app/frontend/src/api/review.ts`
- Modify: `app/frontend/src/components/review/ReviewSourcePanel.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `docs/Front/Front_TDD/09-field-evidence.md`
- Test: `app/frontend/src/api/shared-contracts.test.ts`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write failing test**

Add frontend tests:

- `app/frontend/src/api/shared-contracts.test.ts::normalizes_review_evidence_offsets_and_attention_metadata`
  - Mock review response with evidence array including `id`, `text`, `start_offset`, `end_offset`, `page_no`.
  - Expects normalized field preserves offsets and `attention_required`.
- `app/frontend/src/pages/review/ReviewPage.test.tsx::highlights_evidence_by_offset_without_correcting_raw_ocr`
  - OCR text contains `## 品后诊断`.
  - Evidence offset points to that raw text.
  - Expected `<mark>` contains `品后诊断`, not `最后诊断`.
- `app/frontend/src/pages/review/ReviewPage.test.tsx::falls_back_to_evidence_text_when_offset_is_missing`
  - Evidence has text but no offsets.
  - Expected existing text highlighter works.
- `app/frontend/src/pages/review/ReviewPage.test.tsx::shows_unlocated_message_without_fabricating_highlight`
  - Evidence ID is present but no valid evidence text/offset.
  - Expected message `来源片段未在 OCR 文本中定位，请核对`; no `<mark>`.
- `app/frontend/src/pages/review/ReviewPage.test.tsx::uses_saved_page_order_for_ocr_panel`
  - Pages are in saved order while content looks out of natural order.
  - Expected OCR panel displays saved order; selected evidence jumps to actual raw position.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/api/shared-contracts.test.ts app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: FAIL because frontend types and source panel do not support evidence offsets.

- [ ] **Step 3: Implement minimal code**

Modify `ReviewEvidence`:

- Add `id?: string`, `start_offset?: number`, `end_offset?: number`.
- Keep optional `text`, `page_no`, `page_id`.
- Do not add bounding box usage.

Modify source selection/highlighting:

- Prefer `start_offset/end_offset` when valid for the current raw OCR text.
- Fall back to evidence `text`.
- If both fail, show `来源片段未在 OCR 文本中定位，请核对`.
- Keep long-evidence guard; do not highlight over 100 characters.
- Keep `stripOcrMarkup` only for markup cleanup; do not use it to correct medical text or titles.

Update `docs/Front/Front_TDD/09-field-evidence.md` with FE cases for offset-first highlighter, raw OCR preservation, and no fabricated highlight.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/api/shared-contracts.test.ts app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: PASS; OCR evidence highlights raw OCR by offset/text and does not correct OCR content.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/api/review.ts app/frontend/src/components/review/ReviewSourcePanel.tsx app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/api/shared-contracts.test.ts app/frontend/src/pages/review/ReviewPage.test.tsx docs/Front/Front_TDD/09-field-evidence.md
git commit -m "feat: 前端按证据 offset 高亮 OCR 原文"
```

---

### Task 8: Render Fixed Sections, Not-Found Copy, and Yellow Attention

**Files:**
- Modify: `app/frontend/src/components/review/FieldList.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/demoReviewSample.ts`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/components/review/FieldList.test.tsx`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write failing test**

Add component/page tests:

- `app/frontend/src/components/review/FieldList.test.tsx::renders_single_field_section_without_duplicate_label`
  - Group `主诉` with field `主诉`.
  - Expected section title visible, field label not duplicated beside textarea.
- `app/frontend/src/components/review/FieldList.test.tsx::renders_not_found_as_unmentioned_without_yellow_flag`
  - Field has `extraction_status="not_found"`, empty value, `attention_required=false`.
  - Expected visible copy `未提及`; no yellow exclamation.
- `app/frontend/src/components/review/FieldList.test.tsx::renders_attention_as_yellow_exclamation_only`
  - Field has `attention_required=true`, `attention_message="结果不确定，请核对原文"`.
  - Expected `aria-label="重点核验：结果不确定，请核对原文"` and visible `!`.
- `app/frontend/src/components/review/FieldList.test.tsx::does_not_render_internal_quality_flag_names`
  - Field quality flags contain internal names.
  - Expected UI does not contain `source_section_not_found`, `evidence_missing_fallback`, or `source_hint=`.
- `app/frontend/src/pages/review/ReviewPage.test.tsx::renders_schema_order_even_when_ocr_page_order_is_odd`
  - OCR text begins with diagnosis, then chief complaint.
  - Field section order remains schema order: 主诉 before 现病史 before 诊断.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/components/review/FieldList.test.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: FAIL because current field risk logic derives from internal flags and empty fields render as empty controls without not-found copy.

- [ ] **Step 3: Implement minimal code**

Modify `FieldList`:

- Use `field.attention_required` and `field.attention_message` for yellow exclamation.
- Do not infer yellow attention from `not_found`.
- Display empty not-found fields as `未提及` or `未找到相关记录`; choose `未提及` consistently for field cards.
- In single-field sections where group label equals field label, hide the repeated field label while preserving accessible textarea labels.
- Keep schema group order from `fieldGroups`.
- Do not parse OCR text or infer missing fields.

Update CSS only for the yellow exclamation and not-found visual state. Do not add new decorative cards or nested cards.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix app/frontend run test -- --run app/frontend/src/components/review/FieldList.test.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: PASS; field cards use doctor-facing attention metadata and not-found fields are quiet.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/components/review/FieldList.tsx app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/demoReviewSample.ts app/frontend/src/pages/review/review.css app/frontend/src/components/review/FieldList.test.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "feat: 前端展示固定字段与重点核验提示"
```

---

### Task 9: Add Qwen/OCR Configuration Safeguards

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/backend/services/algorithm_ports/paddleocr_vlm_server.py`
- Modify: `app/config/default.yaml`
- Modify: `app/config/algorithm-modules.README.md`
- Test: `app/backend/tests/test_config.py`
- Test: `app/backend/tests/test_paddleocr_vlm_server_port.py`
- Test: `app/backend/tests/test_image_processing_port.py`

- [ ] **Step 1: Write failing test**

Add tests:

- `app/backend/tests/test_config.py::test_local_ocr_temperature_defaults_to_zero`
  - `load_config()` returns `local_ocr_temperature == 0.0`.
- `app/backend/tests/test_config.py::test_local_ocr_temperature_must_be_number_between_zero_and_two`
  - Invalid string and negative values raise `ValueError`.
- `app/backend/tests/test_config.py::test_vlm_backend_config_does_not_default_to_30000_context`
  - Reads `app/config/vlm_backend_config.yaml`.
  - Expects `max_model_len <= 8192` and `max_model_len != 30000`.
- `app/backend/tests/test_paddleocr_vlm_server_port.py::test_vlm_server_port_passes_temperature_zero`
  - Fake pipeline captures `temperature=0.0`.
- `app/backend/tests/test_image_processing_port.py::test_original_image_passthrough_does_not_move_or_copy_workstation_original`
  - `OriginalImagePassthroughPort.process()` returns the exact original path and leaves the source file present.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_local_ocr_temperature_defaults_to_zero app/backend/tests/test_config.py::test_local_ocr_temperature_must_be_number_between_zero_and_two app/backend/tests/test_config.py::test_vlm_backend_config_does_not_default_to_30000_context app/backend/tests/test_paddleocr_vlm_server_port.py::test_vlm_server_port_passes_temperature_zero app/backend/tests/test_image_processing_port.py::test_original_image_passthrough_does_not_move_or_copy_workstation_original -q
```

Expected: FAIL because `local_ocr_temperature` is not configured or passed to OCR predict.

- [ ] **Step 3: Implement minimal code**

Modify config:

- Add `local_ocr_temperature: 0.0` default.
- Flatten `algorithms.local_ocr_temperature`.
- Validate numeric range `0 <= local_ocr_temperature <= 2`.
- Pass config into `PaddleOCRVLMServerDocumentPort`.

Modify OCR port:

- Constructor accepts `temperature: float = 0.0`.
- `_predict_page()` passes `temperature` to `pipeline.predict`.
- Diagnostic `ocr_vlm_started` event includes `temperature`.

Update `app/config/default.yaml` and `app/config/algorithm-modules.README.md` with:

- OCR temperature default `0.0`.
- 8GB-safe max model length must not default to `30000`.
- Batch processing must not move workstation original images; use original paths or copy into separate working directories when an external batch package requires its own workspace.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_local_ocr_temperature_defaults_to_zero app/backend/tests/test_config.py::test_local_ocr_temperature_must_be_number_between_zero_and_two app/backend/tests/test_config.py::test_vlm_backend_config_does_not_default_to_30000_context app/backend/tests/test_paddleocr_vlm_server_port.py::test_vlm_server_port_passes_temperature_zero app/backend/tests/test_image_processing_port.py::test_original_image_passthrough_does_not_move_or_copy_workstation_original -q
```

Expected: PASS; config prevents OCR randomness, 30000-token default regression, and original image movement.

- [ ] **Step 5: Commit**

```bash
git add app/backend/config.py app/backend/services/algorithm_ports/paddleocr_vlm_server.py app/config/default.yaml app/config/algorithm-modules.README.md app/backend/tests/test_config.py app/backend/tests/test_paddleocr_vlm_server_port.py app/backend/tests/test_image_processing_port.py
git commit -m "chore: 固化 Qwen OCR 安全配置"
```

---

### Task 10: Add End-to-End Admission Record Regression

**Files:**
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Test: `app/backend/tests/test_backend_e2e.py`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write failing test**

Add backend E2E test `test_admission_record_raw_ocr_typo_and_page_order_still_reviewable`:

- Simulated OCR pages are saved in system order:
  - Page 1 text begins with `## 品后诊断` and contains final diagnosis text.
  - Page 2 text contains `主诉：反复咳嗽、咳痰20年...`.
- Fake Qwen field port returns full 61-field payload:
  - `chief_complaint` found with evidence ID from page 2.
  - `diagnosis_final` found with evidence ID from page 1.
  - Blood gas six fields share the same evidence ID.
  - Most past-history fields are `not_found`.
- Expected task enters `review`.
- Expected review route:
  - `ocr_text` still contains `品后诊断`.
  - `field_groups` are schema ordered.
  - `diagnosis_final` value is exactly the source diagnosis string from OCR payload.
  - `pmh_nephritis` is `not_found` and `attention_required=False`.
  - Blood gas six fields share the same evidence unit ID.

Add frontend test `renders_raw_ocr_and_schema_fields_for_typo_title_and_odd_page_order`:

- Mock review API with the backend E2E shape.
- Expected OCR panel displays `品后诊断`.
- Expected field panel shows `主诉` section before `诊断`.
- Clicking `诊断 -> 最终诊断` highlights the raw OCR evidence on page 1.
- No UI text shows internal flags.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_admission_record_raw_ocr_typo_and_page_order_still_reviewable -q
npm --prefix app/frontend run test -- --run app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: FAIL until Tasks 1-9 are implemented.

- [ ] **Step 3: Implement minimal code**

Finish any missing integration discovered by the E2E tests:

- Ensure `document_result.json` stores raw OCR and evidence units.
- Ensure field candidates write full schema coverage.
- Ensure review route enriches raw OCR and schema groups.
- Ensure frontend highlighter uses actual raw OCR location.
- Do not add sample-special correction for `品后诊断`.
- Do not reorder pages based on content.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_admission_record_raw_ocr_typo_and_page_order_still_reviewable -q
npm --prefix app/frontend run test -- --run app/frontend/src/pages/review/ReviewPage.test.tsx
```

Expected: PASS; raw OCR typo/page-order case is reviewable through the fixed field schema and evidence offset highlighter.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_backend_e2e.py app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "test: 覆盖入院记录字段与 OCR 证据端到端"
```

---

### Task 11: Remove Legacy Small-Field Extraction Context

**Files:**
- Delete: `app/config/schemas/copd_admission_record.v1.yaml`
- Modify: `app/backend/services/copd_extraction/prompts.py`
- Modify: `app/backend/services/copd_extraction/port.py`
- Modify: `app/backend/services/copd_extraction/extractor.py`
- Delete: `app/backend/services/copd_extraction/section_splitter.py`
- Modify: `app/backend/tests/test_copd_prompts.py`
- Modify: `app/backend/tests/test_copd_extractor.py`
- Modify: `app/backend/tests/test_copd_section_splitter.py`
- Modify: `app/backend/tests/test_copd_samples.py`
- Test: `app/backend/tests/test_legacy_cleanup.py`

- [ ] **Step 1: Write failing test**

Create `app/backend/tests/test_legacy_cleanup.py`:

- `test_legacy_small_field_schema_file_removed`
  - Asserts `app/config/schemas/copd_admission_record.v1.yaml` does not exist.
- `test_active_code_no_longer_mentions_old_small_field_keys`
  - Scans `app/backend/services/copd_extraction`, `app/backend/services/algorithm_ports`, `app/backend/__init__.py`, and `app/config`.
  - Excludes `app/backend/tests/test_legacy_cleanup.py`.
  - Fails if it finds old small-field keys: `copd_history_years`, `blood_gas_pao2`, `blood_gas_paco2`, `ct_features`, `positive_signs`, `maintenance_therapy`, `dyspnea_grade_mMRC`.
- `test_active_prompt_module_no_longer_exports_legacy_free_key_builders`
  - Imports `app.backend.services.copd_extraction.prompts`.
  - Expects no exported `build_extraction_prompt`, `build_section_group_extraction_prompt`, or `build_source_hint_regeneration_prompt`.
  - Expects `build_admission_structured_fields_prompt` exists.
- `test_active_extraction_port_does_not_reference_section_group_strategy`
  - Reads `app/backend/services/copd_extraction/port.py` and `app/backend/services/copd_extraction/extractor.py`.
  - Fails if active code contains `STRATEGY_SECTION_GROUPS`, `SECTION_GROUPS`, `source_hint`, or `evidence_phrase`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_legacy_cleanup.py -q
```

Expected: FAIL because old schema, old prompt exports, and old section-group references still exist before cleanup.

- [ ] **Step 3: Implement minimal code**

Clean up the old path after Tasks 1-10 pass:

- Delete `app/config/schemas/copd_admission_record.v1.yaml`.
- Remove old prompt builders that output or discuss `source_hint`, `evidence_phrase`, omitted fields, old COPD keys, or free secondary keys.
- Remove legacy field-batch and section-group strategy constants from active extraction code.
- Delete `app/backend/services/copd_extraction/section_splitter.py`; the fixed-field extraction path must use schema order plus evidence units, not title-based section recovery.
- Rewrite or delete old tests that assert old small-field behavior. Keep tests only if they now verify the fixed schema, fixed prompt, evidence IDs, or no-regression cleanup behavior.
- Run `rg -n "copd_history_years|blood_gas_pao2|blood_gas_paco2|ct_features|positive_signs|maintenance_therapy|dyspnea_grade_mMRC|source_hint|evidence_phrase|STRATEGY_SECTION_GROUPS|SECTION_GROUPS" app/backend/services/copd_extraction app/backend/services/algorithm_ports app/backend/__init__.py app/config` and remove active extraction/config matches unless a match is in `test_legacy_cleanup.py` itself.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_legacy_cleanup.py app/backend/tests/test_schema_loader.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_orchestrator.py app/backend/tests/test_reextraction_service.py app/backend/tests/test_backend_e2e.py -q
```

Expected: PASS; active backend/config code no longer exposes old small-field schema, old prompt output keys, or old section-group extraction strategy, and the fixed-field admission-record path still passes.

- [ ] **Step 5: Commit**

```bash
git add app/config/schemas/copd_admission_record.v1.yaml app/backend/services/copd_extraction/prompts.py app/backend/services/copd_extraction/port.py app/backend/services/copd_extraction/extractor.py app/backend/services/copd_extraction/section_splitter.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_extractor.py app/backend/tests/test_copd_section_splitter.py app/backend/tests/test_copd_samples.py app/backend/tests/test_legacy_cleanup.py
git commit -m "refactor: 清理旧版慢阻肺小字段抽取路径"
```

---

## Final Verification

After all tasks pass individually, run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_schema_loader.py app/backend/tests/test_schema_api.py app/backend/tests/test_evidence_units.py app/backend/tests/test_admission_contract.py app/backend/tests/test_copd_prompts.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_field_extraction_port.py app/backend/tests/test_orchestrator.py app/backend/tests/test_reextraction_service.py app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py app/backend/tests/test_export_service.py app/backend/tests/test_config.py app/backend/tests/test_paddleocr_vlm_server_port.py app/backend/tests/test_image_processing_port.py app/backend/tests/test_backend_e2e.py app/backend/tests/test_legacy_cleanup.py -q
npm --prefix app/frontend run test -- --run app/frontend/src/api/shared-contracts.test.ts app/frontend/src/components/review/FieldList.test.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
npm --prefix app/frontend run typecheck
```

Expected:

- Backend focused suite passes.
- Frontend focused Vitest suite passes.
- TypeScript typecheck passes.
- No command downloads models, touches real patient data, or requires network access.

Run before the final report:

```bash
git diff --check -- app/config/schemas/admission_record_structured_fields.v1.yaml app/config/schemas/copd_admission_record.v1.yaml app/backend app/frontend docs/Backend/Backend_TDD/02-algorithm-ports.md docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md docs/Front/Front_TDD/09-field-evidence.md app/config/default.yaml app/config/algorithm-modules.README.md
```

Expected: no whitespace errors.

---
