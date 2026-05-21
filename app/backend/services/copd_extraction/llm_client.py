import json


class LlmClient:
    def complete_json(self, prompt: str):
        raise NotImplementedError


def parse_json_response(content: str):
    return json.loads(content)


class LlamaCppClient(LlmClient):
    def __init__(self, llama):
        self._llama = llama

    def complete_json(self, prompt: str):
        response = self._llama.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        return parse_json_response(content)


def build_llama_cpp_client(model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1):
    from llama_cpp import Llama

    return LlamaCppClient(Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False))
