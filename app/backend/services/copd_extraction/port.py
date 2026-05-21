from .extractor import COPDFieldExtractor


class COPDFieldPort:
    def __init__(self, extractor):
        self._extractor = extractor

    def extract(self, input: dict) -> list[dict]:
        document_result = input.get("document_result") or {}
        text = document_result.get("merged_text") or ""
        return self._extractor.extract(text)


class _LazyCOPDFieldPort:
    """Defer LLM model loading until first extraction request."""

    def __init__(self, model_path: str, field_keys: list[str]):
        self._model_path = model_path
        self._field_keys = field_keys
        self._port = None

    def extract(self, input: dict) -> list[dict]:
        if self._port is None:
            from .llm_client import build_llama_cpp_client

            llm_client = build_llama_cpp_client(self._model_path)
            extractor = COPDFieldExtractor(llm_client=llm_client, field_keys=self._field_keys)
            self._port = COPDFieldPort(extractor)
        return self._port.extract(input)


def build_default_copd_field_port(config: dict, field_keys_provider):
    field_keys = field_keys_provider()
    return _LazyCOPDFieldPort(config["llm_model_path"], field_keys)
