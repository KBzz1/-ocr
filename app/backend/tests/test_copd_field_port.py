import pytest


def test_lazy_copd_field_port_closes_llm_client_after_success(monkeypatch):
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

    result = port.extract({"document_result": {"merged_text": "主诉：反复咳嗽、咳痰15年。"}})

    assert result[0]["field_key"] == "copd_history_years"
    assert built_clients[0].closed is True
    assert port._port is None


def test_lazy_copd_field_port_closes_llm_client_after_failure(monkeypatch):
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

    with pytest.raises(RuntimeError, match="LLM failed"):
        port.extract({"document_result": {"merged_text": "主诉：反复咳嗽。"}})

    assert built_clients[0].closed is True
    assert port._port is None
