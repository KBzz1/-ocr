from .field_result import _default_result, all_fields_empty, complete_field_results
from .prompts import (
    build_extraction_prompt,
    build_section_group_extraction_prompt,
    build_source_hint_regeneration_prompt,
    build_verification_prompt,
)
from .quality_checks import apply_quality_checks
from .section_splitter import FULL_TEXT_KEY, split_sections


NOT_FOUND_VALUES = {"不详", "未知", "未提及", "未说明", "未记录", "无相关信息", "未找到证据"}
SOURCE_HINT_NOT_FOUND = "未找到证据"
MAX_VERIFICATION_DOCUMENT_CONTEXT_CHARS = 1600

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
        results = attach_source_text(results, sections)
        if all_fields_empty(results):
            return results

        results = apply_quality_checks(results, text)
        if not self._enable_verification:
            return results
        verdicts = self._verify_source_groups(results, text)
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
                    _append_quality_flag(item, "llm_review_failed", verdict)
                elif value == "suspicious":
                    item["verification_status"] = "suspicious"
                    _append_quality_flag(item, "llm_review_suspicious", verdict)
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
            try:
                payload = self._llm_client.complete_json(build_section_group_extraction_prompt(group_name, text, field_keys))
                fields = payload.get("fields") if isinstance(payload, dict) else None
                if not isinstance(fields, list):
                    raise ValueError("LLM extraction response must contain fields list")
                allowed_source_hints = [name for name in section_names if sections.get(name)]
                fields = self._regenerate_section_group_fields_if_needed(
                    text,
                    field_keys,
                    allowed_source_hints,
                    fields,
                )
            except Exception as exc:
                raw_results.extend(_group_failed_results(field_keys, group_name, exc))
                continue
            raw_results.extend(self._normalize_section_group_fields(fields, group_name))
        return raw_results

    def _regenerate_section_group_fields_if_needed(
        self,
        text: str,
        field_keys: list[str],
        allowed_source_hints: list[str],
        fields: list[dict],
    ) -> list[dict]:
        context = FieldRegenerationContext(
            text=text,
            field_keys=field_keys,
            allowed_source_hints=allowed_source_hints,
        )
        for strategy in FIELD_REGENERATION_STRATEGIES:
            if not strategy.should_regenerate(fields, context):
                continue
            payload = self._llm_client.complete_json(strategy.build_prompt(fields, context))
            regenerated = payload.get("fields") if isinstance(payload, dict) else None
            if not isinstance(regenerated, list):
                raise ValueError(f"LLM {strategy.name} response must contain fields list")
            fields = regenerated
        return fields

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
            if result.get("evidence_phrase") and not result.get("evidence"):
                result["evidence"] = result["evidence_phrase"]
            if "confidence" not in item or item.get("confidence") is None:
                result["confidence"] = 0.7
            result["source_section"] = result.get("source_hint")
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

    def _verify_source_groups(self, results: list[dict], document_text: str = "") -> list[dict]:
        verdicts = []
        source_groups = build_source_groups(results)
        if not source_groups:
            return verdicts
        document_context = _bounded_document_context(document_text)
        batch_size = max(1, self._verification_batch_size)
        for index in range(0, len(source_groups), batch_size):
            batch = source_groups[index:index + batch_size]
            verification_payload = self._llm_client.complete_json(
                build_verification_prompt(batch, document_context=document_context)
            )
            batch_verdicts = verification_payload.get("verifications") if isinstance(verification_payload, dict) else None
            if not isinstance(batch_verdicts, list):
                raise ValueError("LLM verification response must contain verifications list")
            verdicts.extend(batch_verdicts)
        return verdicts


SOURCE_SECTION_NOT_FOUND = "source_section_not_found"
EVIDENCE_MISSING_FALLBACK = "evidence_missing_fallback"
EVIDENCE_NOT_IN_SOURCE_TEXT = "evidence_not_in_source_text"
EVIDENCE_TOO_LONG = "evidence_too_long"
MAX_EVIDENCE_PHRASE_CHARS = 50


class FieldRegenerationContext:
    def __init__(self, text: str, field_keys: list[str], allowed_source_hints: list[str]):
        self.text = text
        self.field_keys = field_keys
        self.allowed_source_hints = allowed_source_hints


class SourceHintRegenerationStrategy:
    name = "source_hint_regeneration"

    def should_regenerate(self, fields: list[dict], context: FieldRegenerationContext) -> bool:
        return _has_invalid_source_hint(fields, set(context.allowed_source_hints))

    def build_prompt(self, fields: list[dict], context: FieldRegenerationContext) -> str:
        return build_source_hint_regeneration_prompt(
            context.text,
            context.field_keys,
            context.allowed_source_hints,
            fields,
        )


FIELD_REGENERATION_STRATEGIES = [SourceHintRegenerationStrategy()]


def attach_source_text(results: list[dict], sections: dict[str, str]) -> list[dict]:
    for item in results:
        if item.get("extraction_status") != "extracted":
            continue
        source_hint = item.get("source_hint") or item.get("source_section")
        if not source_hint:
            continue
        source_text = sections.get(source_hint)
        if source_text:
            item["source_hint"] = source_hint
            item["source_section"] = source_hint
            item["source_text"] = source_text
            item["source_group_id"] = _source_group_id(source_hint)
            if not item.get("evidence"):
                item["evidence"] = source_text
                _append_quality_flag(
                    item,
                    EVIDENCE_MISSING_FALLBACK,
                    {"comment": "缺少短 evidence，已回退章节原文"},
                )
                item["verification_status"] = "suspicious"
            else:
                _validate_evidence_against_source_text(item, source_text)
            continue
        if source_hint == FULL_TEXT_KEY and sections.get(FULL_TEXT_KEY):
            item["source_text"] = sections[FULL_TEXT_KEY]
            item["source_group_id"] = _source_group_id(source_hint)
            if not item.get("evidence"):
                item["evidence"] = sections[FULL_TEXT_KEY]
                _append_quality_flag(
                    item,
                    EVIDENCE_MISSING_FALLBACK,
                    {"comment": "缺少短 evidence，已回退全文"},
                )
                item["verification_status"] = "suspicious"
            else:
                _validate_evidence_against_source_text(item, sections[FULL_TEXT_KEY])
            continue
        if source_hint == SOURCE_HINT_NOT_FOUND:
            item["source_section"] = None
            item["evidence"] = None
            item["source_text"] = None
            item["source_group_id"] = None
            item["verification_status"] = "suspicious"
            _append_quality_flag(
                item,
                SOURCE_SECTION_NOT_FOUND,
                {"comment": "模型明确返回未找到证据"},
            )
            continue
        item["evidence"] = None
        item["source_text"] = None
        item["source_group_id"] = None
        item["verification_status"] = "suspicious"
        _append_quality_flag(
            item,
            SOURCE_SECTION_NOT_FOUND,
            {"comment": f"source_hint={source_hint} 未在 OCR 章节中定位"},
        )
    return results


def build_source_groups(results: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for item in results:
        if item.get("extraction_status") != "extracted":
            continue
        source_hint = item.get("source_hint")
        source_text = item.get("source_text") or item.get("evidence")
        if not source_hint or not source_text:
            continue
        key = item.get("source_group_id") or _source_group_id(source_hint)
        group = groups.setdefault(
            key,
            {"source_hint": source_hint, "source_text": source_text, "fields": []},
        )
        group["fields"].append(
            {"field_key": item["field_key"], "original_value": item.get("original_value", "")}
        )
    return list(groups.values())


def _validate_evidence_against_source_text(item: dict, source_text: str) -> None:
    evidence = item.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return
    if len(evidence) > MAX_EVIDENCE_PHRASE_CHARS:
        _append_quality_flag(
            item,
            EVIDENCE_TOO_LONG,
            {"comment": "evidence 超过50字"},
        )
    if evidence.strip() not in source_text:
        _append_quality_flag(
            item,
            EVIDENCE_NOT_IN_SOURCE_TEXT,
            {"comment": "evidence 未在来源章节中定位"},
        )
    if item.get("quality_flags") and item.get("verification_status") != "failed":
        item["verification_status"] = "suspicious"


def _source_group_id(source_hint: str) -> str:
    return f"source_group_{source_hint}"


def _bounded_document_context(text: str, max_chars: int = MAX_VERIFICATION_DOCUMENT_CONTEXT_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    head_chars = max_chars * 3 // 4
    tail_chars = max_chars - head_chars
    return f"{text[:head_chars]}\n...[已截断]...\n{text[-tail_chars:]}"


def _has_invalid_source_hint(fields: list[dict], allowed_source_hints: set[str]) -> bool:
    for item in fields:
        if not isinstance(item, dict):
            continue
        value = item.get("original_value")
        if not isinstance(value, str) or not value.strip() or value.strip() in NOT_FOUND_VALUES:
            continue
        source_hint = item.get("source_hint")
        if source_hint not in allowed_source_hints and source_hint != SOURCE_HINT_NOT_FOUND:
            return True
    return False


def _append_quality_flag(item: dict, flag: str, verdict: dict) -> None:
    flags = item.setdefault("quality_flags", [])
    if any(existing.get("flag") == flag for existing in flags if isinstance(existing, dict)):
        return
    message = verdict.get("comment") or verdict.get("reason") or flag
    flags.append({"flag": flag, "severity": "warning", "message": message})


def _group_failed_results(field_keys: list[str], group_name: str, exc: Exception) -> list[dict]:
    results = []
    message = f"{group_name} 抽取失败: {type(exc).__name__}"
    for field_key in field_keys:
        item = _default_result(field_key)
        item["verification_status"] = "suspicious"
        item["quality_flags"] = [
            {"flag": "llm_group_failed", "severity": "warning", "message": message}
        ]
        results.append(item)
    return results
