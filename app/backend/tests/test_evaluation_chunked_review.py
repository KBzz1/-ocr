"""Tests for evaluation-side evidence injection (chunked_review).

These tests cover:

- ``units_from_ocr_text`` builds evidence units from plain OCR text by reusing
  the evidence_units split rules and section_key inference
- ``inject_field_evidence`` locates a field value in the units and attaches the
  hit unit plus one neighbouring unit on each side as field evidence
- unlocated values and empty values fall back to an empty evidence array
  (the verifier then falls back to document_text, or renders "（未提供证据）"
  in grouped mode — never fabricates evidence)
"""

from app.backend.evaluation.chunked_review import inject_field_evidence, units_from_ocr_text

OCR = "主诉：反复咳嗽、咳痰20年。\n现病史：20年前患者受凉后反复出现咳嗽。\n体格检查：神清，颈软，气管居中。体温36.5℃，脉搏88次/分。\n辅助检查：血气分析示PO2 60mmHg。"


def test_units_from_ocr_text_splits_by_sentence():
    units = units_from_ocr_text(OCR)
    assert any("反复咳嗽、咳痰20年" in u["text"] for u in units)   # 主诉句成 unit
    assert any("颈软" in u["text"] for u in units)                  # 体格检查行成 unit
    assert all(u["id"].startswith("u") for u in units)
    assert all("start_offset" in u and "end_offset" in u for u in units)
    # 含章节头时给出 section_key（best-effort）
    assert any(u.get("section_key") == "chief_complaint" for u in units)


def test_inject_field_evidence_located_with_context():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_pulse", "status": "found", "value": "脉搏88次/分"}]
    result = inject_field_evidence(candidates, units)
    ev = result[0]["evidence"]
    assert ev, "值应在 units 中可定位"
    assert any("88次/分" in u["text"] for u in ev)
    # 上下文邻接：证据含命中 unit 前一个 unit（体温行）
    assert any("体温" in u["text"] for u in ev)


def test_inject_field_evidence_unlocated_falls_back_empty():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_skin", "status": "found", "value": "皮肤无异常（原文无此句）"}]
    result = inject_field_evidence(candidates, units)
    assert result[0]["evidence"] == []


def test_inject_field_evidence_skips_empty_value():
    units = units_from_ocr_text(OCR)
    candidates = [{"field_key": "pe_skin", "status": "found", "value": ""}]
    result = inject_field_evidence(candidates, units)
    assert result[0]["evidence"] == []
