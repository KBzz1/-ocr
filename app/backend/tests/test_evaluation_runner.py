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
