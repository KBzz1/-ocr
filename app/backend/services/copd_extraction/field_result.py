from ..algorithm_ports.field_extraction import (
    EXTRACTION_STATUSES,
    all_fields_empty,  # noqa: F401 - re-export
)


def _default_result(field_key: str) -> dict:
    return {
        "field_key": field_key,
        "original_value": "",
        "evidence": None,
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
    if "extraction_status" not in item and result.get("original_value"):
        result["extraction_status"] = "extracted"
    if result.get("extraction_status") not in EXTRACTION_STATUSES:
        result["extraction_status"] = "extracted" if result.get("original_value") else "not_found"
    if result["extraction_status"] == "not_found":
        result["original_value"] = ""
        result["evidence"] = None
    if result["extraction_status"] == "extracted" and not result.get("original_value"):
        result["extraction_status"] = "not_found"
        result["evidence"] = None
    result.setdefault("quality_flags", [])
    result.setdefault("verification_status", "not_checked")
    if not isinstance(result.get("ocr_correction"), dict):
        result["ocr_correction"] = {"applied": False, "raw": "", "normalized": "", "reason": ""}
    return result


def complete_field_results(raw_results: list[dict], field_keys: list[str]) -> list[dict]:
    by_key = {item["field_key"]: _normalize_extracted(item) for item in raw_results if item.get("field_key") in field_keys}
    return [by_key.get(key, _default_result(key)) for key in field_keys]


# all_fields_empty is re-exported from algorithm_ports.field_extraction (see top-level import)
