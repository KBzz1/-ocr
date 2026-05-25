def test_llama_cpp_client_parses_json_response():
    from app.backend.services.copd_extraction.llm_client import LlamaCppClient

    class FakeLlama:
        def __init__(self):
            self.max_tokens = None

        def create_chat_completion(self, messages, temperature, max_tokens, response_format=None):
            self.max_tokens = max_tokens
            return {"choices": [{"message": {"content": '{"fields":[{"field_key":"bmi"}]}'}}]}

    fake_llama = FakeLlama()
    client = LlamaCppClient(llama=fake_llama)

    assert client.complete_json("prompt") == {"fields": [{"field_key": "bmi"}]}
    assert fake_llama.max_tokens == 1024


def test_llama_cpp_client_accepts_fenced_json_with_trailing_commas():
    from app.backend.services.copd_extraction.llm_client import LlamaCppClient

    class FakeLlama:
        def create_chat_completion(self, messages, temperature, max_tokens, response_format=None):
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
下面是结果：
```json
{
  "fields": [
    {
      "field_key": "bmi",
    },
  ],
}
```
"""
                        }
                    }
                ]
            }

    client = LlamaCppClient(llama=FakeLlama())

    assert client.complete_json("prompt") == {"fields": [{"field_key": "bmi"}]}


def test_llama_cpp_client_close_releases_underlying_llama():
    from app.backend.services.copd_extraction.llm_client import LlamaCppClient

    class FakeLlama:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_llama = FakeLlama()
    client = LlamaCppClient(llama=fake_llama)

    client.close()

    assert fake_llama.closed is True
    assert client._llama is None
