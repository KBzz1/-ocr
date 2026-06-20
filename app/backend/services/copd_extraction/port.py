import threading

from ..algorithm_ports.qwen_vllm_client import QwenVLLMClient
from .admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)
from .prompts import build_admission_structured_fields_prompt


class COPDAdmissionQwenFieldPort:
    """Active fixed-field Qwen port for admission-record documents.

    Wires the contract stack implemented by Tasks 3-4:

    1. ``build_admission_structured_fields_prompt`` — schema + evidence_units
       only, no per-field prompts.
    2. ``llm_client.complete_json`` — single LLM call returning the strict
       ``{schema_version, document_type, fields:[…]}`` payload.
    3. ``validate_qwen_payload`` — structural contract enforcement (raises
       ``ALGORITHM_CONTRACT_INVALID`` on bad payloads).
    4. ``map_qwen_fields_to_review_candidates`` — refill evidence arrays
       from backend-owned evidence_units, translate statuses and surface
       per-field attention flags.
    """

    def __init__(self, llm_client):
        self._llm_client = llm_client

    def extract(self, input: dict) -> list[dict]:
        schema = input.get("schema") or {}
        document_result = input.get("document_result") or {}
        evidence_units = (
            input.get("evidence_units")
            if input.get("evidence_units") is not None
            else document_result.get("evidence_units")
            or []
        )
        document_text = document_result.get("merged_text") or ""

        prompt = build_admission_structured_fields_prompt(
            schema=schema,
            evidence_units=evidence_units,
            document_text=document_text,
        )
        payload = self._llm_client.complete_json(prompt)
        # Structural validation raises AppError(ALGORITHM_CONTRACT_INVALID) on
        # any contract violation (missing fields, bad statuses, wrong types).
        validate_qwen_payload(payload, schema)
        return map_qwen_fields_to_review_candidates(
            payload,
            schema,
            evidence_units=evidence_units,
        )


class _LazyCOPDAdmissionQwenFieldPort:
    """Lazy wrapper around :class:`COPDAdmissionQwenFieldPort`.

    默认延迟构造 OpenAI-compatible Qwen vLLM 客户端，避免在 import 阶段
    锁定模型。``llm_client_factory`` 允许测试注入 fake 客户端；显式传入
    ``qwen_vllm_client`` 时可跳过内部默认构造（保持 `test_copd_field_port`
    现有 fixture 兼容）。
    """

    def __init__(
        self,
        qwen_vllm_server_url: str,
        qwen_vllm_model_name: str,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout_seconds: int = 360,
        llm_client_factory=None,
        qwen_vllm_client=None,
    ):
        self._qwen_vllm_server_url = qwen_vllm_server_url
        self._qwen_vllm_model_name = qwen_vllm_model_name
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._llm_client_factory = llm_client_factory
        self._qwen_vllm_client = qwen_vllm_client
        self._port = None
        self._llm_client = None
        self._lock = threading.Lock()

    def extract(self, input: dict) -> list[dict]:
        with self._lock:
            if self._port is None:
                self._build_port()
            return self._port.extract(input)

    def _build_port(self) -> None:
        if self._llm_client_factory is not None:
            qwen_client = self._llm_client_factory(
                base_url=self._qwen_vllm_server_url,
                model=self._qwen_vllm_model_name,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                timeout_seconds=self._timeout_seconds,
            )
        else:
            qwen_client = self._qwen_vllm_client or QwenVLLMClient(
                base_url=self._qwen_vllm_server_url,
                model=self._qwen_vllm_model_name,
                api_key="not-needed",
                timeout_seconds=float(self._timeout_seconds),
            )
        from .llm_client import OpenAICompatibleJsonClient

        llm_client = OpenAICompatibleJsonClient(
            qwen_client,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
        )
        self._llm_client = llm_client
        self._port = COPDAdmissionQwenFieldPort(llm_client)

    def close(self) -> None:
        with self._lock:
            close = getattr(self._llm_client, "close", None)
            if callable(close):
                close()
            self._llm_client = None
            self._port = None


def build_default_copd_field_port(config: dict, field_keys_provider):
    """Build the default field port for the active admission-record path.

    Uses the fixed-field Qwen contract and the shared ``qwen-vision-vllm-server``
    service; no local llama.cpp/GGUF model is loaded.
    """
    factory = config.get("llm_client_factory")
    return _LazyCOPDAdmissionQwenFieldPort(
        config["qwen_vllm_server_url"],
        config["qwen_vllm_model_name"],
        max_tokens=int(config.get("qwen_extraction_max_tokens", 8192)),
        temperature=float(config.get("qwen_extraction_temperature", 0.0)),
        timeout_seconds=int(config.get("qwen_extraction_timeout_seconds", 360)),
        llm_client_factory=factory,
    )
