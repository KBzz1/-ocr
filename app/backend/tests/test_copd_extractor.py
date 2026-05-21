import json


class FakeLlmClient:
    def __init__(self):
        self.calls = []

    def complete_json(self, prompt: str):
        self.calls.append(prompt)
        if "字段级复核器" in prompt:
            return {"verifications": [
                {
                    "field_key": "bmi",
                    "verdict": "pass",
                    "checks": {
                        "evidence_supported": True,
                        "ocr_correction_reasonable": True,
                        "numeric_value_preserved": True,
                        "negation_preserved": True,
                        "section_assignment_reasonable": True,
                    },
                    "comment": "",
                }
            ]}
        return {"fields": [
            {
                "field_key": "bmi",
                "original_value": "24.2kg/m2",
                "evidence": "BHI:24.2kg/m2",
                "confidence": 0.78,
                "source_section": "体格检查",
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "ocr_correction": {
                    "applied": True,
                    "raw": "BHI",
                    "normalized": "BMI",
                    "reason": "位于身高体重之后且单位为 kg/m2",
                },
            }
        ]}


def test_copd_extractor_returns_full_field_results():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    extractor = COPDFieldExtractor(llm_client=FakeLlmClient(), field_keys=["bmi", "crp"])

    results = extractor.extract("体格检查\n身高:175cm体重:74kg。BHI:24.2kg/m2.")

    by_key = {item["field_key"]: item for item in results}
    assert by_key["bmi"]["verification_status"] == "passed"
    assert by_key["bmi"]["ocr_correction"]["applied"] is True
    assert by_key["crp"]["extraction_status"] == "not_found"
