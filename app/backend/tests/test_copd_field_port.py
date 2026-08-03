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
            self.system_prompts: list[str] = []

        def complete_json(self, prompt: str, **kwargs):
            self.prompts.append(prompt)
            captured_prompts.append(prompt)
            self.system_prompts.append(kwargs.get("system_prompt", ""))
            # Return a full schema payload with one found + many not_found fields
            schema = current_schema()
            fields = []
            for group in schema["field_groups"]:
                for field in group["fields"]:
                    fk = field["field_key"]
                    if fk == "chief_complaint":
                        fields.append({
                            "field_key": fk,
                            "status": "found",
                            "value": "反复咳嗽、咳痰15年，喘息6年，加重1月。",
                            "evidence_ids": ["u001"],
                        })
                    else:
                        fields.append({
                            "field_key": fk,
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
    # （拆层后：证据单元在 user，schema 字段表在 system）
    assert fake_client.prompts, "LLM client must receive the prompt"
    prompt = fake_client.prompts[-1]
    assert "u001" in prompt, "evidence unit id must appear in the prompt"
    assert "chief_complaint" in fake_client.system_prompts[-1], (
        "schema field keys must appear in the system prompt"
    )

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


def _full_not_found_payload(schema):
    return {
        "schema_version": schema["version"],
        "document_type": schema["document_type"],
        "fields": [
            {
                "field_key": field["field_key"],
                "status": "not_found",
                "value": "",
                "evidence_ids": [],
            }
            for group in schema["field_groups"]
            for field in group["fields"]
        ],
    }


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


def test_qwen_admission_port_does_not_duplicate_merged_ocr_with_evidence_units():
    """已有 evidence_units 时，抽取 prompt 只发送一份证据流。"""
    from app.backend.services.copd_extraction.port import build_default_copd_field_port

    captured_prompts: list[str] = []

    class FakeLlmClient:
        def complete_json(self, prompt: str, **kwargs):
            captured_prompts.append(prompt)
            return _full_not_found_payload(current_schema())

        def close(self):
            pass

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
            "llm_client_factory": lambda *a, **k: FakeLlmClient(),
        },
        field_keys_provider=lambda: list(current_schema_field_keys()),
    )

    evidence_units = [
        {
            "id": "u001",
            "text": "主诉：反复咳嗽、咳痰15年。",
            "start_offset": 0,
            "end_offset": 16,
            "page_no": 1,
        }
    ]
    merged_only_text = "MERGED_OCR_DUPLICATION_SENTINEL"

    result = port.extract({
        "document_result": {
            "merged_text": merged_only_text,
            "evidence_units": evidence_units,
        },
        "evidence_units": evidence_units,
        "schema": current_schema(),
        "document_type": "copd_admission_record",
    })

    assert len(result) == 61
    prompt = captured_prompts[-1]
    assert evidence_units[0]["text"] in prompt
    assert merged_only_text not in prompt


def test_qwen_admission_port_marks_quality_risks_as_suspicious():
    from app.backend.services.copd_extraction.port import build_default_copd_field_port

    class FakeLlmClient:
        def complete_json(self, prompt: str, **kwargs):
            schema = current_schema()
            fields = []
            for group in schema["field_groups"]:
                for field in group["fields"]:
                    fk = field["field_key"]
                    if fk == "pe_pulse":
                        fields.append({
                            "field_key": fk,
                            "status": "found",
                            "value": "36次/分",
                            "evidence_ids": ["u_vitals"],
                        })
                    else:
                        fields.append({
                            "field_key": fk,
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

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
            "llm_client_factory": lambda *a, **k: FakeLlmClient(),
        },
        field_keys_provider=lambda: list(current_schema_field_keys()),
    )

    document_text = "体温36.6℃，脉搏36次/分，呼吸20次/分。心率99次/分，心律规则。"
    evidence_units = [
        {
            "id": "u_vitals",
            "text": "体温36.6℃，脉搏36次/分，呼吸20次/分",
            "start_offset": 0,
            "end_offset": 23,
            "page_no": 1,
        }
    ]

    result = port.extract({
        "document_result": {
            "merged_text": document_text,
            "evidence_units": evidence_units,
        },
        "evidence_units": evidence_units,
        "schema": current_schema(),
        "document_type": "copd_admission_record",
    })

    pulse = next(item for item in result if item["field_key"] == "pe_pulse")
    assert pulse["verification_status"] == "suspicious"
    assert any(flag["flag"] == "ocr_numeric_conflict" for flag in pulse["quality_flags"])


def test_qwen_admission_prompt_real_llm_preserves_denied_pmh_when_enabled():
    """真实 Qwen vLLM 集成测试：验证提示词不会把否认既往史抽成阳性。

    默认跳过，避免普通单测依赖本机 GPU/容器。手动验证时执行：
    MANZUFEI_RUN_LLM_INTEGRATION=1 conda run -n manzufei_ocr python -m pytest \
      app/backend/tests/test_copd_field_port.py::test_qwen_admission_prompt_real_llm_preserves_denied_pmh_when_enabled -q -s
    """
    import os

    import pytest

    if os.environ.get("MANZUFEI_RUN_LLM_INTEGRATION") != "1":
        pytest.skip("set MANZUFEI_RUN_LLM_INTEGRATION=1 to call local Qwen vLLM")

    from app.backend.services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient
    from app.backend.services.copd_extraction.port import COPDAdmissionQwenFieldPort

    schema = current_schema()
    ocr_text = (
        "入院记录\n"
        "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。\n"
        "既往史：平素身体一般，否认“糖尿病”、“冠心病”等病史，"
        "否认肝炎、结核等传染病史。否认外伤及手术史，否认输血史。\n"
        "个人史：吸烟40余年，已戒烟2年。"
    )
    evidence_units = [
        {
            "id": "u_chief_complaint",
            "text": "主诉：反复咳嗽、咳痰15年，喘息6年，加重1月。",
            "start_offset": 5,
            "end_offset": 31,
            "page_no": 1,
            "section_key": "chief_complaint",
        },
        {
            "id": "u_pmh_negation",
            "text": (
                "既往史：平素身体一般，否认“糖尿病”、“冠心病”等病史，"
                "否认肝炎、结核等传染病史。否认外伤及手术史，否认输血史。"
            ),
            "start_offset": 32,
            "end_offset": 91,
            "page_no": 1,
            "section_key": "past_medical_history",
        },
        {
            "id": "u_personal_smoking",
            "text": "个人史：吸烟40余年，已戒烟2年。",
            "start_offset": 92,
            "end_offset": 109,
            "page_no": 1,
            "section_key": "personal_history",
        },
    ]

    base_url = os.environ.get("MANZUFEI_QWEN_VLLM_URL", "http://127.0.0.1:8082/v1")
    model = os.environ.get("MANZUFEI_QWEN_VLLM_MODEL", "Qwen3.5-4B-AWQ-4bit")
    qwen_client = QwenVLLMClient(
        base_url=base_url,
        model=model,
        timeout_seconds=360,
    )
    port = COPDAdmissionQwenFieldPort(
        OpenAICompatibleJsonClient(qwen_client, max_tokens=8192, temperature=0.0)
    )

    result = port.extract({
        "document_result": {
            "merged_text": ocr_text,
            "evidence_units": evidence_units,
        },
        "evidence_units": evidence_units,
        "schema": schema,
        "document_type": "copd_admission_record",
    })

    by_key = {item["field_key"]: item for item in result}
    diabetes_value = by_key["pmh_diabetes"]["value"]
    coronary_value = by_key["pmh_coronary_heart_disease"]["value"]

    print({
        "pmh_diabetes": diabetes_value,
        "pmh_coronary_heart_disease": coronary_value,
        "pmh_hepatitis_b": by_key["pmh_hepatitis_b"]["value"],
    })

    assert "否认" in diabetes_value
    assert "糖尿病" in diabetes_value
    assert "有糖尿病" not in diabetes_value
    assert "否认" in coronary_value
    assert "冠心病" in coronary_value
    assert "有冠心病" not in coronary_value


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


def test_default_copd_field_port_module_has_no_llama_cpp_builder():
    """默认路径不再保留 build_llama_cpp_client。"""
    from app.backend.services.copd_extraction import llm_client as llm_module

    assert not hasattr(llm_module, "build_llama_cpp_client")
    assert not hasattr(llm_module, "LlamaCppClient")


def test_port_extract_runs_injected_verifier():
    """端口注入 verifier 后，extract 在 quality_checks 之后调用一次 verify。"""
    from app.backend.services.copd_extraction.port import COPDAdmissionQwenFieldPort

    class FakeLlmClient:
        def complete_json(self, prompt, **kwargs):
            return _full_not_found_payload(current_schema())

        def close(self):
            pass

    class RecordingVerifier:
        def __init__(self):
            self.called = 0
            self.group_by = None

        def verify(self, candidates, document_text="", group_by=None, evidence_units=None):
            self.called += 1
            self.group_by = group_by
            return []

    recording_verifier = RecordingVerifier()
    port = COPDAdmissionQwenFieldPort(
        llm_client=FakeLlmClient(),
        verifier=recording_verifier,
    )
    result = port.extract({
        "schema": current_schema(),
        "document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"},
        "evidence_units": [],
    })
    assert recording_verifier.called == 1
    assert recording_verifier.group_by == "field"
    assert isinstance(result, list)
    assert len(result) == 61


def test_qwen_admission_port_still_sends_json_schema_constraint():
    """约束解码不动：抽取路径传给 LLM 客户端的 json_schema 仍等于
    build_extraction_json_schema 的完整结构约束（name/strict/schema）。"""
    from app.backend.services.copd_extraction.port import build_default_copd_field_port
    from app.backend.services.copd_extraction.response_schemas import (
        build_extraction_json_schema,
    )

    captured: dict = {}

    class FakeLlmClient:
        def complete_json(self, prompt: str, **kwargs):
            captured.update(kwargs)
            return _full_not_found_payload(current_schema())

        def close(self):
            pass

    port = build_default_copd_field_port(
        config={
            "qwen_vllm_server_url": "http://qwen-vision-vllm-server:8000/v1",
            "qwen_vllm_model_name": "Qwen3.5-4B-AWQ-4bit",
            "qwen_extraction_max_tokens": 8192,
            "qwen_extraction_temperature": 0.0,
            "qwen_extraction_timeout_seconds": 360,
            "llm_client_factory": lambda *a, **k: FakeLlmClient(),
        },
        field_keys_provider=lambda: list(current_schema_field_keys()),
    )

    schema = current_schema()
    port.extract({
        "schema": schema,
        "document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"},
        "evidence_units": [],
    })

    assert "json_schema" in captured, "抽取路径必须继续传递 json_schema 约束"
    assert captured["json_schema"] == build_extraction_json_schema(schema)
    assert captured["json_schema"]["name"] == "admission_record_structured_fields"
    assert captured["json_schema"]["strict"] is True
    assert captured["json_schema"]["schema"]["properties"]["fields"]["minItems"] == 61


def test_llm_client_without_schema_omits_json_schema_for_json_object_fallback():
    """旧无 schema 调用仍走 json_object：OpenAICompatibleJsonClient 不传 json_schema 时，
    底层 Qwen 客户端收不到 json_schema 键（由 qwen_vllm_client 回落到 json_object）。"""
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient

    captured: dict = {}

    class FakeQwenClient:
        def complete_json(self, **kwargs):
            captured.clear()
            captured.update(kwargs)
            return {"ok": True}

    client = OpenAICompatibleJsonClient(FakeQwenClient())

    # 无 json_schema 调用：不传该键
    client.complete_json("旧调用")
    assert "json_schema" not in captured

    # 带 json_schema 调用：透传该键
    client.complete_json("新调用", json_schema={"name": "x", "schema": {"type": "object"}})
    assert captured["json_schema"] == {"name": "x", "schema": {"type": "object"}}
