import logging

from ..algorithm_ports.field_extraction import (
    EXTRACTION_STATUSES,
    VERIFICATION_STATUSES,
    all_fields_empty,  # noqa: F401 - re-export
)

logger = logging.getLogger(__name__)


def _default_result(field_key: str) -> dict:
    return {
        "field_key": field_key,
        "original_value": "",
        "evidence": None,
        "source_hint": None,
        "source_text": None,
        "source_group_id": None,
        "confidence": 0,
        "source_section": None,
        "extraction_status": "not_found",
        "verification_status": "not_checked",
        "quality_flags": [],
        "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
    }


def _normalize_extracted(item: dict) -> dict:
    result = _default_result(item["field_key"])
    result.update(item)
    if not isinstance(item.get("quality_flags"), list) and item.get("quality_flags") is not None:
        logger.warning("field=%s LLM returned non-list quality_flags: %s", item["field_key"], repr(item.get("quality_flags")))
    if not isinstance(item.get("verification_status"), str) and item.get("verification_status") is not None:
        logger.warning("field=%s LLM returned non-str verification_status: %s", item["field_key"], repr(item.get("verification_status")))
    if not isinstance(item.get("ocr_correction"), dict) and item.get("ocr_correction") is not None:
        logger.warning("field=%s LLM returned non-dict ocr_correction: %s", item["field_key"], repr(item.get("ocr_correction")))
    if result.get("original_value", "").strip() in {"未找到证据"}:
        result["extraction_status"] = "not_found"
        result["original_value"] = ""
        result["evidence"] = None
        result["source_hint"] = None
        result["source_text"] = None
        result["source_group_id"] = None
    if "extraction_status" not in item and result.get("original_value"):
        result["extraction_status"] = "extracted"
    if result.get("extraction_status") not in EXTRACTION_STATUSES:
        result["extraction_status"] = "extracted" if result.get("original_value") else "not_found"
    if result["extraction_status"] == "not_found":
        result["original_value"] = ""
        result["evidence"] = None
        result["source_hint"] = None
        result["source_text"] = None
        result["source_group_id"] = None
    if result["extraction_status"] == "extracted" and not result.get("original_value"):
        result["extraction_status"] = "not_found"
        result["evidence"] = None
    if not isinstance(result.get("quality_flags"), list):
        logger.warning("field=%s quality_flags is not a list (got %s), resetting to []",
                       item["field_key"], type(result.get("quality_flags")).__name__)
        result["quality_flags"] = []
    if not isinstance(result.get("verification_status"), str) or result.get("verification_status") not in VERIFICATION_STATUSES:
        logger.warning("field=%s verification_status invalid (got %s), resetting to not_checked",
                       item["field_key"], repr(result.get("verification_status")))
        result["verification_status"] = "not_checked"
    if not isinstance(result.get("ocr_correction"), dict):
        logger.warning("field=%s ocr_correction is not a dict (got %s), resetting to default",
                       item["field_key"], type(result.get("ocr_correction")).__name__)
        result["ocr_correction"] = {"applied": False, "raw": "", "normalized": "", "reason": ""}
    return result


def complete_field_results(raw_results: list[dict], field_keys: list[str]) -> list[dict]:
    by_key = {item["field_key"]: _normalize_extracted(item) for item in raw_results if item.get("field_key") in field_keys}
    return [by_key.get(key, _default_result(key)) for key in field_keys]


# all_fields_empty is re-exported from algorithm_ports.field_extraction (see top-level import)
