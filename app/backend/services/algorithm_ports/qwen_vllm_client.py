"""Qwen Vision vLLM 共享 OpenAI-compatible 客户端。

后端通过 OpenAI Python SDK 调本地 qwen-vision-vllm-server 的 /v1。
同一个客户端既支持图片 OCR（`complete_text_from_image`），也支持
text-only 固定字段 JSON 抽取（`complete_json`），复用同一个常驻 vLLM 服务。
"""
import base64
import json
import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_IMAGE_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_THINK_OPEN_TAG_RE = re.compile(r"<think>", flags=re.IGNORECASE)

try:
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


def detect_image_mime(image_path) -> str:
    """根据扩展名推断图片 MIME；不在支持列表内抛 ValueError。"""
    suffix = Path(str(image_path)).suffix.lower()
    if suffix not in _IMAGE_MIME_BY_EXT:
        raise ValueError(
            f"unsupported image extension for Qwen vLLM: {suffix!r}; "
            f"支持: {sorted(_IMAGE_MIME_BY_EXT)}"
        )
    return _IMAGE_MIME_BY_EXT[suffix]


def strip_think_blocks(text: str) -> str:
    """清理模型输出里的 <think>...</think> 段，避免污染 OCR 文本或 JSON 解析。

    - 完整闭合的 <think>...</think> 段被完全丢弃；
    - 单独的 `<think>` 开标签（未闭合）只删除标签本身，保留后续文本，
      防止模型截断时把真实正文带没。
    """
    if not text:
        return ""
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_OPEN_TAG_RE.sub("", cleaned)
    return cleaned.strip()


class QwenVLLMClient:
    """OpenAI SDK 客户端的薄包装，承载 OCR 与固定字段抽取。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        openai_client=None,
        api_key: str = "not-needed",
        timeout_seconds: float = 240.0,
    ):
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        if openai_client is None:
            if OpenAI is None:
                raise RuntimeError(
                    "缺少 openai SDK；请在 requirements.txt 中确认 openai>=1.0,<2.0"
                )
            self._client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=timeout_seconds,
                http_client=httpx.Client(trust_env=False),
            )
        else:
            self._client = openai_client

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def _common_kwargs(self, max_tokens: int, temperature: float) -> dict:
        return {
            "model": self._model,
            "temperature": temperature,
            "top_p": 1.0,
            "max_tokens": max_tokens,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }

    def complete_text_from_image(
        self,
        image_path,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        image_path = Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(f"OCR 输入图片不存在: {image_path}")

        mime = detect_image_mime(image_path)
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime};base64,{encoded}"

        content = [
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        if user_prompt:
            content.append({"type": "text", "text": user_prompt})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ]

        kwargs = self._common_kwargs(max_tokens=max_tokens, temperature=temperature)
        kwargs["messages"] = messages

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Qwen vLLM image OCR 调用失败 model=%s base_url=%s: %s",
                self._model, self._base_url, type(exc).__name__,
            )
            raise RuntimeError(f"Qwen vLLM 调用失败: {exc}") from exc

        return self._extract_text(response)

    def complete_json(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None = None,
    ) -> dict:
        kwargs = self._common_kwargs(max_tokens=max_tokens, temperature=temperature)
        if system_prompt:
            kwargs["messages"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        else:
            kwargs["messages"] = [{"role": "user", "content": prompt}]
        kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Qwen vLLM JSON 调用失败 model=%s base_url=%s: %s",
                self._model, self._base_url, type(exc).__name__,
            )
            raise RuntimeError(f"Qwen vLLM 调用失败: {exc}") from exc

        content = self._extract_text(response)
        if not content:
            raise RuntimeError("Qwen vLLM 返回为空")
        normalized = _normalize_json_response(content)
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError as exc:
            tail = normalized[-200:] if len(normalized) > 200 else normalized
            logger.error(
                "Qwen vLLM JSON 解析失败 model=%s tail=%s",
                self._model, tail,
            )
            raise RuntimeError(f"Qwen vLLM 返回非 JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Qwen vLLM JSON 顶层必须是对象")
        return parsed

    def _extract_text(self, response) -> str:
        try:
            choice = response.choices[0]
            content = choice.message.content or ""
        except (AttributeError, IndexError, KeyError, TypeError) as exc:
            logger.error(
                "Qwen vLLM 响应结构非法 model=%s: %s",
                self._model, type(exc).__name__,
            )
            raise RuntimeError(f"Qwen vLLM 响应结构非法: {exc}") from exc
        return strip_think_blocks(content)


def _normalize_json_response(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    else:
        text = _extract_first_json_object(text)
    return _strip_trailing_commas_outside_strings(text)


def _strip_trailing_commas_outside_strings(text: str) -> str:
    chars: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        if escape:
            chars.append(char)
            escape = False
            index += 1
            continue
        if char == "\\" and in_string:
            chars.append(char)
            escape = True
            index += 1
            continue
        if char == '"':
            chars.append(char)
            in_string = not in_string
            index += 1
            continue
        if char == "," and not in_string:
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        chars.append(char)
        index += 1
    return "".join(chars)


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]
