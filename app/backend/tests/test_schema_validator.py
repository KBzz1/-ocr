import pytest
from app.backend.services.schema_validator import SchemaValidator, SchemaValidationError


class TestSchemaValidator:
    @staticmethod
    def _make_validator(allowed=None):
        return SchemaValidator(allowed or {"name", "age", "gender"})

    def test_validate_empty_candidates_raises(self):
        validator = self._make_validator()
        with pytest.raises(SchemaValidationError, match="候选字段列表为空"):
            validator.validate_candidates([])

    def test_validate_non_list_candidates_raises(self):
        validator = self._make_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_candidates({"field_key": "name"})
        assert exc_info.value.code == "INVALID_LIST"

    def test_validate_non_dict_candidate_raises(self):
        validator = self._make_validator()
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_candidates(["name"])
        assert exc_info.value.code == "INVALID_ITEM"

    def test_validate_unknown_field_key_raises(self):
        validator = self._make_validator()
        candidates = [{"field_key": "unknown_field", "value": "x"}]
        with pytest.raises(SchemaValidationError, match="unknown_field"):
            validator.validate_candidates(candidates)

    def test_validate_duplicate_field_key_raises(self):
        validator = self._make_validator()
        candidates = [
            {"field_key": "name", "value": "a"},
            {"field_key": "name", "value": "b"},
        ]
        with pytest.raises(SchemaValidationError, match="重复"):
            validator.validate_candidates(candidates)

    def test_validate_missing_field_key_raises(self):
        validator = self._make_validator()
        candidates = [{"value": "x"}]
        with pytest.raises(SchemaValidationError, match="缺少 field_key"):
            validator.validate_candidates(candidates)

    def test_validate_valid_candidates_passes(self):
        validator = self._make_validator()
        candidates = [
            {"field_key": "name", "value": "张三"},
            {"field_key": "age", "value": "30"},
        ]
        result = validator.validate_candidates(candidates)
        assert result == candidates

    def test_validate_alias_accepts_be05_signature(self):
        validator = self._make_validator()
        candidates = [{"field_key": "name", "value": "张三"}]
        result = validator.validate(candidates, {"version": "1.0.0"})
        assert result == candidates
