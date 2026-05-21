def test_copd_ocr_samples_cover_required_error_families():
    from app.backend.tests.fixtures.copd_ocr_samples import COPD_OCR_SAMPLES

    families = {family for sample in COPD_OCR_SAMPLES for family in sample["error_families"]}

    assert "indicator_label_ocr" in families
    assert "medication_or_medical_term_ocr" in families
    assert "numeric_unit_range_anomaly" in families
    assert "date_or_institution_ocr" in families
    assert "duplicate_or_stitching" in families
    assert "negation_or_uncertainty" in families
    assert len(COPD_OCR_SAMPLES) >= 5
