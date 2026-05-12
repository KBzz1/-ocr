import pytest
from app.backend.errors import AppError, ErrorCode
from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates


def test_valid_candidates_pass():
    validate_field_candidates([
        {"field_key": "chief_complaint", "original_value": "头痛3天", "confidence": 0.95},
        {"field_key": "name", "original_value": "张三", "evidence": None},
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
        {"field_key": "k", "original_value": "x", "unknown_external_attr": {"raw": True}},
    ])
