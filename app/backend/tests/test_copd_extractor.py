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


def test_copd_extractor_can_use_section_group_prompts_with_source_hint():
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
                        "source_hint": "主诉",
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
    # Spec invariant: evidence must not equal source_text; for short sections, recovery returns the value itself
    assert by_key["copd_history_years"]["evidence"] == "15年"
    assert by_key["copd_history_years"]["evidence"] != by_key["copd_history_years"]["source_text"]
    assert by_key["copd_history_years"]["source_text"] == "反复咳嗽、咳痰15年，喘累6年，加重1月。"
    assert by_key["baseline_lung_function"]["source_hint"] == "现病史"
    assert by_key["baseline_lung_function"]["evidence"] == "中度阻塞性通气功能障碍"
    assert by_key["baseline_lung_function"]["evidence"] != by_key["baseline_lung_function"]["source_text"]
    assert by_key["baseline_lung_function"]["source_text"] == "肺功能提示中度阻塞性通气功能障碍，具体未见报告。"


def test_copd_extractor_prefers_section_group_evidence_phrase_over_section_text():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": "脉搏78次/分",
                        "source_hint": "体格检查",
                        "confidence": 0,
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分，呼吸20次/分。")[0]

    assert result["evidence"] == "脉搏78次/分"
    assert result["source_text"] == "体温36.7℃，脉搏78次/分，呼吸20次/分。"
    assert result["confidence"] == 0


def test_copd_extractor_extracts_physical_exam_fields_from_chati_alias():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.prompts = []

        def complete_json(self, prompt: str):
            self.prompts.append(prompt)
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "99次/分",
                        "evidence_phrase": "脉搏99次/分",
                        "source_hint": "体格检查",
                        "confidence": 0.8,
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
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：咳嗽15年。查体：体温36.7℃，脉搏99次/分。")[0]

    assert len(client.prompts) == 1
    assert "【体格检查】" in client.prompts[0]
    assert result["extraction_status"] == "extracted"
    assert result["source_hint"] == "体格检查"
    assert result["source_text"] == "体温36.7℃，脉搏99次/分。"
    assert result["evidence"] == "脉搏99次/分"


def _flag_names(item: dict) -> set[str]:
    return {flag["flag"] for flag in item.get("quality_flags", [])}


def test_copd_extractor_recovers_evidence_from_value_when_phrase_missing():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "78次/分", "source_hint": "体格检查"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分，呼吸20次/分，血压128/76mmHg，神志清楚，精神可，营养中等。")[0]

    assert result["evidence"] != result["source_text"]
    assert "78次/分" in result["evidence"]
    assert len(result["evidence"]) <= 50
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    assert "evidence_recovered_from_value" in _flag_names(result)


def test_copd_extractor_returns_none_evidence_when_value_not_locatable():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "88次/分", "source_hint": "体格检查"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，呼吸20次/分。")[0]

    assert result["evidence"] is None
    assert result["verification_status"] == "suspicious"
    assert "evidence_missing_fallback" in _flag_names(result)


def test_copd_extractor_discards_evidence_phrase_longer_than_50_chars_and_keeps_warning_flag():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    long_evidence = "体温36.7℃，脉搏78次/分，呼吸20次/分，血压128/76mmHg，神志清楚，双肺呼吸音粗，双下肢无水肿。"

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": long_evidence,
                        "source_hint": "体格检查",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract(f"体格检查：{long_evidence}")[0]

    assert len(result["evidence"]) <= 50
    assert result["evidence"] != long_evidence
    assert "78次/分" in result["evidence"]
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    flags = _flag_names(result)
    assert "evidence_too_long" in flags
    assert "evidence_recovered_from_value" in flags


def test_copd_extractor_discards_evidence_phrase_not_in_source_text_and_keeps_warning_flag():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": "脉搏88次/分",
                        "source_hint": "体格检查",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分。")[0]

    assert len(result["evidence"]) <= 50
    assert "78次/分" in result["evidence"]
    assert result["evidence"] in result["source_text"]
    assert result["verification_status"] == "suspicious"
    flags = _flag_names(result)
    assert "evidence_not_in_source_text" in flags
    assert "evidence_recovered_from_value" in flags


def test_copd_extractor_does_not_use_full_text_key_for_recovery():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "78次/分", "source_hint": "全文"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：咳嗽。\n体格检查：脉搏78次/分。")[0]

    assert result["evidence"] is None
    assert result["source_section"] is None
    assert result["source_text"] is None
    assert result["verification_status"] == "suspicious"
    assert "source_section_not_found" in _flag_names(result)


def test_copd_extractor_degrades_failed_section_group_to_suspicious_not_found():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            if "`physical_exam`" in prompt:
                raise RuntimeError("llm oom")
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "evidence_phrase": "咳嗽15年",
                        "source_hint": "主诉",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years", "pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    results = extractor.extract("主诉：咳嗽15年。体格检查：脉搏78次/分。")
    by_key = {item["field_key"]: item for item in results}

    assert by_key["copd_history_years"]["extraction_status"] == "extracted"
    assert by_key["pulse"]["extraction_status"] == "not_found"
    assert by_key["pulse"]["verification_status"] == "suspicious"
    assert by_key["pulse"]["quality_flags"][0]["flag"] == "llm_group_failed"


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


def test_copd_extractor_accepts_explicit_no_evidence_source_hint():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_hint": "未找到证据",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：反复咳嗽。")[0]

    assert result["extraction_status"] == "extracted"
    assert result["evidence"] is None
    assert result["verification_status"] == "suspicious"
    assert result["quality_flags"][0]["flag"] == "source_section_not_found"


def test_copd_extractor_regenerates_invalid_source_hint_with_same_loaded_client():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.calls = []

        def complete_json(self, prompt: str):
            self.calls.append(prompt)
            if "重新生成字段来源指向" in prompt:
                return {
                    "fields": [
                        {
                            "field_key": "copd_history_years",
                            "original_value": "15年",
                            "source_hint": "主诉",
                        }
                    ]
                }
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_section": "history_profile",
                    }
                ]
            }

    client = LlmClient()
    extractor = COPDFieldExtractor(
        llm_client=client,
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract(
        "主诉：反复咳嗽、咳痰15年。"
        "现病史：肺功能提示中度阻塞性通气功能障碍。"
        "既往史：高血压5+年。"
    )[0]

    assert len(client.calls) == 2
    assert result["source_hint"] == "主诉"
    assert result["source_group_id"] == "source_group_主诉"
    assert result["source_text"] == "反复咳嗽、咳痰15年。"
    # Spec invariant: evidence must not equal source_text; short-section recovery returns the value
    assert result["evidence"] == "15年"
    assert result["evidence"] != result["source_text"]


def test_copd_extractor_preserves_short_evidence_phrase_after_source_hint_regeneration():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            if "重新生成字段来源指向" in prompt:
                return {
                    "fields": [
                        {
                            "field_key": "copd_history_years",
                            "original_value": "15年",
                            "source_hint": "主诉",
                        }
                    ]
                }
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "source_hint": "history_profile",
                        "evidence_phrase": "咳嗽、咳痰15年",
                        "confidence": 0.82,
                        "ocr_correction": {
                            "applied": False,
                            "raw": "",
                            "normalized": "",
                            "reason": "",
                        },
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：反复咳嗽、咳痰15年。")[0]

    assert result["source_hint"] == "主诉"
    assert result["evidence"] == "咳嗽、咳痰15年"
    assert result["confidence"] == 0.82


def test_copd_extractor_treats_no_evidence_as_not_found_in_section_groups():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "未找到证据",
                        "source_hint": "未找到证据",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("主诉：反复咳嗽。")[0]

    assert result["extraction_status"] == "not_found"
    assert result["original_value"] == ""


def test_copd_extractor_treats_no_evidence_as_not_found_in_field_batches():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "copd_history_years",
                        "original_value": "未找到证据",
                        "source_hint": "现病史",
                        "extraction_status": "extracted",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["copd_history_years"],
        extraction_strategy="field_batches",
        enable_verification=False,
    )

    result = extractor.extract("主诉：反复咳嗽。")[0]

    assert result["extraction_status"] == "not_found"
    assert result["original_value"] == ""
    assert result["evidence"] is None


def test_field_regeneration_strategies_are_extensible():
    from app.backend.services.copd_extraction.extractor import FIELD_REGENERATION_STRATEGIES

    strategy_names = [strategy.name for strategy in FIELD_REGENERATION_STRATEGIES]

    assert strategy_names == ["source_hint_regeneration"]


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
                    {
                        "field_key": "copd_history_years",
                        "original_value": "15年",
                        "evidence_phrase": "反复咳嗽、咳痰15年",
                        "source_hint": "主诉",
                    },
                    {
                        "field_key": "dyspnea_grade_mMRC",
                        "original_value": "2",
                        "evidence_phrase": "喘累6年",
                        "source_hint": "主诉",
                    },
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


def test_copd_extractor_passes_bounded_original_ocr_context_to_verification():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def __init__(self):
            self.verification_prompt = ""

        def complete_json(self, prompt: str):
            if "字段级复核器" in prompt:
                self.verification_prompt = prompt
                return {"verifications": [{"field_key": "bmi", "verdict": "pass", "checks": {}, "comment": ""}]}
            return {"fields": [{"field_key": "bmi", "original_value": "24.2kg/m2", "source_hint": "体格检查"}]}

    client = LlmClient()
    extractor = COPDFieldExtractor(
        llm_client=client,
        field_keys=["bmi"],
        extraction_strategy="section_groups",
        enable_verification=True,
    )
    long_tail = "补充描述" * 500

    extractor.extract(f"主诉：咳嗽。体格检查：BMI:24.2kg/m2。辅助检查：{long_tail}")

    assert "原始 OCR 上下文" in client.verification_prompt
    assert "体格检查：BMI:24.2kg/m2" in client.verification_prompt
    assert len(client.verification_prompt) < 5000


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


def test_recover_evidence_from_value_locates_and_creates_window():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    # source_text is intentionally longer than max_chars=50 to exercise windowing
    source_text = "前导" * 20 + "体温：36.7℃ 脉搏：99次/分" + "后缀" * 20
    result = _recover_evidence_from_value("36.7℃", source_text, max_chars=50)

    assert result is not None
    assert "36.7℃" in result
    assert len(result) == 50
    assert result in source_text


def test_recover_evidence_from_value_returns_none_when_value_not_in_source():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    assert _recover_evidence_from_value("40℃", "体温：36.7℃", max_chars=50) is None


def test_recover_evidence_from_value_returns_none_for_empty_value():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    assert _recover_evidence_from_value("", "anything", max_chars=50) is None
    assert _recover_evidence_from_value("   ", "anything", max_chars=50) is None


def test_recover_evidence_from_value_returns_none_when_value_exceeds_max_chars():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    long_value = "x" * 60
    assert _recover_evidence_from_value(long_value, long_value + " tail", max_chars=50) is None


def test_recover_evidence_from_value_returns_value_not_whole_section_when_section_is_short():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    # Section shorter than max_chars=50; without the fix, this would return the whole section
    source_text = "脉搏78次/分。"
    result = _recover_evidence_from_value("78次/分", source_text, max_chars=50)

    assert result is not None
    assert result != source_text
    assert result == "78次/分"


def test_recover_evidence_from_value_returns_none_when_value_equals_whole_section():
    from app.backend.services.copd_extraction.extractor import _recover_evidence_from_value

    # Pathological: original_value is the entire section
    source_text = "78次/分"
    result = _recover_evidence_from_value("78次/分", source_text, max_chars=50)

    assert result is None


def test_copd_extractor_evidence_never_equals_source_text_for_short_sections():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    class LlmClient:
        def complete_json(self, prompt: str):
            return {"fields": [{"field_key": "pulse", "original_value": "78次/分", "source_hint": "体格检查"}]}

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    # Use a short section (shorter than max_chars=50)
    result = extractor.extract("体格检查：脉搏78次/分。")[0]

    assert result["evidence"] is not None
    assert result["evidence"] != result["source_text"]
    assert "78次/分" in result["evidence"]
    assert len(result["evidence"]) <= 50


def test_copd_extractor_appends_both_too_long_and_not_in_source_flags():
    from app.backend.services.copd_extraction.extractor import COPDFieldExtractor

    # Long evidence that is also not in the source section
    long_unrelated_evidence = "这段证据完全不在体格检查章节内" * 4  # 60 chars

    class LlmClient:
        def complete_json(self, prompt: str):
            return {
                "fields": [
                    {
                        "field_key": "pulse",
                        "original_value": "78次/分",
                        "evidence_phrase": long_unrelated_evidence,
                        "source_hint": "体格检查",
                    }
                ]
            }

    extractor = COPDFieldExtractor(
        llm_client=LlmClient(),
        field_keys=["pulse"],
        extraction_strategy="section_groups",
        enable_verification=False,
    )

    result = extractor.extract("体格检查：体温36.7℃，脉搏78次/分。")[0]

    flags = _flag_names(result)
    assert "evidence_too_long" in flags
    assert "evidence_not_in_source_text" in flags
    # Recovery should still succeed since the value "78次/分" is in the section
    assert "evidence_recovered_from_value" in flags
    assert "78次/分" in result["evidence"]
    assert result["evidence"] in result["source_text"]
