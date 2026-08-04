"""Evaluation helpers for the shared original ``uXXX`` evidence stream.

The active path builds units once in ``_input_for`` and the verifier consumes
the same registry. ``inject_field_evidence`` remains only as a deprecated
compatibility helper for archived experiments.
"""
from __future__ import annotations

from app.backend.services.copd_extraction.evidence_context import assemble_verification_groups


def units_from_ocr_text(ocr_text: str) -> list[dict]:
    """从纯文本 OCR 构建证据单元（复用 evidence_units 切分规则与 section_key 推断）。

    构造单页 document_result 喂 build_evidence_units；返回带
    id/text/start_offset/end_offset/可选 page_no/section_key 的 units。
    """
    from app.backend.services.algorithm_ports.evidence_units import build_evidence_units

    text = ocr_text or ""
    return build_evidence_units({
        "pages": [{"text": text, "page_no": 1}],
        "merged_text": text,
    })


def build_review_context(
    candidates: list[dict], evidence_units: list[dict], group_by: str | None = "section",
) -> list[dict]:
    """Expose the production/evaluation context assembler for tooling/tests."""
    return assemble_verification_groups(
        candidates, evidence_units, group_by=group_by, neighbor_radius=1
    )


def inject_field_evidence(candidates: list[dict], units: list[dict]) -> list[dict]:
    """按字段值在 units 中的定位回填 evidence（命中 unit + 紧邻上下文各 1 个）。

    定位策略：值的前 8 个字符在 unit 文本中出现即命中（值开头最稳定）；
    无命中时退化为值内任意 6 字符窗口。命中后取该 unit 及其前后各 1 个
    相邻 unit 作为该字段证据（保留上下文）。未定位或值为空的字段 evidence
    置空列表——复核器按现状兜底 document_text（None 模式）或渲染
    "（未提供证据）"（分组模式），不崩溃、不凭空造证据。
    """
    if not units:
        return candidates
    for c in candidates:
        value = (c.get("value") or "").strip()
        if not value:
            c["evidence"] = []
            continue
        head = value[:8]
        idx = _locate_unit(units, head, value)
        if idx is None:
            c["evidence"] = []
            continue
        start, end = max(0, idx - 1), min(len(units), idx + 2)
        c["evidence"] = [dict(u) for u in units[start:end]]
    return candidates


def _locate_unit(units: list[dict], head: str, value: str) -> int | None:
    for i, u in enumerate(units):
        text = u.get("text", "")
        if head and head in text:
            return i
    if len(value) >= 6:
        for i, u in enumerate(units):
            text = u.get("text", "")
            if any(value[j:j + 6] in text for j in range(0, len(value) - 5)):
                return i
    return None
