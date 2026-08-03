"""Field-level LLM verification with deterministic evidence preflight."""
from __future__ import annotations

import json
import logging
import re

from .evidence_context import assemble_verification_groups
from .response_schemas import build_verification_json_schema

logger = logging.getLogger(__name__)

_ALLOWED_VERDICTS = {"pass", "suspicious", "fail"}
_ALLOWED_REASONS = {
    "none", "extraction_mistake", "nonstandard_expression",
    "evidence_insufficient", "ocr_quality_issue",  # ocr_quality_issue 仅历史解析兼容
}
_CHECK_KEYS = (
    "grounding_supported", "field_scope_valid", "text_standard", "logic_consistent",
)
# 后端语义契约（verifier.v2）：约束解码后的确定性验证，条件矛盾的单组响应
# 按失败语义整组跳过并记录本地日志，不静默修补成看似合理的 verdict。


class FieldVerifier:
    def __init__(self, llm_client, append_reminder: bool = False):
        self._llm_client = llm_client
        self._append_reminder = append_reminder

    def verify(
        self,
        candidates: list[dict],
        document_text: str = "",
        group_by: str | None = None,
        evidence_units: list[dict] | None = None,
    ) -> list[dict]:
        """Verify found, non-empty fields and silently degrade on LLM errors.

        When ``evidence_units`` is supplied, it is the authoritative registry.
        A group with a missing/empty cited ID is skipped before any LLM call;
        this preserves the candidate's existing evidence-missing marker.
        ``None`` retains the old candidate-evidence fallback for compatibility.
        """
        targets = [
            c for c in candidates
            if isinstance(c, dict)
            and c.get("status") == "found"
            and (c.get("value") or "").strip()
        ]
        if not targets:
            return []
        try:
            from .prompts import build_verification_messages

            if evidence_units is None:
                if group_by is None:
                    groups = [{
                        "fields": targets,
                        "units": _collect_evidence(targets, document_text),
                        "missing_ids": [],
                    }]
                else:
                    groups = [dict(group, missing_ids=[]) for group in _split_groups(targets, group_by)]
            else:
                groups = assemble_verification_groups(
                    targets, evidence_units, group_by=group_by, neighbor_radius=1
                )

            verdicts: list[dict] = []
            for group in groups:
                group_fields = group.get("fields") or []
                group_keys = {f.get("field_key") for f in group_fields}
                missing_ids = group.get("missing_ids") or []
                if missing_ids:
                    logger.warning(
                        "复核器跳过证据不完整分组 group=%s missing_ids=%s",
                        group.get("group_key"), missing_ids,
                    )
                    continue
                try:
                    fields = _to_field_dicts(group_fields)
                    system, user = build_verification_messages(
                        group.get("units") or [], fields,
                        append_reminder=self._append_reminder,
                    )
                    payload = _complete_json(
                        self._llm_client,
                        user,
                        system,
                        build_verification_json_schema(fields),
                    )
                    verdicts.extend(
                        _parse_verdicts(
                            payload,
                            expected_keys=group_keys,
                            evidence_ids={u.get("id") for u in (group.get("units") or [])},
                        )
                    )
                except Exception:  # noqa: BLE001 — 单组失败不影响其他组
                    logger.warning(
                        "复核器分组调用失败，跳过该组（%s）", group_keys, exc_info=True
                    )
            return verdicts
        except Exception:  # noqa: BLE001 — 复核器失败必须静默降级
            logger.warning("复核器调用失败，已降级为空意见", exc_info=True)
            return []


def _collect_evidence(candidates: list[dict], document_text: str) -> list[dict]:
    """Legacy fallback: preserve candidate IDs and never renumber evidence."""
    seen: set[str] = set()
    units: list[dict] = []
    for candidate in candidates:
        for evidence in candidate.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            key = evidence.get("id") or evidence.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                units.append({
                    "id": evidence.get("id") or "",
                    "text": evidence.get("text", ""),
                    "page_no": evidence.get("page_no"),
                    "section_hint": evidence.get("section_hint") or evidence.get("section_key") or "",
                })
    if not units and document_text:
        units.append({"id": "doc", "text": document_text[:8000], "page_no": 1})
    return units


def _to_field_dicts(targets: list[dict]) -> list[dict]:
    """Build the internal verifier field view (not a persisted contract)."""
    from .prompts import verifier_field_definition

    return [
        {
            "field_key": candidate.get("field_key", ""),
            "definition": verifier_field_definition(
                candidate.get("field_key", ""),
                f"{candidate.get('section_label', '')}/{candidate.get('field_label', '')}"
                if candidate.get("section_label") or candidate.get("field_label") else ""
            ),
            "value": candidate.get("value", ""),
            "evidence_ids": candidate.get("evidence_ids") or [],
        }
        for candidate in targets
    ]


def _split_groups(candidates: list[dict], group_by: str) -> list[dict]:
    """Compatibility grouping when no original evidence registry is supplied."""
    if group_by == "field":
        return [{"fields": [candidate], "units": _collect_units([candidate])}
                for candidate in candidates]
    groups: dict[str, list[dict]] = {}
    for candidate in candidates:
        key = candidate.get("section_key") or next(
            (unit.get("section_key") for unit in (candidate.get("evidence") or [])
             if unit.get("section_key")),
            "__no_section__",
        )
        groups.setdefault(key, []).append(candidate)
    return [
        {"fields": fields, "units": _collect_units(fields)}
        for _, fields in sorted(groups.items())
    ]


def _collect_units(fields: list[dict]) -> list[dict]:
    seen: set[str] = set()
    units: list[dict] = []
    for candidate in fields:
        for evidence in candidate.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            key = evidence.get("id") or evidence.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                units.append({
                    "id": evidence.get("id") or "",
                    "text": evidence.get("text", ""),
                    "page_no": evidence.get("page_no"),
                    "section_hint": evidence.get("section_hint") or evidence.get("section_key") or "",
                })
    return units


def _complete_json(client, user: str, system: str, json_schema: dict):
    """Use constrained decoding, with a narrow fallback for old dummy clients."""
    try:
        return client.complete_json(user, system_prompt=system, json_schema=json_schema)
    except TypeError as exc:
        if "json_schema" not in str(exc):
            raise
        return client.complete_json(user, system_prompt=system)


def _clip_comment(comment) -> str:
    """Keep comments within the external verifier display limit."""
    text = str(comment or "")
    if len(text) <= 40:
        return text
    clipped = text[:40]
    if clipped.count("'") % 2 == 1:
        last_quote = clipped.rfind("'")
        if last_quote > 0:
            clipped = clipped[:last_quote]
    return (clipped[:39] + "…")[:40]


def _comment_cited_ids(comment: str) -> list[str]:
    """提取 comment 中形如 uXXX 的引用 ID（证据编号三位数起）。"""
    return re.findall(r"u\d{3}", comment or "")


def _semantic_violations(
    verdicts: list[dict],
    expected_keys: set[str],
    evidence_ids: set[str],
) -> list[str]:
    """verifier.v2 语义契约：返回违规描述列表；非空 = 该组响应整体非法。

    - field_key 恰好返回一次，不得重复、缺失或出现组外字段；
    - pass 必须四项 checks 全 true 且 reason_code=none；
    - suspicious 必须至少一项 check=false 且 reason_code 不是 none；
    - nonstandard_expression / ocr_quality_issue 必须对应 text_standard=false；
    - extraction_mistake 必须对应 grounding/scope/logic 至少一项 false；
    - suspicious comment 必须引用本请求实际存在的 uXXX。
    历史 fail 条目不套用新语义（旧 checks 键名不同），仅保持解析兼容。
    """
    violations: list[str] = []
    keys = [v.get("field_key", "") for v in verdicts]
    if len(keys) != len(set(keys)):
        violations.append("field_key 重复")
    key_set = {k for k in keys if k}
    missing = sorted(expected_keys - key_set)
    if missing:
        violations.append(f"缺失字段 {missing}")
    extra = sorted(key_set - expected_keys)
    if extra:
        violations.append(f"组外字段 {extra}")
    for v in verdicts:
        field_key = v.get("field_key", "")
        if v.get("verdict") == "fail":
            continue
        checks = v.get("checks") or {}
        if not all(k in checks for k in _CHECK_KEYS):
            violations.append(f"{field_key} checks 缺键")
            continue
        flag_count = sum(1 for k in _CHECK_KEYS if not checks.get(k))
        if v.get("verdict") == "pass":
            if flag_count != 0 or v.get("reason_code") != "none":
                violations.append(f"{field_key} pass 但 checks 非全 true 或 reason 非 none")
        else:  # suspicious
            if flag_count == 0 or v.get("reason_code") == "none":
                violations.append(f"{field_key} suspicious 但 checks 全 true 或 reason=none")
            if v.get("reason_code") in ("nonstandard_expression", "ocr_quality_issue") \
                    and checks.get("text_standard") is not False:
                violations.append(
                    f"{field_key} {v.get('reason_code')} 但 text_standard 非 false")
            if v.get("reason_code") == "extraction_mistake" and all(
                checks.get(k) for k in ("grounding_supported", "field_scope_valid", "logic_consistent")
            ):
                violations.append(f"{field_key} extraction_mistake 但 grounding/scope/logic 全 true")
            cited = _comment_cited_ids(v.get("comment") or "")
            if not cited or not all(cid in evidence_ids for cid in cited):
                violations.append(f"{field_key} suspicious comment 未引用本请求真实 uXXX")
    return violations


def _parse_verdicts(
    payload,
    expected_keys: set[str] | None = None,
    evidence_ids: set[str] | None = None,
) -> list[dict]:
    """Parse responses with verifier.v2 semantic contract; group-skip on violations."""
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload) if isinstance(payload, str) else None
        except (json.JSONDecodeError, TypeError):
            logger.warning("复核器输出非 JSON，已降级为空意见")
            return []
    verifications = payload.get("verifications") if isinstance(payload, dict) else None
    if not isinstance(verifications, list):
        return []
    verdicts: list[dict] = []
    for item in verifications:
        if not isinstance(item, dict):
            continue
        verdict = item.get("verdict")
        if verdict not in _ALLOWED_VERDICTS:
            continue
        reason_code = item.get("reason_code") or "none"
        if reason_code not in _ALLOWED_REASONS:
            continue
        checks = item.get("checks") or {}
        if not isinstance(checks, dict):
            checks = {}
        # 历史键归一：verifier.v2 的 ocr_text_clear → v3 的 text_standard（布尔语义不变）
        checks = {
            "text_standard" if key == "ocr_text_clear" else key: value
            for key, value in checks.items()
        }
        verdicts.append({
            "field_key": item.get("field_key", ""),
            "verdict": verdict,
            "reason_code": reason_code,
            "checks": checks,
            "comment": _clip_comment(item.get("comment")),
        })
    if not verdicts:
        return []
    if expected_keys is not None:
        violations = _semantic_violations(
            verdicts, expected_keys, evidence_ids or set(),
        )
        if violations:
            logger.warning(
                "复核器语义契约违规，整组跳过 group=%s violations=%s",
                sorted(expected_keys), violations,
            )
            return []
    return verdicts


def apply_verdicts(candidates: list[dict], verdicts: list[dict]) -> list[dict]:
    """Merge suspicious/fail flags without changing any extracted value."""
    by_key = {c.get("field_key"): c for c in candidates if isinstance(c, dict)}
    for verdict in verdicts:
        field = by_key.get(verdict.get("field_key"))
        if field is None or verdict.get("verdict") not in ("suspicious", "fail"):
            continue
        flags = field.setdefault("quality_flags", [])
        if not any(
            f.get("flag") == "verifier_suspicious"
            for f in flags if isinstance(f, dict)
        ):
            flags.append({
                "flag": "verifier_suspicious",
                "severity": "warning",
                "message": verdict.get("comment") or "复核器标记，请核对原文",
            })
        if field.get("verification_status") != "failed":
            field["verification_status"] = "suspicious"
        field["attention_required"] = True
        field["attention_message"] = "复核器标记，请核对原文"
    return candidates
