from abc import ABC, abstractmethod


class LlmClient(ABC):
    @abstractmethod
    def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        enable_thinking: bool | None = None,
        json_schema: dict | None = None,
    ) -> dict:
        """调用 LLM 并以 JSON 返回结果。

        prompt 为用户消息；system_prompt / enable_thinking / json_schema 可选，
        非空（非 None）时才透传，缺省保持具体客户端默认行为一致。
        """
        ...

    def close(self) -> None:
        return None


class OpenAICompatibleJsonClient(LlmClient):
    """Qwen vLLM OpenAI-compatible 客户端的 LlmClient 适配。

    真实延迟 / 超时 / 模型 / base_url 都由注入的 QwenVLLMClient 持有。
    本类只负责把 LlmClient.complete_json(prompt, system_prompt, enable_thinking, json_schema)
    签名翻译成 ``QwenVLLMClient.complete_json(prompt, max_tokens, temperature,
    system_prompt, enable_thinking)``；system_prompt / enable_thinking 都只在
    非空（非 None）时才透传，缺省保持与 QwenVLLMClient 默认行为一致。
    """

    def __init__(
        self,
        qwen_client,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        enable_thinking: bool | None = None,
    ):
        self._qwen_client = qwen_client
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._enable_thinking = enable_thinking

    def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
        enable_thinking: bool | None = None,
        json_schema: dict | None = None,
    ) -> dict:
        kwargs = {
            "prompt": prompt,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        if system_prompt:
            kwargs["system_prompt"] = system_prompt
        thinking = enable_thinking if enable_thinking is not None else self._enable_thinking
        if thinking is not None:
            kwargs["enable_thinking"] = thinking
        if json_schema is not None:
            kwargs["json_schema"] = json_schema
        return self._qwen_client.complete_json(**kwargs)

    def close(self) -> None:
        close = getattr(self._qwen_client, "close", None)
        if callable(close):
            close()
