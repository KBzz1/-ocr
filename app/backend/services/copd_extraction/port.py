from .extractor import COPDFieldExtractor, STRATEGY_SECTION_GROUPS


class COPDFieldPort:
    def __init__(self, extractor):
        self._extractor = extractor

    def extract(self, input: dict) -> list[dict]:
        document_result = input.get("document_result") or {}
        text = document_result.get("merged_text") or ""
        return self._extractor.extract(text)


class _LazyCOPDFieldPort:
    """Defer LLM model loading until first extraction request."""

    def __init__(
        self,
        model_path: str,
        field_keys: list[str],
        n_ctx: int = 8192,
        max_tokens: int = 4096,
        extraction_batch_size: int = 25,
        enable_verification: bool = False,
        extraction_strategy: str = STRATEGY_SECTION_GROUPS,
    ):
        self._model_path = model_path
        self._field_keys = field_keys
        self._n_ctx = n_ctx
        self._max_tokens = max_tokens
        self._extraction_batch_size = extraction_batch_size
        self._enable_verification = enable_verification
        self._extraction_strategy = extraction_strategy
        self._port = None
        self._llm_client = None

    def extract(self, input: dict) -> list[dict]:
        if self._port is None:
            self._build_port()
        return self._port.extract(input)

    def _build_port(self) -> None:
        from .llm_client import build_llama_cpp_client

        llm_client = build_llama_cpp_client(
            self._model_path,
            n_ctx=self._n_ctx,
            max_tokens=self._max_tokens,
        )
        extractor = COPDFieldExtractor(
            llm_client=llm_client,
            field_keys=self._field_keys,
            extraction_batch_size=self._extraction_batch_size,
            verification_batch_size=self._extraction_batch_size,
            enable_verification=self._enable_verification,
            extraction_strategy=self._extraction_strategy,
        )
        self._llm_client = llm_client
        self._port = COPDFieldPort(extractor)

    def close(self) -> None:
        close = getattr(self._llm_client, "close", None)
        if callable(close):
            close()
        self._llm_client = None
        self._port = None


def build_default_copd_field_port(config: dict, field_keys_provider):
    field_keys = field_keys_provider()
    return _LazyCOPDFieldPort(
        config["llm_model_path"],
        field_keys,
        n_ctx=config.get("llm_context_tokens", 8192),
        max_tokens=config.get("llm_max_tokens", 4096),
        extraction_batch_size=config.get("llm_extraction_batch_size", 25),
        enable_verification=config.get("llm_enable_verification", False),
    )
