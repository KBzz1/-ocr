def test_verification_prompt_keeps_comments_short():
    from app.backend.services.copd_extraction.prompts import build_verification_prompt

    prompt = build_verification_prompt([{"field_key": "bmi", "original_value": "24.2"}])

    assert "comment 不超过 40 个汉字" in prompt


def test_openai_compatible_json_client_uses_qwen_vllm_client():
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient

    class FakeQwenVLLMClient:
        def __init__(self, result):
            self.result = result
            self.calls = []

        def complete_json(self, prompt, max_tokens, temperature):
            self.calls.append({
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            })
            return self.result

    fake_qwen = FakeQwenVLLMClient(
        {"schema_version": "admission_record_structured_fields.v1", "fields": []}
    )
    client = OpenAICompatibleJsonClient(fake_qwen, max_tokens=8192, temperature=0.0)

    result = client.complete_json("prompt")

    assert result["schema_version"] == "admission_record_structured_fields.v1"
    assert fake_qwen.calls[-1]["max_tokens"] == 8192
    assert fake_qwen.calls[-1]["temperature"] == 0.0


def test_openai_compatible_json_client_propagates_qwen_runtime_error():
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient

    class BrokenQwenVLLMClient:
        def complete_json(self, prompt, max_tokens, temperature):
            raise RuntimeError("Qwen vLLM 响应结构非法")

    client = OpenAICompatibleJsonClient(BrokenQwenVLLMClient(), max_tokens=1024, temperature=0.0)

    try:
        client.complete_json("prompt")
    except RuntimeError as exc:
        assert "Qwen vLLM" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
