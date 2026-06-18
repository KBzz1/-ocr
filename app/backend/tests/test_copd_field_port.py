import threading
import time
from concurrent.futures import ThreadPoolExecutor


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


def test_lazy_copd_field_port_reuses_llm_client_until_closed(monkeypatch):
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def __init__(self):
            self.closed = False

        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "evidence": "反复咳嗽、咳痰15年",
                        "confidence": 0.8,
                        "source_section": "history_profile",
                        "extraction_status": "extracted",
                        "verification_status": "not_checked",
                        "quality_flags": [],
                        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                    }
                ]
            }

        def close(self):
            self.closed = True

    built_clients = []

    def build_client(*args, **kwargs):
        client = FakeLlmClient()
        built_clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", build_client)
    port = _LazyCOPDFieldPort(
        model_path="/tmp/model.gguf",
        field_keys=["copd_history_years"],
        enable_verification=False,
    )

    first = port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})
    second = port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})

    assert first[0]["field_key"] == "copd_history_years"
    assert second[0]["field_key"] == "copd_history_years"
    assert len(built_clients) == 1
    assert built_clients[0].closed is False
    assert port._port is not None

    port.close()

    assert built_clients[0].closed is True
    assert port._port is None


def test_lazy_copd_field_port_keeps_client_loaded_after_group_failure(monkeypatch):
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def __init__(self):
            self.closed = False

        def complete_json(self, prompt: str):
            raise RuntimeError("LLM failed")

        def close(self):
            self.closed = True

    built_clients = []

    def build_client(*args, **kwargs):
        client = FakeLlmClient()
        built_clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", build_client)
    port = _LazyCOPDFieldPort(model_path="/tmp/model.gguf", field_keys=["copd_history_years"])

    result = port.extract({"document_result": {"merged_text": "主诉：反复咳嗽。"}})

    assert result[0]["extraction_status"] == "not_found"
    assert result[0]["verification_status"] == "suspicious"
    assert result[0]["quality_flags"][0]["flag"] == "llm_group_failed"
    assert built_clients[0].closed is False
    assert port._port is not None

    port.close()

    assert built_clients[0].closed is True
    assert port._port is None


def test_lazy_copd_field_port_rebuilds_client_after_close(monkeypatch):
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def __init__(self):
            self.closed = False

        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "copd_history_years", "original_value": "15年", "source_hint": "主诉"}]}

        def close(self):
            self.closed = True

    built_clients = []

    def build_client(*args, **kwargs):
        client = FakeLlmClient()
        built_clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", build_client)
    port = _LazyCOPDFieldPort(model_path="/tmp/model.gguf", field_keys=["copd_history_years"])

    port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})
    port.close()
    port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})

    assert len(built_clients) == 2
    assert built_clients[0].closed is True
    assert built_clients[1].closed is False


def test_lazy_copd_field_port_builds_single_client_for_concurrent_first_requests(monkeypatch):
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "copd_history_years", "original_value": "15年", "source_hint": "主诉"}]}

        def close(self):
            pass

    built_clients = []

    def build_client(*args, **kwargs):
        time.sleep(0.05)
        client = FakeLlmClient()
        built_clients.append(client)
        return client

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", build_client)
    port = _LazyCOPDFieldPort(model_path="/tmp/model.gguf", field_keys=["copd_history_years"])
    barrier = threading.Barrier(2)

    def extract_once():
        barrier.wait()
        return port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: extract_once(), range(2)))

    assert len(results) == 2


def test_copd_field_port_aborts_at_section_group_boundary_when_cancelled(monkeypatch):
    """取消 token 在第一个 section group 跑完后被 set,第二次循环检查时应抛
    REEXTRACTION_CANCELLED,不会继续发起后续 LLM 调用。"""
    from app.backend.errors import AppError, ErrorCode
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def __init__(self):
            self.call_count = 0

        def complete_json(self, prompt: str):
            self.call_count += 1
            return {
                "fields": [
                    {
                        "field_key": "occupation",
                        "original_value": "退休",
                        "evidence": "职业:退休",
                        "confidence": 0.7,
                        "source_hint": "个人史",
                        "source_section": "个人史",
                        "extraction_status": "extracted",
                        "verification_status": "not_checked",
                        "quality_flags": [],
                        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
                    }
                ]
            }

        def close(self):
            pass

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", lambda *a, **k: FakeLlmClient())
    port = _LazyCOPDFieldPort(
        model_path="/tmp/model.gguf",
        field_keys=[
            "occupation",
            "temperature",
            "blood_gas_ph",
        ],
        enable_verification=False,
    )

    event = threading.Event()

    # 拦截 complete_json 在第一次调用结束时把 event set 掉,模拟"批次完成时用户点击取消"
    real_client_holder = {}

    def build_client_intercepting(*args, **kwargs):
        real = FakeLlmClient()
        real_client_holder["client"] = real

        class Intercepting:
            def __init__(self, inner):
                self._inner = inner

            def complete_json(self, prompt):
                result = self._inner.complete_json(prompt)
                event.set()
                return result

            def close(self):
                self._inner.close()

        return Intercepting(real)

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", build_client_intercepting)
    port = _LazyCOPDFieldPort(
        model_path="/tmp/model.gguf",
        field_keys=["occupation", "temperature", "blood_gas_ph"],
        enable_verification=False,
    )

    import pytest

    with pytest.raises(AppError) as exc_info:
        port.extract(
            {
                "document_result": {
                    "merged_text": "主诉:咳痰. 个人史:职业:退休. 体格检查:T 36.5℃. 辅助检查:血气 pH 7.40.",
                },
                "cancellation_token": event,
            }
        )

    assert exc_info.value.code == ErrorCode.REEXTRACTION_CANCELLED.code
    # 第一个 group 跑完,后续 group 在批次间检查到 cancel 就停;真实 LLM 不会被
    # 第二次及之后调用。SECTION_GROUPS 共 3 组,所以 ≤ 1 次。
    assert real_client_holder["client"].call_count <= 1


def test_copd_field_port_raises_immediately_when_cancelled_before_first_call(monkeypatch):
    from app.backend.errors import AppError, ErrorCode
    from app.backend.services.copd_extraction import llm_client as llm_module
    from app.backend.services.copd_extraction.port import _LazyCOPDFieldPort

    class FakeLlmClient:
        def __init__(self):
            self.call_count = 0

        def complete_json(self, prompt: str):
            self.call_count += 1
            return {"fields": []}

        def close(self):
            pass

    monkeypatch.setattr(llm_module, "build_llama_cpp_client", lambda *a, **k: FakeLlmClient())
    port = _LazyCOPDFieldPort(
        model_path="/tmp/model.gguf",
        field_keys=["occupation"],
        enable_verification=False,
    )

    event = threading.Event()
    event.set()  # 用户在第一次 LLM 之前就点击了取消

    import pytest

    with pytest.raises(AppError) as exc_info:
        port.extract(
            {
                "document_result": {"merged_text": "主诉:咳痰"},
                "cancellation_token": event,
            }
        )

    assert exc_info.value.code == ErrorCode.REEXTRACTION_CANCELLED.code
