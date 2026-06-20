from abc import ABC, abstractmethod


class LlmClient(ABC):
    @abstractmethod
    def complete_json(self, prompt: str) -> dict:
        ...

    def close(self) -> None:
        return None


class OpenAICompatibleJsonClient(LlmClient):
    """Qwen vLLM OpenAI-compatible 客户端的 LlmClient 适配。

    真实延迟 / 超时 / 模型 / base_url 都由注入的 QwenVLLMClient 持有。
    本类只负责把 LlmClient.complete_json(prompt) 签名翻译成
    ``QwenVLLMClient.complete_json(prompt, max_tokens, temperature)``。
    """

    def __init__(self, qwen_client, max_tokens: int = 8192, temperature: float = 0.0):
        self._qwen_client = qwen_client
        self._max_tokens = max_tokens
        self._temperature = temperature

    def complete_json(self, prompt: str) -> dict:
        return self._qwen_client.complete_json(
            prompt=prompt,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )

    def close(self) -> None:
        close = getattr(self._qwen_client, "close", None)
        if callable(close):
            close()
