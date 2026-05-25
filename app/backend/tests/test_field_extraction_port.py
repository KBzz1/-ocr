import pytest
from app.backend.errors import AppError, ErrorCode
from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates


def test_valid_candidates_pass():
    validate_field_candidates([
        {"field_key": "chief_complaint", "original_value": "头痛3天", "confidence": 0.95,
         "extraction_status": "extracted", "verification_status": "not_checked",
         "quality_flags": [], "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
         "evidence": "头痛3天"},
        {"field_key": "name", "original_value": "张三", "evidence": None,
         "extraction_status": "not_found", "verification_status": "not_checked",
         "quality_flags": [], "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""}},
    ])


@pytest.mark.parametrize("payload", [
    {"field_key": "chief_complaint"},
    ["not-a-dict"],
    [{"original_value": "x"}],
    [{"field_key": "", "original_value": "x"}],
    [{"field_key": 123, "original_value": "x"}],
    [{"field_key": "k"}],
    [{"field_key": "k", "original_value": 123}],
    [{"field_key": "k", "original_value": "x", "confidence": "high"}],
    [{"field_key": "k", "original_value": "x", "evidence": 42}],
])
def test_invalid_candidates_raise_contract_invalid(payload):
    with pytest.raises(AppError) as exc_info:
        validate_field_candidates(payload)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_extra_fields_are_allowed():
    validate_field_candidates([
        {"field_key": "k", "original_value": "x", "unknown_external_attr": {"raw": True},
         "extraction_status": "extracted", "verification_status": "not_checked",
         "quality_flags": [], "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
         "evidence": "x"},
    ])


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
    validate_field_candidates([_valid_field_result()])


def test_validate_field_result_allows_extracted_missing_evidence_when_marked_suspicious():
    item = _valid_field_result()
    item["evidence"] = None
    item["source_hint"] = "主诉"
    item["source_group_id"] = None
    item["verification_status"] = "suspicious"
    item["quality_flags"] = [
        {"flag": "source_section_not_found", "severity": "warning", "message": "source_hint 未定位"}
    ]

    validate_field_candidates([item])


def test_validate_field_result_rejects_missing_ocr_correction():
    item = _valid_field_result()
    del item["ocr_correction"]

    with pytest.raises(AppError):
        validate_field_candidates([item])


def test_validate_field_result_rejects_invalid_status():
    item = _valid_field_result()
    item["verification_status"] = "maybe"

    with pytest.raises(AppError):
        validate_field_candidates([item])


from app.backend.services.algorithm_ports.fixtures import FixtureFieldPort


class TestFixtureFieldPort:
    def test_fixture_preserves_preset_candidates(self):
        candidates = [{"field_key": "chief_complaint", "original_value": "预置值", "evidence": None, "confidence": 0.9}]
        port = FixtureFieldPort(candidates=candidates)
        result = port.extract({"task_id": "t1", "document_result": {}, "schema": {"version": "v1"}})
        assert result == candidates

    def test_fixture_default_candidates(self):
        port = FixtureFieldPort()
        result = port.extract({"task_id": "t1", "document_result": {}, "schema": {"version": "v1"}})
        assert len(result) == 1
        assert result[0]["field_key"] == "chief_complaint"

    def test_fixture_return_empty(self):
        port = FixtureFieldPort(return_empty=True)
        result = port.extract({"task_id": "t1", "document_result": {}, "schema": {"version": "v1"}})
        assert result == []

    def test_fixture_should_fail_raises(self):
        port = FixtureFieldPort(should_fail=True)
        with pytest.raises(RuntimeError, match="fixture field extraction failure"):
            port.extract({"task_id": "t1", "document_result": {}, "schema": {"version": "v1"}})

    def test_fixture_does_not_parse_schema_or_document(self):
        port = FixtureFieldPort(candidates=[{"field_key": "fixed", "original_value": "fixed_val", "confidence": 0.5}])
        result = port.extract({"task_id": "t1", "document_result": {"pages": []}, "schema": {"fields": []}})
        assert result[0]["field_key"] == "fixed"
