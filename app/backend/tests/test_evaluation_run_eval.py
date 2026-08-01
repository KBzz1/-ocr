"""run_eval CLI 冒烟：fake client 注入验证脚本链路，不依赖真实 LLM。

- test_cli_end_to_end_with_fake_client：正常链路（金标加载 → 抽取 → 报告落盘）。
- test_uncaught_llm_error_marks_sample_error_and_continues：真实 LLM 客户端
  （QwenVLLMClient.complete_json）在服务不可用/超时时抛的是 RuntimeError 等
  非 AppError 异常，会穿透 run_pipeline 的内部捕获；CLI 样本循环必须兜底，
  把该样本记为 EVAL_LLM_FAILURE error 并继续下一个样本，不中断整个评估。
"""
import json
from pathlib import Path

from app.backend.evaluation import run_eval
from app.backend.services.schema_loader import load_schema

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

    def spy_evaluate_sample(sample, result, schema=None):
        captured.append((sample.get("case_id"), result))
        return real_evaluate_sample(sample, result, schema)

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

    # 失败样本详情落报告 errors 明细（--compare 错误集对比可见）
    assert [e["kind"] for e in report["errors"]] == ["eval_llm_failure"]
    failure = report["errors"][0]
    assert failure["case_id"] == "case_001"
    assert failure["field_key"] == ""
    assert "connection refused" in failure["message"]


def _field_map(schema):
    return {f["field_key"]: f for g in schema["field_groups"] for f in g["fields"]}


def test_cli_golden_review_writes_separate_report(tmp_path, monkeypatch):
    """--golden-review：review 活资产单独统计，报告与 manual 分开落盘。"""
    schema_path = _write_schema(tmp_path)
    golden_dir = _write_golden(tmp_path, ["case_001"])
    review_golden_dir = tmp_path / "golden_review"
    review_golden_dir.mkdir()
    (review_golden_dir / "r001.json").write_text(json.dumps({
        "case_id": "r001", "source": "review",
        "schema_version": "1.0.0",
        "golden": [{"field_key": "chief_complaint", "status": "found",
                    "value": "反复咳嗽、咳痰20年"}],
    }, ensure_ascii=False), encoding="utf-8")
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    monkeypatch.setattr(run_eval, "build_llm_client", lambda args: FakeClient())
    report_path = run_eval.main([
        "--golden-dir", str(golden_dir),
        "--golden-review", str(review_golden_dir),
        "--schema", str(schema_path),
        "--model", "fake-model",
        "--report-dir", str(report_dir),
    ])

    # manual 主报告不混入 review 样本
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["metrics"]["sample_count"] == 1
    assert report["meta"].get("source") is None

    # review 子集单独成报告,meta 标注 source=review
    review_report_path = next(p for p in report_dir.glob("*_review.json"))
    review_report = json.loads(review_report_path.read_text(encoding="utf-8"))
    assert review_report["meta"]["source"] == "review"
    assert review_report["metrics"]["sample_count"] == 1
    assert review_report["metrics"]["value_accuracy"] == 1.0
    assert review_report["by_pitfall"]["review_feedback"]["value_total"] == 1


def test_merge_j_annotations_from_batch_schema():
    # 构造 schema：v2 的 J 注解（qwen_type=J / review_control=judgement）按字段名
    # 合并到 v1 同名字段；非 J 字段、v1 独有字段不受影响；不引入 v2 独有字段。
    v1 = {
        "version": "v1", "document_type": "copd_admission_record",
        "field_groups": [
            {"group_key": "pe", "group_label": "体格检查", "fields": [
                {"field_key": "pe_nose", "label": "鼻部", "type": "string"},
                {"field_key": "pe_chest", "label": "胸部", "type": "string"},
            ]},
            {"group_key": "v1_only", "group_label": "v1独有", "fields": [
                {"field_key": "v1_only_field", "label": "独有", "type": "string"},
            ]},
        ],
    }
    v2 = {
        "version": "v2", "document_type": "qwen_batch_admission_record",
        "field_groups": [
            {"group_key": "pe", "group_label": "体格检查", "fields": [
                {"field_key": "pe_nose", "qwen_type": "J", "review_control": "judgement"},
                {"field_key": "pe_chest", "qwen_type": "T", "review_control": "text"},
            ]},
            {"group_key": "v2_only", "group_label": "v2独有", "fields": [
                {"field_key": "v2_only_field", "qwen_type": "J", "review_control": "judgement"},
            ]},
        ],
    }
    merged = run_eval._merge_j_annotations(v1, v2)
    fields = _field_map(merged)
    assert fields["pe_nose"]["qwen_type"] == "J"
    assert fields["pe_nose"]["review_control"] == "judgement"
    assert "qwen_type" not in fields["pe_chest"]  # 非 J 注解不合并
    assert "qwen_type" not in fields["v1_only_field"]  # v1 独有字段不受影响
    assert "v2_only_field" not in fields  # 不引入 v2 独有字段


def test_real_v1_schema_merges_v2_j_annotations():
    # 真实 v1（61 字段，无注解）合并真实 v2 后：共享 J 字段被标注，
    # v1 独有字段（v2 无同名字段）不受影响。
    root = Path(run_eval.__file__).resolve().parents[3]
    v1 = load_schema(str(root / "app" / "config" / "schemas" / "admission_record_structured_fields.v1.yaml"))
    v2 = load_schema(run_eval._BATCH_SCHEMA_PATH)
    merged = run_eval._merge_j_annotations(v1, v2)
    fields = _field_map(merged)
    assert fields["pe_nose"]["qwen_type"] == "J"
    assert fields["pe_nose"]["review_control"] == "judgement"
    assert fields["pmh_hepatitis_b"]["qwen_type"] == "J"
    assert fields["pmh_hepatitis_b"]["review_control"] == "judgement"
    assert "qwen_type" not in fields["hpi_mental_status"]  # v1 独有字段不受影响
    assert "qwen_type" not in fields["pe_respiratory_exam"]  # 与 v2 不同名，不受影响


def test_main_passes_merged_schema_to_evaluate_sample(tmp_path, monkeypatch):
    # 接线：run_eval 加载 v1 后合并 v2 J 注解，evaluate_sample 收到已标注 schema。
    root = Path(run_eval.__file__).resolve().parents[3]
    schema_path = root / "app" / "config" / "schemas" / "admission_record_structured_fields.v1.yaml"
    golden_dir = _write_golden(tmp_path, ["case_001"])
    report_dir = tmp_path / "reports"
    report_dir.mkdir()

    captured = {}
    real_evaluate_sample = run_eval.evaluate_sample

    def spy_evaluate_sample(sample, result, schema=None):
        captured["schema"] = schema
        return real_evaluate_sample(sample, result, schema)

    monkeypatch.setattr(run_eval, "build_llm_client", lambda args: FakeClient())
    monkeypatch.setattr(run_eval, "evaluate_sample", spy_evaluate_sample)
    run_eval.main([
        "--golden-dir", str(golden_dir),
        "--schema", str(schema_path),
        "--model", "fake-model",
        "--report-dir", str(report_dir),
    ])
    fields = _field_map(captured["schema"])
    assert fields["pe_nose"]["qwen_type"] == "J"
    assert fields["chief_complaint"].get("qwen_type") != "J"  # T 字段不受影响
