"""JSON Schema response formats for the fixed-field extraction pipeline.

The schemas in this module constrain only the JSON shape.  Evidence
existence, field coverage/order, and semantic grounding remain backend
responsibilities and are deliberately validated after decoding.
"""
from __future__ import annotations


def schema_field_keys(schema: dict) -> list[str]:
    """Return schema field keys in their persisted order."""
    keys: list[str] = []
    for group in schema.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            key = field.get("field_key")
            if isinstance(key, str) and key:
                keys.append(key)
    return keys


def build_extraction_json_schema(schema: dict) -> dict:
    """Build the vLLM/OpenAI ``json_schema`` response format for extraction."""
    field_keys = schema_field_keys(schema)
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["field_key", "status", "value", "evidence_ids"],
        "properties": {
            "field_key": {"type": "string", "enum": field_keys},
            "status": {"type": "string", "enum": ["found", "not_found", "uncertain"]},
            "value": {"type": "string"},
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }
    document_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "document_type", "fields"],
        "properties": {
            "schema_version": {"type": "string", "enum": [schema.get("version", "")]},
            "document_type": {"type": "string", "enum": [schema.get("document_type", "")]},
            "fields": {
                "type": "array",
                "minItems": len(field_keys),
                "maxItems": len(field_keys),
                "items": item_schema,
            },
        },
    }
    return {
        "name": "admission_record_structured_fields",
        "strict": True,
        "schema": document_schema,
    }


def build_verification_json_schema(fields: list[dict]) -> dict:
    """Build the response format for one verifier request.

    The generated schema emits only ``pass``/``suspicious``.  The parser still
    accepts historical ``fail`` responses so archived runs remain readable.
    """
    field_keys = [
        f.get("field_key") for f in fields or []
        if isinstance(f, dict) and isinstance(f.get("field_key"), str) and f.get("field_key")
    ]
    checks = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "grounding_supported",
            "field_scope_valid",
            "text_standard",
            "logic_consistent",
        ],
        "properties": {
            "grounding_supported": {"type": "boolean"},
            "field_scope_valid": {"type": "boolean"},
            "text_standard": {"type": "boolean"},
            "logic_consistent": {"type": "boolean"},
        },
    }
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["field_key", "verdict", "reason_code", "checks", "comment"],
        "properties": {
            "field_key": {"type": "string", "enum": field_keys},
            "verdict": {"type": "string", "enum": ["pass", "suspicious"]},
            "reason_code": {
                "type": "string",
                "enum": ["extraction_mistake", "nonstandard_expression", "none"],
            },
            "checks": checks,
            "comment": {"type": "string", "maxLength": 40},
        },
    }
    return {
        "name": "copd_field_verifications",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["verifications"],
            "properties": {
                "verifications": {
                    "type": "array",
                    "minItems": len(field_keys),
                    "maxItems": len(field_keys),
                    "items": item_schema,
                }
            },
        },
    }
