from .extractor import COPDFieldExtractor


class COPDFieldPort:
    def __init__(self, extractor):
        self._extractor = extractor

    def extract(self, input: dict) -> list[dict]:
        document_result = input.get("document_result") or {}
        text = document_result.get("merged_text") or ""
        return self._extractor.extract(text)


def _schema_field_keys(schema: dict) -> list[str]:
    return [
        field["field_key"]
        for group in schema.get("field_groups", [])
        for field in group.get("fields", [])
    ]


def build_default_copd_field_port(config: dict, schema_provider):
    from .llm_client import build_llama_cpp_client

    schema = schema_provider()
    llm_client = build_llama_cpp_client(config["llm_model_path"])
    extractor = COPDFieldExtractor(llm_client=llm_client, field_keys=_schema_field_keys(schema))
    return COPDFieldPort(extractor)
