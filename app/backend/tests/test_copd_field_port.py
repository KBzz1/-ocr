def test_qwen_admission_port_sends_schema_and_evidence_units(monkeypatch):
    """新固定字段 Qwen 端口：注入 LLM 客户端，构造含 schema + evidence_units 的 prompt，
    并通过 admission_contract 把 LLM 输出映射为 61 个 review-candidate。"""
    from app.backend.services.copd_extraction.admission_contract import (
        map_qwen_fields_to_review_candidates,
    )
    from app.backend.services.copd_extraction.port import build_default_copd_field_port

    captured_prompts: list[str] = []

    class FakeLlmClient:
        def __init__(self):
            self.prompts: list[str] = []

        def complete_json(self, prompt: str):
            self.prompts.append(prompt)
            captured_prompts.append(prompt)
            # Return a full schema payload with one found + many not_found fields
            schema = current_schema()
            fields = []
            for group in schema["field_groups"]:
                for field in group["fields"]:
                    fk = field["field_key"]
                    if fk == "chief_complaint":
                        fields.append({
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "field_key": fk,
                            "field_label": field["label"],
                            "status": "found",
                            "value": "反复咳嗽、咳痰15年，喘息6年，加重1月。",
                            "evidence_ids": ["u001"],
                        })
                    else:
                        fields.append({
                            "section_key": group["group_key"],
                            "section_label": group["group_label"],
                            "field_key": fk,
                            "field_label": field["label"],
                            "status": "not_found",
                            "value": "",
                            "evidence_ids": [],
                        })
            return {
                "schema_version": schema["version"],
                "document_type": schema["document_type"],
                "fields": fields,
            }

        def close(self):
            pass

    fake_client = FakeLlmClient()

    def provider():
        return list(current_schema_field_keys())

    port = build_default_copd_field_port(
        config={
            "llm_model_path": "/tmp/model.gguf",
            "llm_client_factory": lambda *a, **k: fake_client,
        },
        field_keys_provider=provider,
    )

    schema = current_schema()
    evidence_units = [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。",
            "start_offset": 0,
            "end_offset": 23,
            "page_no": 1,
        }
    ]

    result = port.extract({
        "document_result": {
            "merged_text": "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。",
            "evidence_units": evidence_units,
        },
        "evidence_units": evidence_units,
        "schema": schema,
        "document_type": "copd_admission_record",
    })

    # Port must consume evidence_units and the schema via prompt builder
    assert fake_client.prompts, "LLM client must receive the prompt"
    prompt = fake_client.prompts[-1]
    assert "u001" in prompt, "evidence unit id must appear in the prompt"
    assert "chief_complaint" in prompt, "schema field keys must appear in the prompt"

    # Port must return 61 candidates via admission_contract mapping
    assert isinstance(result, list)
    assert len(result) == 61, f"expected 61 schema fields, got {len(result)}"

    # The chief_complaint candidate should be the found one with evidence resolved
    by_key = {c["field_key"]: c for c in result}
    assert by_key["chief_complaint"]["extraction_status"] == "extracted"
    assert by_key["chief_complaint"]["value"] == "反复咳嗽、咳痰15年，喘息6年，加重1月。"
    assert by_key["chief_complaint"]["evidence_ids"] == ["u001"]
    assert isinstance(by_key["chief_complaint"]["evidence"], list)
    assert by_key["chief_complaint"]["evidence"][0]["id"] == "u001"
    assert by_key["chief_complaint"]["evidence"][0]["text"] == evidence_units[0]["text"]

    # Other candidates should be not_found with empty evidence
    assert by_key["pe_temperature"]["extraction_status"] == "not_found"
    assert by_key["pe_temperature"]["evidence"] == []


def current_schema():
    """Load the fixed-fields admission schema used by the active field port."""
    from app.backend.services.schema_loader import load_schema

    return load_schema("app/config/schemas/admission_record_structured_fields.v1.yaml")


def current_schema_field_keys():
    schema = current_schema()
    return [
        field["field_key"]
        for group in schema.get("field_groups", [])
        for field in group.get("fields", [])
    ]
