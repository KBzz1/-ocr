from .field_result import _default_result, all_fields_empty, complete_field_results
from .prompts import build_extraction_prompt, build_section_group_extraction_prompt, build_verification_prompt
from .quality_checks import apply_quality_checks
from .section_splitter import split_sections


NOT_FOUND_VALUES = {"不详", "未知", "未提及", "未说明", "未记录", "无相关信息"}

STRATEGY_FIELD_BATCHES = "field_batches"
STRATEGY_SECTION_GROUPS = "section_groups"


SECTION_GROUPS = [
    (
        "history_profile",
        ["主诉", "现病史", "既往史", "个人史", "婚育史", "家族史", "全文"],
        [
            "occupation",
            "smoking_history_raw_text",
            "smoking_history_status",
            "copd_history_years",
            "baseline_lung_function",
            "maintenance_therapy",
            "cough_sputum_change",
            "dyspnea_grade_mMRC",
            "treatment_failure",
            "weight_loss",
            "gi_symptoms",
            "comorbidities",
        ],
    ),
    (
        "physical_exam",
        ["体格检查"],
        ["temperature", "pulse", "respiration", "blood_pressure", "bmi", "positive_signs"],
    ),
    (
        "auxiliary_exam",
        ["辅助检查"],
        [
            "blood_gas_ph",
            "blood_gas_pao2",
            "blood_gas_paco2",
            "electrolyte_imbalance",
            "wbc",
            "crp",
            "ct_features",
        ],
    ),
]


class COPDFieldExtractor:
    def __init__(
        self,
        llm_client,
        field_keys: list[str],
        extraction_batch_size: int = 5,
        verification_batch_size: int = 5,
        enable_verification: bool = True,
        extraction_strategy: str = "field_batches",
    ):
        self._llm_client = llm_client
        self._field_keys = field_keys
        self._extraction_batch_size = extraction_batch_size
        self._verification_batch_size = verification_batch_size
        self._enable_verification = enable_verification
        self._extraction_strategy = extraction_strategy

    def extract(self, text: str) -> list[dict]:
        sections = split_sections(text)
        if self._extraction_strategy == STRATEGY_SECTION_GROUPS:
            raw_results = self._extract_section_groups(sections)
        else:
            raw_results = self._extract_field_batches(sections)
        results = complete_field_results(raw_results, self._field_keys)
        if all_fields_empty(results):
            return results

        results = apply_quality_checks(results, text)
        if not self._enable_verification:
            return results
        verdicts = self._verify_field_batches(text, results)
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

    def _extract_section_groups(self, sections: dict[str, str]) -> list[dict]:
        raw_results = []
        allowed = set(self._field_keys)
        for group_name, section_names, group_field_keys in SECTION_GROUPS:
            field_keys = [key for key in group_field_keys if key in allowed]
            if not field_keys:
                continue
            text = self._collect_sections(sections, section_names)
            if not text.strip():
                continue
            payload = self._llm_client.complete_json(build_section_group_extraction_prompt(group_name, text, field_keys))
            fields = payload.get("fields") if isinstance(payload, dict) else None
            if not isinstance(fields, list):
                raise ValueError("LLM extraction response must contain fields list")
            raw_results.extend(self._normalize_section_group_fields(fields, group_name))
        return raw_results

    def _normalize_section_group_fields(self, fields: list[dict], group_name: str) -> list[dict]:
        normalized = []
        for item in fields:
            if not isinstance(item, dict):
                continue
            field_key = item.get("field_key")
            value = item.get("original_value")
            if not isinstance(field_key, str) or not isinstance(value, str) or not value.strip():
                continue
            if value.strip() in NOT_FOUND_VALUES:
                continue
            result = _default_result(field_key)
            result.update(item)
            result.setdefault("evidence", value.strip())
            result.setdefault("confidence", 0.7)
            result["source_section"] = group_name
            result["extraction_status"] = "extracted"
            normalized.append(result)
        return normalized

    def _collect_sections(self, sections: dict[str, str], section_names: list[str]) -> str:
        collected = []
        for section_name in section_names:
            section_text = sections.get(section_name)
            if section_text:
                collected.append(f"【{section_name}】\n{section_text}")
        return "\n\n".join(collected)

    def _extract_field_batches(self, sections: dict[str, str]) -> list[dict]:
        raw_results = []
        for field_keys in self._field_key_batches():
            extraction_payload = self._llm_client.complete_json(build_extraction_prompt(sections, field_keys))
            fields = extraction_payload.get("fields") if isinstance(extraction_payload, dict) else None
            if not isinstance(fields, list):
                raise ValueError("LLM extraction response must contain fields list")
            raw_results.extend(fields)
        return raw_results

    def _field_key_batches(self) -> list[list[str]]:
        batch_size = max(1, self._extraction_batch_size)
        return [
            self._field_keys[index:index + batch_size]
            for index in range(0, len(self._field_keys), batch_size)
        ]

    def _verify_field_batches(self, text: str, results: list[dict]) -> list[dict]:
        verdicts = []
        batch_size = max(1, self._verification_batch_size)
        for index in range(0, len(results), batch_size):
            batch = results[index:index + batch_size]
            verification_payload = self._llm_client.complete_json(build_verification_prompt(text, batch))
            batch_verdicts = verification_payload.get("verifications") if isinstance(verification_payload, dict) else None
            if not isinstance(batch_verdicts, list):
                raise ValueError("LLM verification response must contain verifications list")
            verdicts.extend(batch_verdicts)
        return verdicts
