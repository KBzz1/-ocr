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
    if result.get("original_value"):
        result["extraction_status"] = "extracted"
    result.setdefault("quality_flags", [])
    result.setdefault("verification_status", "not_checked")
    result.setdefault("ocr_correction", {"applied": False, "raw": "", "normalized": "", "reason": ""})
    return result


def complete_field_results(raw_results: list[dict], field_keys: list[str]) -> list[dict]:
    by_key = {item["field_key"]: _normalize_extracted(item) for item in raw_results if item.get("field_key") in field_keys}
    return [by_key.get(key, _default_result(key)) for key in field_keys]


def all_fields_empty(field_results: list[dict]) -> bool:
    return all(not (item.get("original_value") or "").strip() for item in field_results)
