"""run_eval CLI 冒烟：fake client 注入验证脚本链路，不依赖真实 LLM。

- test_cli_end_to_end_with_fake_client：正常链路（金标加载 → 抽取 → 报告落盘）。
- test_uncaught_llm_error_marks_sample_error_and_continues：真实 LLM 客户端
  （QwenVLLMClient.complete_json）在服务不可用/超时时抛的是 RuntimeError 等
  非 AppError 异常，会穿透 run_pipeline 的内部捕获；CLI 样本循环必须兜底，
  把该样本记为 EVAL_LLM_FAILURE error 并继续下一个样本，不中断整个评估。
"""
import json

from app.backend.evaluation import run_eval

SCHEMA_YAML = (
    "version: 1.0.0\n"
    "document_type: copd_admission_record\n"
    "field_groups:\n"
    "  - group_key: chief_complaint\n"
    "    group_label: 主诉\n"
    "    fields:\n"
    "      - field_key: chief_complaint\n"
    "        label: 主诉\n"
)


def _write_schema(tmp_path):
    schema_path = tmp_path / "schema.yaml"
    schema_path.write_text(SCHEMA_YAML, encoding="utf-8")
    return schema_path


def _write_golden(tmp_path, case_ids):
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    for case_id in case_ids:
        (golden_dir / f"{case_id}.json").write_text(json.dumps({
            "case_id": case_id,
            "ocr_text": "主诉：反复咳嗽、咳痰20年。",
            "pitfalls": ["negation"],
            "golden": [{"field_key": "chief_complaint", "status": "found", "value": "反复咳嗽、咳痰20年"}],
        }, ensure_ascii=False), encoding="utf-8")
    return golden_dir


class FakeClient:
    def complete_json(self, prompt, **kwargs):
        return {"schema_version": "1.0.0", "document_type": "copd_admission_record",
                "fields": [{"field_key": "chief_complaint", "status": "found",
                            "value": "反复咳嗽、咳痰20年", "evidence_ids": []}]}

    def close(self):
        pass


class FlakyClient:
    """第一个样本抛 RuntimeError（模拟 vLLM 服务不可用），之后正常返回。"""

    def __init__(self):
        self._calls = 0

    def complete_json(self, prompt, **kwargs):
        self._calls += 1
        if self._calls == 1:
            raise RuntimeError("vLLM 服务不可用: connection refused")
        return {"schema_version": "1.0.0", "document_type": "copd_admission_record",
                "fields": [{"field_key": "chief_complaint", "status": "found",
                            "value": "反复咳嗽、咳痰20年", "evidence_ids": []}]}

    def close(self):
        pass


def test_cli_end_to_end_with_fake_client(tmp_path, monkeypatch):
    schema_path = _write_schema(tmp_path)
    golden_dir = _write_golden(tmp_path, ["case_001"])
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    monkeypatch.setattr(run_eval, "build_llm_client", lambda args: FakeClient())
    report_path = run_eval.main([
        "--golden-dir", str(golden_dir),
        "--schema", str(schema_path),
        "--model", "fake-model",
        "--report-dir", str(report_dir),
    ])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["value_accuracy"] == 1.0
    assert report["metrics"]["contract_invalid_count"] == 0
    assert report["meta"]["model"] == "fake-model"


def test_uncaught_llm_error_marks_sample_error_and_continues(tmp_path, monkeypatch):
    schema_path = _write_schema(tmp_path)
    golden_dir = _write_golden(tmp_path, ["case_001", "case_002"])
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    captured = []
    real_evaluate_sample = run_eval.evaluate_sample

    def spy_evaluate_sample(sample, result):
        captured.append((sample.get("case_id"), result))
        return real_evaluate_sample(sample, result)

    monkeypatch.setattr(run_eval, "build_llm_client", lambda args: FlakyClient())
    monkeypatch.setattr(run_eval, "evaluate_sample", spy_evaluate_sample)
    report_path = run_eval.main([
        "--golden-dir", str(golden_dir),
        "--schema", str(schema_path),
        "--model", "fake-model",
        "--report-dir", str(report_dir),
    ])
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # 第一个样本的 RuntimeError 被兜底为 error 记录，循环未中断
    assert [cid for cid, _ in captured] == ["case_001", "case_002"]
    _, failed_result = captured[0]
    assert failed_result["error"]["code"] == "EVAL_LLM_FAILURE"
    assert "connection refused" in failed_result["error"]["message"]

    # 报告仍生成；失败样本计为 contract_invalid，第二个样本正常评估
    assert report["metrics"]["sample_count"] == 2
    assert report["metrics"]["contract_invalid_count"] == 1
    assert report["metrics"]["value_accuracy"] == 1.0
    assert report["meta"]["model"] == "fake-model"
