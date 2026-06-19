"""Tests for the Qwen admission_record_structured_fields.v1 contract.

These tests verify that the backend strictly enforces the fixed-field contract
for the new Qwen structured extraction path:

- payload must cover every schema field exactly once
- payload must not introduce or duplicate field_keys outside the schema
- evidence is *refilled* from backend evidence_units, never fabricated
- field-level attention (suspicious evidence / missing evidence) is a
  per-field concern and must not bubble up as a task-level contract failure
- diagnosis values pass through verbatim, with no normalization
"""

import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.copd_extraction.admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _schema() -> dict:
    """Minimal schema mirroring ``admission_record_structured_fields.v1``.

    Three groups covering 4 fields total so we can test ordering, presence
    and unknown field rejection without depending on the full 61-field table.
    """
    return {
        "version": "admission_record_structured_fields.v1",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": "chief_complaint",
                "group_label": "主诉",
                "fields": [
                    {"field_key": "chief_complaint", "label": "主诉", "type": "string"},
                ],
            },
            {
                "group_key": "physical_examination",
                "group_label": "体格检查",
                "fields": [
                    {"field_key": "pe_temperature", "label": "体温", "type": "string"},
                    {"field_key": "pe_pulse", "label": "脉搏", "type": "string"},
                ],
            },
            {
                "group_key": "diagnosis",
                "group_label": "诊断",
                "fields": [
                    {"field_key": "diagnosis_final", "label": "最终诊断", "type": "string"},
                ],
            },
        ],
    }


def _evidence_units() -> list[dict]:
    return [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年。",
            "start_offset": 0,
            "end_offset": 14,
            "page_no": 1,
        },
        {
            "id": "u002",
            "text": "体温 36.7℃",
            "start_offset": 20,
            "end_offset": 30,
            "page_no": 1,
        },
        {
            "id": "u003",
            "text": "脉搏 80次/分",
            "start_offset": 31,
            "end_offset": 40,
            "page_no": 1,
        },
    ]


def _valid_payload() -> dict:
    return {
        "schema_version": "admission_record_structured_fields.v1",
        "document_type": "copd_admission_record",
        "fields": [
            {
                "section_key": "chief_complaint",
                "section_label": "主诉",
                "field_key": "chief_complaint",
                "field_label": "主诉",
                "status": "found",
                "value": "反复咳嗽、咳痰15年",
                "evidence_ids": ["u001"],
            },
            {
                "section_key": "physical_examination",
                "section_label": "体格检查",
                "field_key": "pe_temperature",
                "field_label": "体温",
                "status": "found",
                "value": "36.7℃",
                "evidence_ids": ["u002"],
            },
            {
                "section_key": "physical_examination",
                "section_label": "体格检查",
                "field_key": "pe_pulse",
                "field_label": "脉搏",
                "status": "not_found",
                "value": "",
                "evidence_ids": [],
            },
            {
                "section_key": "diagnosis",
                "section_label": "诊断",
                "field_key": "diagnosis_final",
                "field_label": "最终诊断",
                "status": "uncertain",
                "value": "慢性阻塞性肺疾病急性加重",
                "evidence_ids": [],
            },
        ],
    }


# ---------------------------------------------------------------------------
# validate_qwen_payload: structural enforcement
# ---------------------------------------------------------------------------


def test_validate_qwen_payload_requires_all_schema_fields():
    schema = _schema()
    payload = _valid_payload()
    # drop one schema field
    payload["fields"] = [f for f in payload["fields"] if f["field_key"] != "pe_pulse"]

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_rejects_schema_outside_field():
    schema = _schema()
    payload = _valid_payload()
    # inject a field that is not in the schema
    payload["fields"].append({
        "section_key": "chief_complaint",
        "section_label": "主诉",
        "field_key": "evil_extra",
        "field_label": "多余字段",
        "status": "found",
        "value": "x",
        "evidence_ids": [],
    })

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_rejects_duplicate_field():
    schema = _schema()
    payload = _valid_payload()
    payload["fields"].append(dict(payload["fields"][0]))

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_rejects_wrong_schema_version():
    schema = _schema()
    payload = _valid_payload()
    payload["schema_version"] = "wrong.v1"

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_rejects_wrong_document_type():
    schema = _schema()
    payload = _valid_payload()
    payload["document_type"] = "progress_note"

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_rejects_extra_top_level_key():
    schema = _schema()
    payload = _valid_payload()
    payload["legacy_source_hint"] = "旧字段"

    with pytest.raises(AppError) as exc_info:
        validate_qwen_payload(payload, schema)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_validate_qwen_payload_accepts_not_found_without_attention():
    schema = _schema()
    payload = _valid_payload()

    # Structural validation: validate_qwen_payload is the structural gate
    # and returns the schema-ordered payload fields verbatim. It does NOT
    # refill evidence; that is map_qwen_fields_to_review_candidates' job.
    normalized = validate_qwen_payload(payload, schema)
    not_found_entry = next(f for f in normalized if f["field_key"] == "pe_pulse")
    assert not_found_entry["status"] == "not_found"
    assert not_found_entry["value"] == ""
    assert not_found_entry["evidence_ids"] == []

    # The mapping step (Task 5's call site) translates status -> attention
    # and refills evidence from the backend units.
    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, _evidence_units()
    )
    not_found_candidate = next(c for c in candidates if c["field_key"] == "pe_pulse")
    assert not_found_candidate["extraction_status"] == "not_found"
    assert not_found_candidate["original_value"] == ""
    assert not_found_candidate["evidence"] == []
    assert not_found_candidate["attention_required"] is False
    assert not_found_candidate["attention_message"] == ""


def test_validate_qwen_payload_maps_found_with_evidence_array():
    schema = _schema()
    payload = _valid_payload()

    # validate_qwen_payload returns the raw Qwen payload fields in schema
    # order; it does not refill evidence.
    normalized = validate_qwen_payload(payload, schema)
    found_entry = next(f for f in normalized if f["field_key"] == "chief_complaint")
    assert found_entry["status"] == "found"
    assert found_entry["value"] == "反复咳嗽、咳痰15年"
    assert found_entry["evidence_ids"] == ["u001"]

    # map_qwen_fields_to_review_candidates is the one that does the
    # evidence refill and produces the reviewer-facing extraction_status.
    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, _evidence_units()
    )
    found_candidate = next(c for c in candidates if c["field_key"] == "chief_complaint")
    assert found_candidate["extraction_status"] == "extracted"
    assert found_candidate["original_value"] == "反复咳嗽、咳痰15年"
    assert isinstance(found_candidate["evidence"], list)
    assert len(found_candidate["evidence"]) == 1
    evidence = found_candidate["evidence"][0]
    assert evidence["id"] == "u001"
    assert evidence["text"] == "主诉：反复咳嗽、咳痰15年。"
    assert evidence["start_offset"] == 0
    assert evidence["end_offset"] == 14
    assert evidence["page_no"] == 1


# ---------------------------------------------------------------------------
# map_qwen_fields_to_review_candidates: per-field attention rules
# ---------------------------------------------------------------------------


def _found_missing_evidence_payload() -> dict:
    payload = _valid_payload()
    for f in payload["fields"]:
        if f["field_key"] == "chief_complaint":
            f["status"] = "found"
            f["value"] = "反复咳嗽、咳痰15年"
            f["evidence_ids"] = []
    return payload


def test_found_missing_evidence_becomes_attention_not_task_contract_failure():
    schema = _schema()
    payload = _found_missing_evidence_payload()

    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, _evidence_units()
    )

    chief = next(c for c in candidates if c["field_key"] == "chief_complaint")
    assert chief["extraction_status"] == "extracted"
    assert chief["verification_status"] == "suspicious"
    assert chief["attention_required"] is True
    assert chief["attention_message"] == "缺少来源证据，请核对原文"
    # No fabricated evidence.
    assert chief["evidence"] == []


def _unknown_evidence_id_payload() -> dict:
    payload = _valid_payload()
    for f in payload["fields"]:
        if f["field_key"] == "pe_temperature":
            f["status"] = "found"
            f["value"] = "36.7℃"
            f["evidence_ids"] = ["u999_unknown"]
    return payload


def test_unknown_evidence_id_becomes_attention_not_fake_highlight():
    schema = _schema()
    payload = _unknown_evidence_id_payload()

    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, _evidence_units()
    )

    temperature = next(c for c in candidates if c["field_key"] == "pe_temperature")
    assert temperature["attention_required"] is True
    assert temperature["attention_message"] == "来源片段未在 OCR 文本中定位，请核对"
    # Must not fabricate highlight or text.
    assert temperature["evidence"] == []
    # Internal flag can be retained for audit.
    assert "evidence_id_not_found" in temperature["quality_flags"]


def test_found_with_evidence_unit_missing_offsets_becomes_attention_not_fake_offset():
    """spec: 证据无法定位时不伪造高亮。evidence_unit 缺 start_offset/end_offset
    时该 unit 视为不可定位(跳过),长度不匹配触发 unlocated 提示,
    而不是默认 offset=0 让前端高亮到 merged_text 开头。
    """
    schema = _schema()
    payload = _valid_payload()
    # 单元有 id 和 text 但缺 offset(异常但可能出现的遗留/损坏单元)
    units_missing_offsets = [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年。",
            "page_no": 1,
            # 故意不提供 start_offset / end_offset
        }
    ]

    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, units_missing_offsets
    )
    found = next(c for c in candidates if c["field_key"] == "chief_complaint")
    assert found["attention_required"] is True
    assert found["attention_message"] == "来源片段未在 OCR 文本中定位，请核对"
    # 不得回填出带 offset 的伪造 evidence。
    assert found["evidence"] == []


def test_diagnosis_output_is_not_rewritten_by_adapter():
    schema = _schema()
    payload = _valid_payload()
    raw_diagnosis_text = (
        "1 慢性阻塞性肺疾病急性加重\n"
        "2 Ⅱ型呼吸衰竭\n"
        "3 冠心病\n"
        "4 高血压病3级"
    )
    for f in payload["fields"]:
        if f["field_key"] == "diagnosis_final":
            f["status"] = "found"
            f["value"] = raw_diagnosis_text
            f["evidence_ids"] = []

    candidates = map_qwen_fields_to_review_candidates(
        payload, schema, _evidence_units()
    )

    diagnosis = next(c for c in candidates if c["field_key"] == "diagnosis_final")
    # Adapter must preserve raw diagnosis text verbatim.
    assert diagnosis["original_value"] == raw_diagnosis_text
    # No automatic suffix/prefix/重写.
    assert "建议" not in diagnosis["original_value"]
    assert "推断" not in diagnosis["original_value"]
    # found without evidence -> attention, but value untouched.
    assert diagnosis["attention_required"] is True
    assert diagnosis["attention_message"] == "缺少来源证据，请核对原文"
