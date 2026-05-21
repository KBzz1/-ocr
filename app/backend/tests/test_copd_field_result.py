def test_complete_field_results_fills_not_found_fields():
    from app.backend.services.copd_extraction.field_result import complete_field_results

    results = complete_field_results(
        [{"field_key": "bmi", "original_value": "24.2", "evidence": "BHI:24.2kg/m2"}],
        ["bmi", "crp"],
    )

    by_key = {item["field_key"]: item for item in results}
    assert by_key["bmi"]["extraction_status"] == "extracted"
    assert by_key["crp"]["extraction_status"] == "not_found"
    assert by_key["crp"]["original_value"] == ""
    assert by_key["crp"]["evidence"] is None
    assert by_key["crp"]["ocr_correction"]["applied"] is False


def test_all_empty_detects_full_empty_result():
    from app.backend.services.copd_extraction.field_result import all_fields_empty

    assert all_fields_empty([
        {"field_key": "bmi", "original_value": "", "extraction_status": "not_found"},
        {"field_key": "crp", "original_value": "", "extraction_status": "not_found"},
    ])
