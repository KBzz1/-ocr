import json
import ctypes
import gc
import logging
import re
import site
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class LlmClient(ABC):
    @abstractmethod
    def complete_json(self, prompt: str) -> dict:
        ...

    def close(self) -> None:
        return None


def _parse_json_response(content: str) -> dict:
    normalized = _normalize_json_response(content)
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        tail = normalized[-300:] if len(normalized) > 300 else normalized
        logger.error("LLM JSON parse failed: %s | normalized_tail=%s", exc, tail)
        raise ValueError(f"LLM 返回非 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        logger.error("LLM JSON top-level not dict, got %s", type(parsed).__name__)
        raise ValueError("LLM 返回 JSON 顶层必须是对象")
    return parsed


def _normalize_json_response(content: str) -> str:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    else:
        text = _extract_first_json_object(text)
    return re.sub(r",(\s*[}\]])", r"\1", text)


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


class LlamaCppClient(LlmClient):
    def __init__(self, llama, max_tokens: int = 1024):
        self._llama = llama
        self._max_tokens = max_tokens

    def complete_json(self, prompt: str):
        if self._llama is None:
            raise RuntimeError("LLM client is closed")
        response = self._llama.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
        )
        content = response["choices"][0]["message"]["content"]
        if content:
            tail = content[-200:] if len(content) > 200 else content
            logger.debug("LLM raw response len=%d tail=%s", len(content), tail)
        else:
            logger.warning("LLM returned empty content")
        return _parse_json_response(content)

    def close(self) -> None:
        llama = self._llama
        self._llama = None
        if llama is not None and hasattr(llama, "close"):
            llama.close()
        del llama
        gc.collect()


def _preload_llama_runtime_libraries() -> None:
    """Load optional wheel-provided CUDA/OpenMP libraries before importing llama_cpp."""
    library_names = (
        "llama_cpp_python.libs/libgomp-a34b3233.so.1.0.0",
        "nvidia/cuda_runtime/lib/libcudart.so.12",
        "nvidia/cublas/lib/libcublas.so.12",
        "nvidia/cublas/lib/libcublasLt.so.12",
    )
    search_roots = [Path(path) for path in site.getsitepackages()]
    mode = getattr(ctypes, "RTLD_GLOBAL", ctypes.DEFAULT_MODE)
    for root in search_roots:
        for name in library_names:
            path = root / name
            if path.exists():
                ctypes.CDLL(str(path), mode=mode)


def build_llama_cpp_client(
    model_path: str,
    n_ctx: int = 8192,
    n_gpu_layers: int = -1,
    max_tokens: int = 1024,
):
    _preload_llama_runtime_libraries()
    from llama_cpp import Llama

    return LlamaCppClient(
        Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False),
        max_tokens=max_tokens,
    )
