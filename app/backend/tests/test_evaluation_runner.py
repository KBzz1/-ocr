"""评估 runner 单测：管线组装、消融变体、报告生成（fake client，不依赖真实 LLM）。"""
import json
import pytest

from app.backend.evaluation.runner import build_report, evaluate_sample, run_pipeline


def make_schema():
    return {
        "version": "1.0.0",
        "document_type": "copd_admission_record",
        "field_groups": [
            {
                "group_key": "chief_complaint",
                "group_label": "主诉",
                "fields": [{"field_key": "chief_complaint", "label": "主诉", "review_control": "text"}],
            }
        ],
    }


def make_schema_with_j_fields():
    schema = make_schema()
    schema["field_groups"][0]["fields"].append(
        {"field_key": "pe_nose", "label": "鼻部", "qwen_type": "J"}
    )
    return schema


def make_golden_payload():
    return {
        "schema_version": "1.0.0",
        "document_type": "copd_admission_record",
        "fields": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年", "evidence_ids": []}],
    }


class FakeLlmClient:
    def __init__(self, payload):
        self._payload = payload

    def complete_json(self, prompt: str, **kwargs):
        return json.loads(json.dumps(self._payload))


SAMPLE = {
    "case_id": "case_001",
    "ocr_text": "主诉：反复咳嗽、咳痰20年，加重10余天。",
    "pitfalls": ["negation"],
    "golden": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年，加重10余天"}],
}


class TestRunPipeline:
    def test_happy_path_returns_payload_and_candidates(self):
        schema = make_schema()
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
        )
        assert result["error"] is None
        assert result["candidates"][0]["field_key"] == "chief_complaint"
        assert result["candidates"][0]["status"] == "found"

    def test_contract_failure_captured_not_raised(self):
        schema = make_schema()
        bad_payload = {"fields": []}  # 契约非法
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
        )
        assert result["error"] is not None
        assert result["error"]["code"] == "ALGORITHM_CONTRACT_INVALID"
        assert result["candidates"] == []

    def test_no_contract_skips_validation(self):
        schema = make_schema()
        bad_payload = {"fields": []}
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(bad_payload),
            check_contract=False,
        )
        assert result["error"] is None


class TestEvaluateSample:
    def test_perfect_match(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "反复咳嗽、咳痰20年，加重10余天", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["value_correct"] == 1
        assert result["metrics"]["value_total"] == 1
        assert result["metrics"]["status_correct"] == 1
        assert result["metrics"]["hallucination"] == 0

    def test_status_mismatch_counts(self):
        result = evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "not_found",
                "value": "", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })
        assert result["metrics"]["status_correct"] == 0
        assert result["metrics"]["value_correct"] == 0

    def test_contract_error_counts_as_contract_invalid(self):
        result = evaluate_sample(SAMPLE, {
            "payload": {}, "candidates": [],
            "error": {"code": "ALGORITHM_CONTRACT_INVALID", "message": "bad"},
        })
        assert result["metrics"]["contract_invalid"] == 1

    def test_skips_hallucination_when_golden_not_located(self):
        # 金标 value 在 ocr_text 不可定位（否定短语重建）→ 该字段不判幻觉
        sample = {
            "case_id": "case_001",
            "ocr_text": "否认\"糖尿病\"、\"冠心病\"等病史",
            "golden": [{"field_key": "pmh_diabetes", "status": "found", "value": "否认糖尿病病史"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pmh_diabetes", "status": "found",
                "value": "否认糖尿病病史", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        out = evaluate_sample(sample, result)
        assert out["metrics"]["hallucination"] == 0
        assert out["metrics"]["value_correct"] == 1  # 值一致

    def test_j_judgement_fields_use_normal_family_equivalence(self):
        sample = {
            "case_id": "case_001",
            "ocr_text": "鼻腔通畅，各鼻窦区无压痛",
            "golden": [{"field_key": "pe_nose", "status": "found", "value": "鼻腔通畅"}],
        }
        result = {
            "payload": {},
            "candidates": [{
                "field_key": "pe_nose", "status": "found",
                "value": "正常", "ocr_correction": {"applied": False},
            }],
            "error": None,
        }
        schema = make_schema_with_j_fields()
        out = evaluate_sample(sample, result, schema=schema)
        assert out["metrics"]["value_correct"] == 1


class TestBuildReport:
    def test_summary_and_grouping(self):
        report = build_report([evaluate_sample(SAMPLE, {
            "payload": make_golden_payload(),
            "candidates": [{
                "field_key": "chief_complaint", "status": "found",
                "value": "完全错误的值", "ocr_correction": {"applied": False},
            }],
            "error": None,
        })], {"model": "qwen", "prompt_version": "v1", "sample_count": 1})
        assert report["metrics"]["value_accuracy"] == 0.0
        assert report["metrics"]["status_accuracy"] == 1.0
        assert report["metrics"]["hallucination_count"] == 1
        assert report["by_field"]["chief_complaint"]["value_total"] == 1
        assert report["by_pitfall"]["negation"]["value_total"] == 1
        assert report["errors"] == [{"case_id": "case_001", "field_key": "chief_complaint", "kind": "value_mismatch"}]


class FakeVerifier:
    def __init__(self, verdicts):
        self._verdicts = verdicts
        self.called = 0

    def verify(self, candidates, document_text=""):
        self.called += 1
        return [dict(v) for v in self._verdicts]

    def close(self):
        pass


class TestRunPipelineVerifier:
    def test_apply_verify_default_runs_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "原文无此值"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            verifier=verifier,
        )
        assert verifier.called == 1
        candidates = result["candidates"]
        assert candidates[0]["verification_status"] == "suspicious"

    def test_no_verifier_skips_verifier(self):
        schema = make_schema()
        verifier = FakeVerifier([
            {"field_key": "chief_complaint", "verdict": "suspicious", "reason_code": "extraction_mistake",
             "checks": {}, "comment": "x"},
        ])
        result = run_pipeline(
            {"schema": schema, "document_result": {"merged_text": SAMPLE["ocr_text"]}, "evidence_units": []},
            FakeLlmClient(make_golden_payload()),
            apply_verify=False,
            verifier=verifier,
        )
        assert verifier.called == 0
        # 注意：found+无 evidence_ids 的候选在 map 阶段即被标 suspicious
        # （evidence_missing，与复核器无关），故不能断言 verification_status
        # 不等于 suspicious；改为断言复核器专属痕迹（verifier_suspicious flag）不存在。
        assert not any(
            f.get("flag") == "verifier_suspicious"
            for f in result["candidates"][0].get("quality_flags", [])
            if isinstance(f, dict)
        )
