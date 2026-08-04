"""Deterministic evidence registry and verifier context assembly.

The extraction port owns the original ``uXXX`` units.  This module only
selects those units and their immediate neighbours; it never searches for a
predicted value and never creates a second ID namespace.
"""
from __future__ import annotations


def _unit_order(unit: dict, fallback: int) -> int:
    value = unit.get("order")
    return value if isinstance(value, int) else fallback


def normalize_units(evidence_units: list[dict] | None) -> list[dict]:
    """Return a copy with stable display metadata, preserving IDs and text."""
    result: list[dict] = []
    for index, unit in enumerate(evidence_units or [], 1):
        if not isinstance(unit, dict):
            continue
        unit_id = unit.get("id")
        text = unit.get("text")
        if not isinstance(unit_id, str) or not unit_id or not isinstance(text, str):
            continue
        copied = dict(unit)
        copied["order"] = _unit_order(unit, index)
        copied["section_hint"] = unit.get("section_hint") or unit.get("section_key") or ""
        result.append(copied)
    result.sort(key=lambda u: (u.get("order", 0), u.get("start_offset", 0)))
    return result


def build_evidence_registry(evidence_units: list[dict] | None) -> dict[str, dict]:
    """Index original evidence units by ID; duplicate IDs are invalid input."""
    registry: dict[str, dict] = {}
    for unit in normalize_units(evidence_units):
        registry[unit["id"]] = unit
    return registry


def _candidate_ids(candidate: dict) -> list[str]:
    ids = candidate.get("evidence_ids") or []
    return [item for item in ids if isinstance(item, str) and item]


def _group_key(candidate: dict, group_by: str | None) -> str:
    if group_by == "field":
        return str(candidate.get("field_key") or "__no_field__")
    if group_by == "section":
        return str(candidate.get("section_key") or "__no_section__")
    return "__all__"


def assemble_verification_groups(
    candidates: list[dict],
    evidence_units: list[dict] | None,
    group_by: str | None = None,
    neighbor_radius: int = 1,
) -> list[dict]:
    """Build groups with cited units plus one original neighbour on each side.

    Each group contains ``missing_ids``.  The verifier must skip a group with
    any missing ID before calling an LLM.  That distinction prevents an
    evidence-packet assembly error from becoming a model-labelled field error.
    """
    units = normalize_units(evidence_units)
    registry = {u["id"]: u for u in units}
    positions = {u["id"]: i for i, u in enumerate(units)}
    grouped: dict[str, list[dict]] = {}
    for candidate in candidates or []:
        grouped.setdefault(_group_key(candidate, group_by), []).append(candidate)

    output: list[dict] = []
    for key, fields in grouped.items():
        cited_ids: list[str] = []
        for field in fields:
            for evidence_id in _candidate_ids(field):
                if evidence_id not in cited_ids:
                    cited_ids.append(evidence_id)
        missing_ids = [eid for eid in cited_ids if eid not in registry]
        if not cited_ids:
            missing_ids = ["<empty evidence_ids>"]

        selected: set[int] = set()
        for evidence_id in cited_ids:
            index = positions.get(evidence_id)
            if index is None:
                continue
            start = max(0, index - max(0, neighbor_radius))
            end = min(len(units), index + max(0, neighbor_radius) + 1)
            selected.update(range(start, end))
        context_units = [dict(units[i]) for i in sorted(selected)]
        output.append({
            "group_key": key,
            "fields": fields,
            "cited_ids": cited_ids,
            "missing_ids": missing_ids,
            "units": context_units,
        })
    return output
