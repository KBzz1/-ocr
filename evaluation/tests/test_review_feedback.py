"""审核回流工具单测：脱敏、金标活资产生成与加载。"""
import json

from pathlib import Path

from evaluation.code.desensitize import desensitize_text
from evaluation.code.feedback import build_review_golden, load_review_golden


def test_desensitize_masks_phone_id_and_long_numbers():
    text = "联系电话13812345678，住院号12345678901，身份证110101199003078858。"
    out = desensitize_text(text)
    assert "13812345678" not in out
    assert "12345678901" not in out
    assert "110101199003078858" not in out
    assert "联系电话" in out and "住院号" in out


def test_desensitize_masks_id_starting_with_mobile_prefix():
    # 河北/山西/内蒙古地区码(13/14/15 开头)的 18 位身份证：前 11 位恰似手机号，
    # 若手机号正则先执行会把 18 位整串拦腰截断、尾段(7 位)原样泄漏。
    # 长数字串必须整体先于手机号掩码，且掩码后不得残留任何数字。
    text = "身份证130101199003078858，电话13812345678。"
    out = desensitize_text(text)
    assert "130101199003078858" not in out
    assert "13812345678" not in out
    assert not any(ch.isdigit() for ch in out)


def test_desensitize_keeps_dates():
    text = "2023-12-22 入院，体温36.5℃"
    assert desensitize_text(text) == text


def test_build_review_golden_writes_desensitized_file(tmp_path: Path):
    feedback_dir = tmp_path / "feedback"
    golden_dir = tmp_path / "golden_review"
    feedback_dir.mkdir()
    (feedback_dir / "t001.json").write_text(json.dumps({
        "task_id": "t001", "created_at": "2026-08-01T00:00:00+00:00",
        "schema_version": "1.0.0",
        "fields": [
            {"field_key": "pe_pulse", "status": "found",
             "original_value": "6次/分", "corrected_value": "66次/分"},
            {"field_key": "pmh_diabetes", "status": "found",
             "original_value": "否认糖尿病", "corrected_value": "否认糖尿病 电话13812345678"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    path = build_review_golden(feedback_dir, golden_dir, "t001")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["source"] == "review"
    assert data["case_id"] == "t001"
    assert data["golden"][0] == {"field_key": "pe_pulse", "status": "found", "value": "66次/分"}
    assert "13812345678" not in json.dumps(data, ensure_ascii=False)


def test_load_review_golden_collects_samples(tmp_path: Path):
    golden_dir = tmp_path / "golden_review"
    golden_dir.mkdir()
    (golden_dir / "t001.json").write_text(json.dumps({
        "case_id": "t001", "source": "review",
        "golden": [{"field_key": "pe_pulse", "status": "found", "value": "66次/分"}],
    }, ensure_ascii=False), encoding="utf-8")
    samples = load_review_golden(golden_dir)
    assert len(samples) == 1
    assert samples[0]["golden"][0]["field_key"] == "pe_pulse"
