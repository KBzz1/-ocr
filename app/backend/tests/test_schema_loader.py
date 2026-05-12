import os
import tempfile
import pytest
import yaml
from app.backend.errors import AppError, ErrorCode


def _write_yaml(tmpdir, filename, data):
    path = os.path.join(tmpdir, filename)
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
            }
        ],
    }


class TestSchemaLoaderValid:
    def test_load_valid_schema_returns_dict(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        path = _write_yaml(tmpdir, "schema.yaml", _valid_schema())
        result = load_schema(path)
        assert isinstance(result, dict)
        assert result["version"] == "1.0.0"
        assert result["document_type"] == "general_medical_record"
        assert len(result["field_groups"]) == 1

    def test_load_normalized_defaults_for_required_and_hint(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        # required/hint 不提供，验证默认值
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        field = result["field_groups"][0]["fields"][0]
        assert field["required"] is False
        assert field["hint"] == ""

    def test_type_defaults_to_string_when_missing(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["field_groups"][0]["fields"][0]["type"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        assert result["field_groups"][0]["fields"][0]["type"] == "string"

    def test_field_groups_order_preserved(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = {
            "version": "1.0.0",
            "document_type": "test",
            "field_groups": [
                {"group_key": "c", "group_label": "第三",
                 "fields": [{"field_key": "f3", "label": "f3"}]},
                {"group_key": "a", "group_label": "第一",
                 "fields": [{"field_key": "f1", "label": "f1"}]},
                {"group_key": "b", "group_label": "第二",
                 "fields": [{"field_key": "f2", "label": "f2"}]},
            ],
        }
        path = _write_yaml(tmpdir, "schema.yaml", schema)
        result = load_schema(path)
        group_keys = [g["group_key"] for g in result["field_groups"]]
        assert group_keys == ["c", "a", "b"]


class TestSchemaLoaderReject:
    def test_load_missing_file_raises(self):
        from app.backend.services.schema_loader import load_schema

        with pytest.raises(AppError) as exc_info:
            load_schema("/nonexistent/schema.yaml")
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_version(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["version"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_document_type(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["document_type"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_empty_field_groups(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"] = []
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_duplicate_field_key(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"][0]["fields"].append(
            {"field_key": "name", "label": "重复字段"}
        )
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_missing_field_label(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        del schema["field_groups"][0]["fields"][0]["label"]
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_invalid_field_type(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"][0]["fields"][0]["type"] = "datetime"
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code

    def test_reject_duplicate_group_key(self):
        from app.backend.services.schema_loader import load_schema

        tmpdir = tempfile.mkdtemp()
        schema = _valid_schema()
        schema["field_groups"].append({
            "group_key": "basic",
            "group_label": "重复组",
            "fields": [{"field_key": "x", "label": "x"}],
        })
        path = _write_yaml(tmpdir, "schema.yaml", schema)

        with pytest.raises(AppError) as exc_info:
            load_schema(path)
        assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR.code
