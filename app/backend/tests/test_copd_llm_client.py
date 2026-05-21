def test_llama_cpp_client_parses_json_response():
    from app.backend.services.copd_extraction.llm_client import LlamaCppClient

    class FakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens, response_format=None):
            return {"choices": [{"message": {"content": '{"fields":[{"field_key":"bmi"}]}'}}]}

    client = LlamaCppClient(llama=FakeLlama())

    assert client.complete_json("prompt") == {"fields": [{"field_key": "bmi"}]}
