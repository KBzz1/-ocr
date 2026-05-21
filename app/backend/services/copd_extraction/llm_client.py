import json
import ctypes
import site
from abc import ABC, abstractmethod
from pathlib import Path


class LlmClient(ABC):
    @abstractmethod
    def complete_json(self, prompt: str) -> dict:
        ...


def _parse_json_response(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 返回非 JSON: {exc}") from exc


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
        return _parse_json_response(content)


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


def build_llama_cpp_client(model_path: str, n_ctx: int = 4096, n_gpu_layers: int = -1):
    _preload_llama_runtime_libraries()
    from llama_cpp import Llama

    return LlamaCppClient(Llama(model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=False))
