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


def test_copd_extractor_batches_large_field_sets_to_avoid_truncated_json():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class BatchAwareLlmClient:
        def __init__(self):
            self.extraction_batches = []
            self.verification_batches = []

        def complete_json(self, prompt: str):
            if "字段级复核器" in prompt:
                marker = "来源分组："
                groups = json.loads(prompt.split(marker, 1)[1].strip())
                fields = [field for group in groups for field in group["fields"]]
                self.verification_batches.append([item["field_key"] for item in fields])
                return {
                    "verifications": [
                        {
                            "field_key": item["field_key"],
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
                        for item in fields
                    ]
                }
            marker = "字段 key 必须完整覆盖："
            keys_json = prompt.split(marker, 1)[1].split("\n", 1)[0]
            keys = json.loads(keys_json)
            self.extraction_batches.append(keys)
            return {
                "fields": [
                    {
                        "field_key": key,
                        "original_value": f"value-{key}",
                        "evidence": f"evidence-{key}",
                        "confidence": 0.8,
                        "source_section": "现病史",
                        "extraction_status": "extracted",
                        "verification_status": "not_checked",
                        "quality_flags": [],
                        "ocr_correction": {
                            "applied": False,
                            "raw": "",
                            "normalized": "",
                            "reason": "",
                        },
                    }
                    for key in keys
                ]
            }

    field_keys = [f"field_{index}" for index in range(13)]
    llm_client = BatchAwareLlmClient()
    extractor = COPDFieldExtractor(
        llm_client=llm_client,
        field_keys=field_keys,
        extraction_batch_size=5,
        verification_batch_size=5,
    )

    results = extractor.extract("现病史：测试文本。")

    assert [item["field_key"] for item in results] == field_keys
    assert all(item["extraction_status"] == "extracted" for item in results)
    assert llm_client.extraction_batches == [
        field_keys[0:5],
        field_keys[5:10],
        field_keys[10:13],
    ]
    assert llm_client.verification_batches == [field_keys]


def test_copd_extractor_can_skip_verification_to_keep_llm_calls_bounded():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.calls = []

        def complete_json(self, prompt: str):
            self.calls.append(prompt)
            if "字段级复核器" in prompt:
                raise AssertionError("verification should be skipped")
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "evidence": "反复咳嗽、咳痰15年",
                        "confidence": 0.8,
                        "source_section": "主诉",
                        "extraction_status": "extracted",
                        "verification_status": "not_checked",
                        "quality_flags": [],
                        "ocr_correction": {
                            "applied": False,
                            "raw": "",
                            "normalized": "",
                            "reason": "",
                        },
                    }
                ]
            }

    client = LlmClient()
    extractor = COPDFieldExtractor(
        llm_client=client,
        field_keys=["copd_history_years", "bmi"],
        extraction_batch_size=25,
        enable_verification=False,
    )

    results = extractor.extract("主诉：反复咳嗽、咳痰15年。")

    by_key = {item["field_key"]: item for item in results}
    assert len(client.calls) == 1
    assert by_key["copd_history_years"]["original_value"] == "15年"
    assert by_key["copd_history_years"]["verification_status"] == "not_checked"
    assert by_key["bmi"]["extraction_status"] == "not_found"


def test_copd_extractor_can_use_section_group_prompts_from_legacy_success_path():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.calls = []

        def complete_json(self, prompt: str):
            self.calls.append(prompt)
            assert "字段级复核器" not in prompt
            assert "主诉" in prompt
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "反复咳嗽、咳痰15年，喘累6年",
                        "evidence": "主诉：反复咳嗽、咳痰15年，喘累6年，加重1月。",
                        "confidence": 0.86,
                        "source_section": "主诉",
                        "extraction_status": "extracted",
                        "verification_status": "not_checked",
                        "quality_flags": [],
                        "ocr_correction": {
                            "applied": False,
                            "raw": "",
                            "normalized": "",
                            "reason": "",
                        },
                    }
                ]
            }

    client = LlmClient()
    extractor = COPDFieldExtractor(
        llm_client=client,
        field_keys=["copd_history_years", "bmi"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    results = extractor.extract("主诉：反复咳嗽、咳痰15年，喘累6年，加重1月。")

    by_key = {item["field_key"]: item for item in results}
    assert len(client.calls) == 1
    assert by_key["copd_history_years"]["extraction_status"] == "extracted"
    assert by_key["bmi"]["extraction_status"] == "not_found"


def test_copd_extractor_uses_source_hint_to_attach_section_text():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            assert "source_hint" in prompt
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_hint": "主诉",
                    },
                    {
                        "field_key": "baseline_lung_function",
                        "original_value": "中度阻塞性通气功能障碍",
                        "source_hint": "现病史",
                    },
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years", "baseline_lung_function"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    results = extractor.extract(
        "主诉：反复咳嗽、咳痰15年，喘累6年，加重1月。"
        "现病史：肺功能提示中度阻塞性通气功能障碍，具体未见报告。"
    )

    by_key = {item["field_key"]: item for item in results}
    assert by_key["copd_history_years"]["source_hint"] == "主诉"
    assert by_key["copd_history_years"]["evidence"] == "反复咳嗽、咳痰15年，喘累6年，加重1月。"
    assert by_key["copd_history_years"]["source_text"] == "反复咳嗽、咳痰15年，喘累6年，加重1月。"
    assert by_key["baseline_lung_function"]["source_hint"] == "现病史"
    assert by_key["baseline_lung_function"]["evidence"] == "肺功能提示中度阻塞性通气功能障碍，具体未见报告。"
    assert by_key["baseline_lung_function"]["source_text"] == "肺功能提示中度阻塞性通气功能障碍，具体未见报告。"


def test_copd_extractor_marks_missing_source_hint_section_suspicious():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_hint": "主诉",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("现病史：反复咳嗽、咳痰15年。")[0]

    assert result["extraction_status"] == "extracted"
    assert result["evidence"] is None
    assert result["verification_status"] == "suspicious"
    assert result["quality_flags"][0]["flag"] == "source_section_not_found"


def test_copd_extractor_maps_legacy_history_profile_source_to_group_text():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_section": "history_profile",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract(
        "主诉：反复咳嗽、咳痰15年。"
        "现病史：肺功能提示中度阻塞性通气功能障碍。"
        "既往史：高血压5+年。"
    )[0]

    assert result["source_hint"] == "病史资料"
    assert result["source_group_id"] == "source_group_病史资料"
    assert "【主诉】\n反复咳嗽、咳痰15年。" in result["source_text"]
    assert "【既往史】\n高血压5+年。" in result["source_text"]
    assert result["evidence"] == result["source_text"]


def test_copd_extractor_verifies_fields_grouped_by_source_hint():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.verification_payloads = []

        def complete_json(self, prompt: str):
            if "字段级复核器" in prompt:
                marker = "来源分组："
                self.verification_payloads.append(json.loads(prompt.split(marker, 1)[1].strip()))
                return {
                    "verifications": [
                        {"field_key": "copd_history_years", "verdict": "pass", "checks": {}, "comment": ""},
                        {"field_key": "dyspnea_grade_mMRC", "verdict": "suspicious", "checks": {}, "comment": "原文表述模糊"},
                    ]
                }
            return {
                "fields": [
                    {"field_key": "copd_history_years", "original_value": "15年", "source_hint": "主诉"},
                    {"field_key": "dyspnea_grade_mMRC", "original_value": "2", "source_hint": "主诉"},
                ]
            }

    client = LlmClient()
    extractor = COPDFieldExtractor(
        llm_client=client,
        field_keys=["copd_history_years", "dyspnea_grade_mMRC"],
        extraction_strategy="section_groups",
        enable_verification=True,
    )

    results = extractor.extract("主诉：反复咳嗽、咳痰15年，喘累6年，加重1月。")

    by_key = {item["field_key"]: item for item in results}
    assert by_key["copd_history_years"]["verification_status"] == "passed"
    assert by_key["dyspnea_grade_mMRC"]["verification_status"] == "suspicious"
    assert client.verification_payloads == [
        [
            {
                "source_hint": "主诉",
                "source_text": "反复咳嗽、咳痰15年，喘累6年，加重1月。",
                "fields": [
                    {"field_key": "copd_history_years", "original_value": "15年"},
                    {"field_key": "dyspnea_grade_mMRC", "original_value": "2"},
                ],
            }
        ]
    ]


def test_copd_extractor_treats_llm_unknown_placeholder_as_not_found():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "occupation", "original_value": "不详"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["occupation"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：反复咳嗽。")

    assert result[0]["field_key"] == "occupation"
    assert result[0]["extraction_status"] == "not_found"
