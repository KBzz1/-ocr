import os
import tempfile
import pytest
import yaml


def _write_schema(tmpdir, data):
    path = os.path.join(tmpdir, "schema.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)
    return path


def _valid_schema():
    return {
        "version": "1.0.0",
        "document_type": "general_medical_record",
        "field_groups": [
            {
                "group_key": "basic",
                "group_label": "基本信息",
                "fields": [
                    {"field_key": "name", "label": "姓名", "type": "string"},
                    {"field_key": "age", "label": "年龄", "type": "number"},
                ],
            },
            {
                "group_key": "exam",
                "group_label": "检查",
                "fields": [
                    {"field_key": "temp", "label": "体温", "type": "string"},
                ],
            },
        ],
    }


class TestSchemaService:
    @staticmethod
    def _make_service(tmpdir, schema_data=None):
        from app.backend.services.schema_service import SchemaService

        data = schema_data if schema_data is not None else _valid_schema()
        path = _write_schema(tmpdir, data)
        return SchemaService(path)

    def test_get_current_returns_schema_dict(self, tmp_path):
        service = self._make_service(tmp_path)
        schema = service.get_current()
        assert schema["version"] == "1.0.0"
        assert len(schema["field_groups"]) == 2

    def test_get_current_version(self, tmp_path):
        service = self._make_service(tmp_path)
        assert service.get_current_version() == "1.0.0"

    def test_get_allowed_field_keys(self, tmp_path):
        service = self._make_service(tmp_path)
        keys = service.get_allowed_field_keys()
        assert keys == {"name", "age", "temp"}

    def test_get_field_order_returns_ordered_list(self, tmp_path):
        service = self._make_service(tmp_path)
        order = service.get_field_order()
        assert order == ["name", "age", "temp"]

    def test_build_validator_returns_schema_validator(self, tmp_path):
        from app.backend.services.schema_validator import SchemaValidator

        service = self._make_service(tmp_path)
        validator = service.build_validator()
        assert isinstance(validator, SchemaValidator)

    def test_cache_reuses_loaded_schema(self, tmp_path):
        service = self._make_service(tmp_path)
        first = service.get_current()
        second = service.get_current()
        assert first is second
