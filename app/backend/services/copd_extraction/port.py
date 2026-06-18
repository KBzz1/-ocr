import threading

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

    Defer model loading until the first request. ``llm_client_factory`` allows
    tests to inject a fake client; when absent, defaults to the offline
    llama-cpp client built from ``llm_model_path``.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 8192,
        max_tokens: int = 4096,
        llm_client_factory=None,
    ):
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._max_tokens = max_tokens
        self._llm_client_factory = llm_client_factory
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
            llm_client = self._llm_client_factory(
                self._model_path,
                n_ctx=self._n_ctx,
                max_tokens=self._max_tokens,
            )
        else:
            from .llm_client import build_llama_cpp_client

            llm_client = build_llama_cpp_client(
                self._model_path,
                n_ctx=self._n_ctx,
                max_tokens=self._max_tokens,
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

    Uses the fixed-field Qwen contract (Tasks 3-4).
    """
    factory = config.get("llm_client_factory")
    return _LazyCOPDAdmissionQwenFieldPort(
        config["llm_model_path"],
        n_ctx=config.get("llm_context_tokens", 8192),
        max_tokens=config.get("llm_max_tokens", 4096),
        llm_client_factory=factory,
    )
