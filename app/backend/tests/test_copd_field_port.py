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

        def complete_json(self, prompt: str, **kwargs):
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
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
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


def test_default_copd_field_port_builds_qwen_vllm_json_client():
    """默认固定字段抽取路径必须使用 Qwen vLLM OpenAI 客户端，不再冷启动 llama.cpp/GGUF。"""
    from app.backend.services.copd_extraction.port import build_default_copd_field_port
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient

    captured = {}

    class FakeQwenVLLMClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
        },
        field_keys_provider=lambda: list(current_schema_field_keys()),
    )
    # 注入 fake Qwen vLLM client，触发懒构建
    port._qwen_vllm_client = FakeQwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
    )
    port._build_port()
    assert isinstance(port._llm_client, OpenAICompatibleJsonClient)
    assert captured["base_url"] == "http://qwen-vision-vllm-server:8000/v1"
    assert captured["model"] == "Qwen3.5-4B-AWQ-4bit"


def test_default_copd_field_port_does_not_require_llm_model_path():
    """默认路径不再依赖 `llm_model_path` 加载本地 GGUF。"""
    from app.backend.services.copd_extraction.port import build_default_copd_field_port

    class FakeQwenVLLMClient:
        def __init__(self, **kwargs):
            pass

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
        },
        field_keys_provider=lambda: [],
    )
    port._qwen_vllm_client = FakeQwenVLLMClient()
    port._build_port()
    assert port is not None


def test_default_copd_field_port_does_not_invoke_llama_cpp_builder(monkeypatch):
    """默认路径不得调用 build_llama_cpp_client。"""
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import build_default_copd_field_port

    invoked = {"count": 0}

    def fake_builder(*args, **kwargs):
        invoked["count"] += 1
        return None

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", fake_builder)

    class FakeQwenVLLMClient:
        def __init__(self, **kwargs):
            pass

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
        },
        field_keys_provider=lambda: [],
    )
    port._qwen_vllm_client = FakeQwenVLLMClient()
    port._build_port()

    assert invoked["count"] == 0, "默认路径不应触发 build_llama_cpp_client"
