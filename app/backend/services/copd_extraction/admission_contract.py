"""Qwen admission_record_structured_fields.v1 contract adapter.

This module is the strict, fixed-field boundary between the new Qwen
structured extraction prompt and the legacy review-candidate layer that the
backend persists and the doctor reviews.

Responsibilities:

1. ``validate_qwen_payload(payload, schema)`` — enforce the structural
   contract emitted by the Qwen model: full schema coverage, no
   unknown/duplicate field_keys, and a fixed status vocabulary. Anything
   that breaks the task-level contract raises ``ALGORITHM_CONTRACT_INVALID``
   so the orchestrator can mark the task ``failed``. The return value is a
   schema-ordered list of the structurally-validated payload fields
   (``status`` / ``value`` / ``evidence_ids``) — it does NOT refill
   ``evidence`` arrays.

2. ``map_qwen_fields_to_review_candidates(payload, schema, evidence_units)``
   — refill ``evidence`` arrays from the backend-owned evidence_units
   (never from the model's prose), translate the new ``status`` vocabulary
   into ``extraction_status`` / ``verification_status`` and surface
   per-field attention flags without fabricating text or offsets. This is
   the function Task 5 will call to land Qwen output into the review
   pipeline.

Hard constraints (from the spec and project rules):

- Do NOT correct OCR text.
- Do NOT reorder pages.
- Do NOT add sample-specific rules.
- Do NOT add bounding boxes or section recovery.
- Do NOT auto-rewrite diagnosis values; pass through verbatim.
- Do NOT fabricate evidence text or offsets.
- Internal ``quality_flags`` may stay for audit; doctor-facing
  ``attention_message`` must be plain Chinese.
"""

from __future__ import annotations

import logging
from typing import Iterable

from ...errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status vocabularies
# ---------------------------------------------------------------------------

VALID_QWEN_STATUSES = {"found", "not_found", "uncertain"}
VALID_TOP_LEVEL_KEYS = {"schema_version", "document_type", "fields"}
VALID_FIELD_KEYS = {"field_key", "status", "value", "evidence_ids"}

# Mapping from the new Qwen status to the legacy extraction_status used by the
# review-candidate layer.
_STATUS_TO_EXTRACTION = {
    "found": "extracted",
    "not_found": "not_found",
    "uncertain": "uncertain",
}

# Doctor-facing messages (plain Chinese). These are the only messages shown to
# the reviewing physician; internal flags stay in ``quality_flags``.
_MSG_MISSING_EVIDENCE = "缺少来源证据，请核对原文"
_MSG_EVIDENCE_NOT_LOCATED = "来源片段未在 OCR 文本中定位，请核对"
_MSG_UNCERTAIN = "结果不确定，请核对原文"

_INTERNAL_FLAG_MISSING_EVIDENCE = "evidence_missing"
_INTERNAL_FLAG_EVIDENCE_NOT_FOUND = "evidence_id_not_found"
_INTERNAL_FLAG_UNCERTAIN = "uncertain_status"


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------


def _iter_schema_fields(schema: dict) -> Iterable[tuple[str, dict, str, str]]:
    """Yield ``(field_key, field_meta, section_key, section_label)``.

    The schema's ``group_key`` / ``group_label`` are surfaced to the
    review-candidate layer as ``section_key`` / ``section_label`` so the
    doctor sees the same chapter vocabulary the model used to emit.
    """
    if not isinstance(schema, dict):
        return
    for group in schema.get("field_groups", []) or []:
        if not isinstance(group, dict):
            continue
        section_key = group.get("group_key", "")
        section_label = group.get("group_label", section_key)
        for field in group.get("fields", []) or []:
            if not isinstance(field, dict):
                continue
            field_key = field.get("field_key", "")
            if not field_key:
                continue
            yield field_key, field, section_key, section_label


def _schema_field_keys(schema: dict) -> list[str]:
    return [field_key for field_key, _meta, _sk, _sl in _iter_schema_fields(schema)]


# ---------------------------------------------------------------------------
# Public API: structural validation
# ---------------------------------------------------------------------------


def validate_qwen_payload(payload: dict, schema: dict) -> list[dict]:
    """Validate the Qwen structured-fields payload against the schema.

    Returns a list of the structurally-validated payload fields in
    **schema order** so the downstream layer has a stable, complete
    ordering. Each entry carries the raw ``status`` / ``value`` /
    ``evidence_ids`` from the Qwen output but NOT the refilled
    ``evidence`` array or attention metadata — that is the job of
    :func:`map_qwen_fields_to_review_candidates`, which has the
    ``evidence_units`` needed to perform highlight refilling.

    Raises ``AppError(ALGORITHM_CONTRACT_INVALID)`` for any structural
    violation (missing fields, duplicates, unknown keys, bad status, wrong
    types). All such failures are task-level failures.
    """
    by_key = _validate_and_index_by_key(payload, schema)
    return [by_key[field_key] for field_key in _schema_field_keys(schema)]


# ---------------------------------------------------------------------------
# Public API: map to review candidates
# ---------------------------------------------------------------------------


def map_qwen_fields_to_review_candidates(
    payload: dict,
    schema: dict,
    evidence_units: list[dict] | None,
) -> list[dict]:
    """Translate the validated Qwen payload into review-candidate dicts.

    Each returned dict has the keys consumed by ``complete_field_results``
    and the review UI:

    - ``field_key``, ``field_label``, ``section_key``, ``section_label``
    - ``original_value`` (verbatim from Qwen; never normalized)
    - ``extraction_status`` / ``verification_status``
    - ``evidence`` (list of dicts with id/text/start_offset/end_offset/page_no,
      or ``[]`` — never fabricated)
    - ``attention_required`` (bool), ``attention_message`` (plain Chinese)
    - ``quality_flags`` (internal flag names, retained for audit)

    Per-field attention (suspicious evidence) is surfaced here but does NOT
    fail the task-level contract.
    """
    by_key = _validate_and_index_by_key(payload, schema)
    return _build_candidates(by_key, schema, evidence_units=evidence_units)


# ---------------------------------------------------------------------------
# Internal: shared structural validation
# ---------------------------------------------------------------------------


def _validate_and_index_by_key(payload: dict, schema: dict) -> dict[str, dict]:
    """Run the structural validation loop once and return ``{field_key: entry}``.

    Centralizes the Qwen structural contract so :func:`validate_qwen_payload`
    and :func:`map_qwen_fields_to_review_candidates` share a single source of
    truth. All structural failures (non-list ``fields``, missing /
    duplicate / unknown ``field_key``, bad status, wrong value /
    evidence_ids types) raise ``AppError(ALGORITHM_CONTRACT_INVALID)``.
    """
    if not isinstance(payload, dict):
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message="Qwen 顶层 payload 必须是对象",
        )

    extra_keys = set(payload) - VALID_TOP_LEVEL_KEYS
    if extra_keys:
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message=f"Qwen payload 包含非法顶层键：{', '.join(sorted(extra_keys))}",
        )

    schema_version = schema.get("version")
    if payload.get("schema_version") != schema_version:
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message="Qwen payload.schema_version 与 schema 不一致",
        )

    document_type = schema.get("document_type")
    if payload.get("document_type") != document_type:
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message="Qwen payload.document_type 与 schema 不一致",
        )

    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, list):
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message="Qwen payload.fields 必须是数组",
        )

    allowed_keys = set(_schema_field_keys(schema))
    seen: set[str] = set()
    by_key: dict[str, dict] = {}

    for index, entry in enumerate(raw_fields):
        if not isinstance(entry, dict):
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen fields[{index}] 必须是字典",
            )
        field_key = entry.get("field_key")
        extra_field_keys = set(entry) - VALID_FIELD_KEYS
        if extra_field_keys:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=(
                    f"Qwen fields[{index}] 包含非法键："
                    f"{', '.join(sorted(extra_field_keys))}"
                ),
            )
        missing_field_keys = VALID_FIELD_KEYS - set(entry)
        if missing_field_keys:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=(
                    f"Qwen fields[{index}] 缺少键："
                    f"{', '.join(sorted(missing_field_keys))}"
                ),
            )
        if not isinstance(field_key, str) or not field_key:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen fields[{index}].field_key 必须是非空字符串",
            )
        if field_key not in allowed_keys:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen fields[{index}].field_key={field_key} 不在 schema 内",
            )
        if field_key in seen:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen field_key={field_key} 重复",
            )
        seen.add(field_key)

        status = entry.get("status")
        if status not in VALID_QWEN_STATUSES:
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen field_key={field_key} status 非法：{status!r}",
            )

        value = entry.get("value", "")
        if not isinstance(value, str):
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen field_key={field_key} value 必须是字符串",
            )

        evidence_ids = entry.get("evidence_ids", [])
        if not isinstance(evidence_ids, list) or any(
            not isinstance(eid, str) for eid in evidence_ids
        ):
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen field_key={field_key} evidence_ids 必须是字符串列表",
            )
        if len(evidence_ids) != len(set(evidence_ids)):
            raise AppError(
                ErrorCode.ALGORITHM_CONTRACT_INVALID,
                message=f"Qwen field_key={field_key} evidence_ids 不得重复",
            )

        by_key[field_key] = dict(entry)

    missing = [k for k in allowed_keys if k not in seen]
    if missing:
        raise AppError(
            ErrorCode.ALGORITHM_CONTRACT_INVALID,
            message=f"Qwen payload 缺少 schema 字段：{', '.join(missing)}",
        )

    return by_key


# ---------------------------------------------------------------------------
# Internal: evidence lookup helpers
# ---------------------------------------------------------------------------


def _build_evidence_index(evidence_units: list[dict] | None) -> dict[str, dict]:
    if not evidence_units:
        return {}
    index: dict[str, dict] = {}
    for unit in evidence_units:
        if not isinstance(unit, dict):
            continue
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not unit_id:
            continue
        # Later wins on duplicate IDs; evidence_units are unique by contract.
        index[unit_id] = unit
    return index


def _build_candidates(
    by_key: dict[str, dict],
    schema: dict,
    evidence_units: list[dict] | None,
) -> list[dict]:
    """Build review-candidate entries in schema order from validated input."""
    evidence_index = _build_evidence_index(evidence_units)
    section_lookup = {
        field_key: (section_key, section_label)
        for field_key, _meta, section_key, section_label in _iter_schema_fields(schema)
    }
    field_label_lookup = {
        field_key: meta.get("label", field_key)
        for field_key, meta, _sk, _sl in _iter_schema_fields(schema)
    }

    candidates: list[dict] = []
    for field_key, _meta, _sk, _sl in _iter_schema_fields(schema):
        entry = by_key.get(field_key)
        if entry is None:
            # Should not happen because _validate_and_index_by_key already
            # enforced completeness; keep a defensive skip here.
            continue
        section_key, section_label = section_lookup.get(field_key, ("", ""))
        field_label = field_label_lookup.get(field_key, field_key)
        status = entry["status"]
        value = entry.get("value", "")
        evidence_ids = entry.get("evidence_ids", []) or []

        # extraction_status comes from the status lookup alone; no per-status
        # reassignment needed.
        extraction_status = _STATUS_TO_EXTRACTION[status]

        verification_status = "not_checked"
        attention_required = False
        attention_message = ""
        quality_flags: list[str] = []
        evidence: list[dict] = []

        if status == "not_found":
            value = ""
        elif status == "uncertain":
            verification_status = "suspicious"
            attention_required = True
            attention_message = _MSG_UNCERTAIN
            quality_flags.append(_INTERNAL_FLAG_UNCERTAIN)
            evidence = _resolve_evidence_ids(evidence_ids, evidence_index)
        else:  # found
            if not evidence_ids:
                verification_status = "suspicious"
                attention_required = True
                attention_message = _MSG_MISSING_EVIDENCE
                quality_flags.append(_INTERNAL_FLAG_MISSING_EVIDENCE)
            else:
                resolved = _resolve_evidence_ids(evidence_ids, evidence_index)
                if len(resolved) != len(evidence_ids):
                    verification_status = "suspicious"
                    attention_required = True
                    attention_message = _MSG_EVIDENCE_NOT_LOCATED
                    quality_flags.append(_INTERNAL_FLAG_EVIDENCE_NOT_FOUND)
                else:
                    evidence = resolved

        candidates.append({
            "field_key": field_key,
            "field_label": field_label,
            "section_key": section_key,
            "section_label": section_label,
            "status": status,
            "value": value,
            "evidence_ids": list(evidence_ids),
            "original_value": value,
            "extraction_status": extraction_status,
            "verification_status": verification_status,
            "evidence": evidence,
            "attention_required": attention_required,
            "attention_message": attention_message,
            "quality_flags": quality_flags,
            "ocr_correction": {
                "applied": False,
                "raw": "",
                "normalized": "",
                "reason": "",
            },
        })

    return candidates


def _resolve_evidence_ids(
    evidence_ids: list[str], index: dict[str, dict]
) -> list[dict]:
    """Return a list of evidence dicts for the given IDs.

    Only IDs that exist in ``index`` are returned; missing IDs are skipped
    (the caller compares lengths to detect attention). Each returned dict
    carries id, text, start_offset, end_offset and optional page_no — never
    fabricated text or offsets.
    """
    resolved: list[dict] = []
    for eid in evidence_ids:
        unit = index.get(eid)
        if not isinstance(unit, dict):
            continue
        # spec: 证据无法定位时不伪造高亮。缺 offset 的 unit 视为不可定位,
        # 直接跳过——调用方通过长度不匹配检测并触发 unlocated 提示,
        # 而不是默认 offset=0 让前端高亮到文本开头。
        start_offset = unit.get("start_offset")
        end_offset = unit.get("end_offset")
        if not isinstance(start_offset, int) or not isinstance(end_offset, int):
            continue
        entry: dict = {
            "id": unit.get("id", eid),
            "text": unit.get("text", ""),
            "start_offset": start_offset,
            "end_offset": end_offset,
        }
        if "page_no" in unit and unit["page_no"] is not None:
            entry["page_no"] = unit["page_no"]
        resolved.append(entry)
    return resolved
