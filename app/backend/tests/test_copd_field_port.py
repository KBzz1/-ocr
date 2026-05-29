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
