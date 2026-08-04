"""校准工具单测：Cohen's kappa、裁定模板导出与加载（纯确定性，无 LLM）。"""
import json

from pathlib import Path

from evaluation.code.calibrate import (
    cohen_kappa,
    compute_kappa,
    export_verdicts_file,
    load_adjudications,
)


def test_cohen_kappa_known_value():
    # 2×2: [[pass/不应标, pass/应标], [suspicious/不应标, suspicious/应标]]
    # P0=(20+15)/50=0.70, Pe=(25*30+25*20)/2500=0.50 → kappa=0.40
    table = [[20, 5], [10, 15]]
    assert round(cohen_kappa(table), 4) == 0.4


def test_cohen_kappa_perfect_and_random():
    assert cohen_kappa([[30, 0], [0, 30]]) == 1.0
    assert cohen_kappa([[15, 15], [15, 15]]) == 0.0


def test_compute_kappa_builds_table_from_verdicts_and_adjudications():
    verdicts = [
        {"case_id": "c1", "field_key": "f1", "verdict": "pass"},
        {"case_id": "c1", "field_key": "f2", "verdict": "suspicious"},
        {"case_id": "c1", "field_key": "f3", "verdict": "fail"},
        {"case_id": "c1", "field_key": "f4", "verdict": "pass"},
    ]
    adjudications = {("c1", "f1"): False, ("c1", "f2"): True, ("c1", "f3"): True, ("c1", "f4"): True}
    out = compute_kappa(verdicts, adjudications)
    assert out["n"] == 4
    assert out["table"] == [[1, 1], [0, 2]]  # [[pass&不应标, pass&应标], [suspicious&不应标, suspicious&应标]]


def test_export_and_load_adjudication_template_roundtrip(tmp_path: Path):
    verdicts = [{"case_id": "c1", "field_key": "f1", "verdict": "suspicious",
                 "reason_code": "extraction_mistake", "comment": "值无证据", "value": "6次/分",
                 "evidence_text": "脉搏：66次/分"}]
    out = tmp_path / "verdicts.json"
    export_verdicts_file(verdicts, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"][0]["field_key"] == "f1"
    # 裁定文件格式
    adj_path = tmp_path / "adjudications.json"
    adj_path.write_text(json.dumps({"adjudications": [{"case_id": "c1", "field_key": "f1", "should_flag": True}]}, ensure_ascii=False), encoding="utf-8")
    assert load_adjudications(adj_path) == {("c1", "f1"): True}
