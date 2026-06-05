"""Review field 共享构造器,供 review/export/reextraction 三处复用。

把占位字段、候选到字段映射、summary 聚合、阻断判定收敛到同一处,避免三处实现各自漂移。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from ..enums import FieldStatus


def _now_iso(now: str | None = None) -> str:
    return now or datetime.now(timezone.utc).isoformat()


def build_placeholder_field(
    field_key: str,
    field_name: str,
    *,
    now: str | None = None,
) -> dict:
    """生成 unreviewed 占位字段(final_value/auto_value 空,不影响导出/确认阻断)。"""
    return {
        "field_key": field_key,
        "field_name": field_name,
        "auto_value": "",
        "final_value": "",
        "evidence": None,
        "page_no": None,
        "confidence": None,
        "source_hint": None,
        "source_text": None,
        "source_group_id": None,
        "source_section": None,
        "extraction_status": "not_found",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": None,
        "status": FieldStatus.UNREVIEWED.value,
        "empty_accepted": False,
        "review_note": None,
        "reviewed_at": None,
        "updated_at": _now_iso(now),
        "history": [],
    }


def build_field_from_candidate(
    field_key: str,
    field_name: str,
    candidate: dict,
    *,
    now: str | None = None,
    previous_history: list[dict] | None = None,
    previous_review_note: str | None = None,
) -> dict:
    """根据抽取候选构造 review 字段,状态重置为 unreviewed,history 透传旧条目。"""
    history = list(previous_history or [])
    field = {
        "field_key": field_key,
        "field_name": field_name,
        "auto_value": candidate.get("original_value", ""),
        "final_value": candidate.get("original_value", ""),
        "evidence": candidate.get("evidence"),
        "page_no": candidate.get("page_no"),
        "confidence": candidate.get("confidence"),
        "source_hint": candidate.get("source_hint"),
        "source_text": candidate.get("source_text"),
        "source_group_id": candidate.get("source_group_id"),
        "source_section": candidate.get("source_section"),
        "extraction_status": candidate.get("extraction_status", "extracted"),
        "verification_status": candidate.get("verification_status", "not_checked"),
        "quality_flags": list(candidate.get("quality_flags") or []),
        "ocr_correction": candidate.get("ocr_correction"),
        "status": FieldStatus.UNREVIEWED.value,
        "empty_accepted": False,
        "review_note": previous_review_note,
        "reviewed_at": None,
        "updated_at": _now_iso(now),
        "history": history,
    }
    return field


def append_reextract_history(
    field: dict,
    *,
    from_value,
    to_value: str,
    run_id: str,
    now: str | None = None,
) -> None:
    """在 field["history"] 追加 reextract 记录(空 list 走 setdefault 兜底)。"""
    field.setdefault("history", []).append({
        "action": "reextract",
        "from_value": from_value,
        "to_value": to_value,
        "run_id": run_id,
        "changed_at": _now_iso(now),
    })


def build_review_summary(fields: Iterable[dict]) -> dict:
    """统一的 review summary 聚合,与 review/export/reextraction 三处契约保持一致。"""
    fields = list(fields)
    return {
        "total_count": len(fields),
        "unreviewed_count": sum(1 for f in fields if f.get("status") == FieldStatus.UNREVIEWED.value),
        "confirmed_count": sum(1 for f in fields if f.get("status") == FieldStatus.CONFIRMED.value),
        "modified_count": sum(1 for f in fields if f.get("status") == FieldStatus.MODIFIED.value),
        "suspicious_count": sum(1 for f in fields if f.get("verification_status") == "suspicious"),
        "failed_verification_count": sum(1 for f in fields if f.get("verification_status") == "failed"),
        "not_found_count": sum(1 for f in fields if f.get("extraction_status") == "not_found"),
        "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
    }


def is_field_blocking(field: dict) -> bool:
    """字段是否阻断导出/确认。

    - UNREVIEWED 状态且 final_value 非空字符串 → 阻断(等待人工确认或修改)
    - UNREVIEWED + 空 final_value → 不阻断(占位字段,无需人工介入)
    - CONFIRMED/MODIFIED → 不阻断
    """
    if field.get("status") != FieldStatus.UNREVIEWED.value:
        return False
    final_value = field.get("final_value")
    if not isinstance(final_value, str) or not final_value.strip():
        return False
    return True
