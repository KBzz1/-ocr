from .field_result import all_fields_empty, complete_field_results
from .prompts import build_extraction_prompt, build_verification_prompt
from .quality_checks import apply_quality_checks
from .section_splitter import split_sections


class COPDFieldExtractor:
    def __init__(self, llm_client, field_keys: list[str]):
        self._llm_client = llm_client
        self._field_keys = field_keys

    def extract(self, text: str) -> list[dict]:
        sections = split_sections(text)
        extraction_payload = self._llm_client.complete_json(build_extraction_prompt(sections, self._field_keys))
        raw_results = extraction_payload.get("fields") if isinstance(extraction_payload, dict) else None
        if not isinstance(raw_results, list):
            raise ValueError("LLM extraction response must contain fields list")
        results = complete_field_results(raw_results, self._field_keys)
        if all_fields_empty(results):
            return results

        results = apply_quality_checks(results, text)
        verification_payload = self._llm_client.complete_json(build_verification_prompt(text, results))
        verdicts = verification_payload.get("verifications") if isinstance(verification_payload, dict) else None
        if not isinstance(verdicts, list):
            raise ValueError("LLM verification response must contain verifications list")
        return self._merge_verdicts(results, verdicts)

    def _merge_verdicts(self, results: list[dict], verdicts: list[dict]) -> list[dict]:
        verdict_by_key = {item.get("field_key"): item for item in verdicts if isinstance(item, dict)}
        for item in results:
            verdict = verdict_by_key.get(item["field_key"])
            if verdict:
                value = verdict.get("verdict")
                if value == "pass" and not item.get("quality_flags"):
                    item["verification_status"] = "passed"
                elif value == "fail":
                    item["verification_status"] = "failed"
                elif value == "suspicious":
                    item["verification_status"] = "suspicious"
        return results
