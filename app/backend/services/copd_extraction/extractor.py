import re

from ...errors import AppError, ErrorCode
from .field_result import _default_result, all_fields_empty, complete_field_results
from .prompts import (
    build_extraction_prompt,
    build_section_group_extraction_prompt,
    build_source_hint_regeneration_prompt,
    build_verification_prompt,
    build_adversarial_verification_prompt,
)
from .quality_checks import apply_quality_checks
from .section_splitter import FULL_TEXT_KEY, split_sections


NOT_FOUND_VALUES = {"不详", "未知", "未提及", "未说明", "未记录", "无相关信息", "未找到证据"}
SOURCE_HINT_NOT_FOUND = "未找到证据"
MAX_VERIFICATION_DOCUMENT_CONTEXT_CHARS = 1600

STRATEGY_FIELD_BATCHES = "field_batches"
STRATEGY_SECTION_GROUPS = "section_groups"


def _raise_if_cancelled(token) -> None:
    """批次之间检查取消 token;若 set 则抛 REEXTRACTION_CANCELLED。

    Token 是任意带 ``is_set()`` 的对象(实际是 threading.Event)。单次 in-flight
    LLM 调用本身不可中断,这里只能让链路在下一个批次边界停下。
    """
    if token is None:
        return
    if getattr(token, "is_set", lambda: False)():
        raise AppError(
            ErrorCode.REEXTRACTION_CANCELLED,
            message="用户取消重新抽取",
            details={"reason": "user_cancelled"},
        )


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
        enable_adversarial_verification: bool = True,
        extraction_strategy: str = "field_batches",
    ):
        self._llm_client = llm_client
        self._field_keys = field_keys
        self._extraction_batch_size = extraction_batch_size
        self._verification_batch_size = verification_batch_size
        self._enable_verification = enable_verification
        self._enable_adversarial_verification = enable_adversarial_verification
        self._extraction_strategy = extraction_strategy

    def extract(self, text: str, cancellation_token=None) -> list[dict]:
        sections = split_sections(text)
        _raise_if_cancelled(cancellation_token)
        if self._extraction_strategy == STRATEGY_SECTION_GROUPS:
            raw_results = self._extract_section_groups(sections, cancellation_token=cancellation_token)
        else:
            raw_results = self._extract_field_batches(sections, cancellation_token=cancellation_token)
        results = complete_field_results(raw_results, self._field_keys)
        results = attach_source_text(results, sections)
        if all_fields_empty(results):
            return results

        results = apply_quality_checks(results, text)
        if not self._enable_verification:
            return results
        _raise_if_cancelled(cancellation_token)
        verdicts = self._verify_source_groups(results, text, cancellation_token=cancellation_token)
        results = self._merge_verdicts(results, verdicts)
        if self._enable_adversarial_verification:
            _raise_if_cancelled(cancellation_token)
            results = self._adversarial_verify(results, text, cancellation_token=cancellation_token)
        return results

    def _merge_verdicts(self, results: list[dict], verdicts: list[dict]) -> list[dict]:
        verdict_by_key = {item.get("field_key"): item for item in verdicts if isinstance(item, dict)}
        for item in results:
            verdict = verdict_by_key.get(item["field_key"])
            if verdict:
                value = verdict.get("verdict")
                if value == "pass":
                    if not item.get("quality_flags"):
                        item["verification_status"] = "passed"
                    else:
                        # LLM 认为通过，但薄规则仍有标记 → 保留为 passed
                        # 但追加区分性 flag 供前端重点展示
                        item["verification_status"] = "passed"
                        _append_quality_flag(
                            item,
                            LLM_PASSED_RULE_FLAGGED,
                            {"comment": "LLM 复核通过，但薄规则仍存在标记，请人工确认"},
                        )
                elif value == "fail":
                    item["verification_status"] = "failed"
                    _append_quality_flag(item, "llm_review_failed", verdict)
                elif value == "suspicious":
                    item["verification_status"] = "suspicious"
                    _append_quality_flag(item, "llm_review_suspicious", verdict)
        return results

    def _extract_section_groups(self, sections: dict[str, str], cancellation_token=None) -> list[dict]:
        raw_results = []
        allowed = set(self._field_keys)
        for group_name, section_names, group_field_keys in SECTION_GROUPS:
            _raise_if_cancelled(cancellation_token)
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
            fields = _merge_regenerated_fields(fields, regenerated)
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

    def _extract_field_batches(self, sections: dict[str, str], cancellation_token=None) -> list[dict]:
        raw_results = []
        for field_keys in self._field_key_batches():
            _raise_if_cancelled(cancellation_token)
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

    def _verify_source_groups(self, results: list[dict], document_text: str = "", cancellation_token=None) -> list[dict]:
        verdicts = []
        source_groups = build_source_groups(results)
        if not source_groups:
            return verdicts
        document_context = _bounded_document_context(document_text)
        batch_size = max(1, self._verification_batch_size)
        for index in range(0, len(source_groups), batch_size):
            _raise_if_cancelled(cancellation_token)
            batch = source_groups[index:index + batch_size]
            try:
                verification_payload = self._llm_client.complete_json(
                    build_verification_prompt(batch, document_context=document_context)
                )
                batch_verdicts = verification_payload.get("verifications") if isinstance(verification_payload, dict) else None
                if not isinstance(batch_verdicts, list):
                    raise ValueError("LLM verification response must contain verifications list")
                verdicts.extend(batch_verdicts)
            except Exception as exc:
                # 复核失败时优雅降级：将该批次所有字段标记为 suspicious，
                # 而非让整个任务进入 failed
                for group in batch:
                    for field in group.get("fields", []):
                        verdicts.append({
                            "field_key": field.get("field_key"),
                            "verdict": "suspicious",
                            "reason_code": "none",
                            "checks": {},
                            "comment": f"LLM 复核失败: {type(exc).__name__}",
                        })
        return verdicts

    def _adversarial_verify(self, results: list[dict], document_text: str = "", cancellation_token=None) -> list[dict]:
        """对抗性复核：要求 LLM 主动挑刺，直接输出问题列表。

        与常规复核不同，对抗性复核以批评者视角审视抽取结果，
        输出直接转为 quality_flags，不经规则层过滤。
        """
        source_groups = build_source_groups(results)
        if not source_groups:
            return results
        document_context = _bounded_document_context(document_text)
        # 对抗性复核一次处理所有 source_groups，让 LLM 有全局视角
        try:
            payload = self._llm_client.complete_json(
                build_adversarial_verification_prompt(
                    source_groups, document_context=document_context
                )
            )
            issues = payload.get("issues") if isinstance(payload, dict) else None
        except Exception:
            # 对抗性复核失败不阻塞主流程
            return results
        if not isinstance(issues, list):
            return results

        # 将 issues 转换为 quality_flags
        field_map = {item["field_key"]: item for item in results}
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            field_key = issue.get("field_key")
            item = field_map.get(field_key)
            if item is None:
                continue
            problem_type = issue.get("problem_type") or "adversarial_issue"
            description = issue.get("description") or "对抗性复核发现问题"
            severity = issue.get("severity") or "medium"

            flag_name = f"adversarial_{problem_type}"
            _append_quality_flag(item, flag_name, {"comment": description})

            # 高严重度问题：若当前状态为 passed，升级为 suspicious
            if severity == "high" and item.get("verification_status") == "passed":
                item["verification_status"] = "suspicious"

        return results


SOURCE_SECTION_NOT_FOUND = "source_section_not_found"
EVIDENCE_MISSING_FALLBACK = "evidence_missing_fallback"
EVIDENCE_NOT_IN_SOURCE_TEXT = "evidence_not_in_source_text"
EVIDENCE_TOO_LONG = "evidence_too_long"
EVIDENCE_RECOVERED_FROM_VALUE = "evidence_recovered_from_value"
LLM_VERIFICATION_FAILED = "llm_verification_failed"
LLM_PASSED_RULE_FLAGGED = "llm_passed_rule_flagged"
MAX_EVIDENCE_PHRASE_CHARS = 50

# —— 文本规范化：全角标点 → 半角，用于 evidence 模糊匹配 ——
_FULLWIDTH_TO_HALFWIDTH = str.maketrans({
    "，": ",", "。": ".", "！": "!", "？": "?",
    "：": ":", "；": ";", "“": '"', "”": '"',
    "（": "(", "）": ")", "【": "[", "】": "]",
    "　": " ", "～": "~",
})


def _normalize_for_matching(text: str) -> str:
    """规范化文本用于模糊匹配：全角→半角标点、去除所有空白。"""
    if not text:
        return text
    result = text.translate(_FULLWIDTH_TO_HALFWIDTH)
    result = re.sub(r"\s+", "", result)
    return result


def _find_normalized_match_start(needle: str, haystack: str) -> int:
    """返回规范化匹配在原始 haystack 中的起始下标。"""
    normalized_needle = _normalize_for_matching(needle)
    if not normalized_needle:
        return -1
    normalized_chars: list[str] = []
    original_indexes: list[int] = []
    for index, char in enumerate(haystack):
        translated = char.translate(_FULLWIDTH_TO_HALFWIDTH)
        if not translated or re.match(r"\s+", translated):
            continue
        normalized_chars.append(translated)
        original_indexes.append(index)
    normalized_haystack = "".join(normalized_chars)
    normalized_index = normalized_haystack.find(normalized_needle)
    if normalized_index < 0 or normalized_index >= len(original_indexes):
        return -1
    return original_indexes[normalized_index]


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
        if source_hint == SOURCE_HINT_NOT_FOUND or source_hint == FULL_TEXT_KEY:
            item["source_section"] = None
            item["evidence"] = None
            item["source_text"] = None
            item["source_group_id"] = None
            item["verification_status"] = "suspicious"
            _append_quality_flag(
                item,
                SOURCE_SECTION_NOT_FOUND,
                {"comment": f"source_hint={source_hint} 不作为章节定位依据"},
            )
            continue
        source_text = sections.get(source_hint)
        if not source_text:
            item["evidence"] = None
            item["source_text"] = None
            item["source_group_id"] = None
            item["verification_status"] = "suspicious"
            _append_quality_flag(
                item,
                SOURCE_SECTION_NOT_FOUND,
                {"comment": f"source_hint={source_hint} 未在 OCR 章节中定位"},
            )
            continue
        item["source_hint"] = source_hint
        item["source_section"] = source_hint
        item["source_text"] = source_text
        item["source_group_id"] = _source_group_id(source_hint)
        _resolve_field_evidence(item, source_text)
    return results


def _resolve_field_evidence(item: dict, source_text: str) -> None:
    raw_evidence = item.get("evidence")
    has_raw_evidence = isinstance(raw_evidence, str) and raw_evidence.strip()

    # —— 始终保留原始 evidence 作为审核参考 ——
    if has_raw_evidence:
        item["_raw_evidence"] = raw_evidence

    raw_evidence_too_long = has_raw_evidence and len(raw_evidence) > MAX_EVIDENCE_PHRASE_CHARS

    # —— 检查 evidence 是否在原文中出现 ——
    # 短 evidence：规范化后做子串匹配，容忍全角/半角标点和空白差异
    # 长 evidence：用原始文本匹配（仅用于标记，不用于恢复）
    raw_evidence_not_in_source = False
    if has_raw_evidence:
        if raw_evidence_too_long:
            raw_evidence_not_in_source = raw_evidence not in source_text
        else:
            norm_evidence = _normalize_for_matching(raw_evidence)
            norm_source = _normalize_for_matching(source_text)
            raw_evidence_not_in_source = norm_evidence not in norm_source

    if has_raw_evidence and not raw_evidence_too_long and not raw_evidence_not_in_source:
        item["evidence"] = raw_evidence
        return

    if raw_evidence_too_long:
        _append_quality_flag(item, EVIDENCE_TOO_LONG, {"comment": "evidence 超过50字，已丢弃"})
    if raw_evidence_not_in_source:
        _append_quality_flag(
            item,
            EVIDENCE_NOT_IN_SOURCE_TEXT,
            {"comment": "evidence 未在来源章节中定位，已丢弃"},
        )

    recovered = _recover_evidence_from_value(
        item.get("original_value", ""),
        source_text,
        max_chars=MAX_EVIDENCE_PHRASE_CHARS,
    )
    if recovered is not None:
        item["evidence"] = recovered
        _append_quality_flag(
            item,
            EVIDENCE_RECOVERED_FROM_VALUE,
            {"comment": "evidence 缺失或非法，已用 original_value 在章节中定位恢复"},
        )
        if item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
        return

    item["evidence"] = None
    if not raw_evidence_too_long and not raw_evidence_not_in_source:
        _append_quality_flag(
            item,
            EVIDENCE_MISSING_FALLBACK,
            {"comment": "缺少短 evidence 且无法用 original_value 恢复"},
        )
    if item.get("verification_status") != "failed":
        item["verification_status"] = "suspicious"


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


def _recover_evidence_from_value(
    original_value: str,
    source_text: str,
    max_chars: int = MAX_EVIDENCE_PHRASE_CHARS,
) -> str | None:
    if not isinstance(original_value, str) or not original_value.strip():
        return None
    if not isinstance(source_text, str):
        return None
    value = original_value.strip()
    if len(value) > max_chars:
        return None

    # 1) 精确匹配
    index = source_text.find(value)

    # 2) 规范化后匹配（全角/半角标点、空白差异）
    if index < 0:
        index = _find_normalized_match_start(value, source_text)

    if index < 0:
        return None
    if value == source_text:
        # Pathological: value is the entire section, no useful sub-window
        return None
    if len(source_text) <= max_chars:
        # Section is short enough that any window covers the whole section;
        # return the value itself to keep evidence != source_text.
        return value
    window_radius = max(0, (max_chars - len(value)) // 2)
    start = max(0, index - window_radius)
    end = min(len(source_text), start + max_chars)
    start = max(0, end - max_chars)
    return source_text[start:end]


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


def _merge_regenerated_fields(previous: list[dict], regenerated: list[dict]) -> list[dict]:
    previous_by_key = {
        item.get("field_key"): item
        for item in previous
        if isinstance(item, dict) and isinstance(item.get("field_key"), str)
    }
    merged = []
    for item in regenerated:
        if not isinstance(item, dict):
            continue
        field_key = item.get("field_key")
        base = previous_by_key.get(field_key)
        if isinstance(base, dict):
            combined = dict(base)
            combined.update(item)
            merged.append(combined)
        else:
            merged.append(item)
    return merged


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
