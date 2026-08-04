"""Tests for build_evidence_units.

These tests enforce the spec's "do not correct OCR, do not reorder pages" rules
for lightweight OCR evidence units. They verify:

- raw OCR text (including obvious typos like `品后诊断`) is preserved verbatim
- blood-gas groups stay as a single unit
- diagnosis items are not fragmented to comma-level
- every unit's offsets round-trip against ``merged_text``
- the saved page order from the backend drives unit offsets, never content-based
  reordering
"""

from app.backend.services.algorithm_ports.evidence_units import build_evidence_units


def _document_result(pages, merged_text):
    return {"pages": pages, "merged_text": merged_text}


def test_build_evidence_units_preserves_raw_ocr_title_typos():
    text = "## 品后诊断\n\n慢性阻塞性肺疾病急性加重\n\n## 初步诊断：\n\n主诉：反复咳嗽、咳痰20年。"
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": "## 品后诊断\n\n慢性阻塞性肺疾病急性加重"},
        {"page_id": "p2", "page_no": 2, "status": "success", "text": "## 初步诊断：\n\n主诉：反复咳嗽、咳痰20年。"},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    joined = "\n".join(unit["text"] for unit in units)
    assert "品后诊断" in joined, "raw OCR title typo must be preserved verbatim"
    assert "最后诊断" not in joined, "OCR text must not be auto-corrected"


def test_build_evidence_units_keeps_blood_gas_group_together():
    blood_gas_line = "血气：pH 7.40、pCO2 36.00mmHg、pO2 76.00mmHg、Na+ 130.00mmol/L、FIO2 21.00、氧合指数：361"
    text = "辅助检查\n\n" + blood_gas_line
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": "辅助检查\n\n" + blood_gas_line},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    matching = [u for u in units if "pH 7.40" in u["text"]]
    assert len(matching) == 1, "blood gas group must remain one unit, not be split by 、"
    unit = matching[0]
    for label in ("pH 7.40", "pCO2 36.00mmHg", "pO2 76.00mmHg", "Na+ 130.00mmol/L", "FIO2 21.00", "氧合指数：361"):
        assert label in unit["text"], f"blood gas label '{label}' must be inside the single unit"


def test_build_evidence_units_keeps_diagnosis_items_together():
    diagnosis_block = (
        "## 品后诊断\n\n"
        "慢性阻塞性肺疾病急性加重\n"
        "2 Ⅱ型呼吸衰竭\n"
        "3 冠心病\n"
        "4 高血压病3级"
    )
    text = diagnosis_block
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": diagnosis_block},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    # Diagnosis must stay at line-level or block-level granularity, not comma-level fragments.
    diagnosis_units = [u for u in units if "慢性阻塞性肺疾病急性加重" in u["text"]]
    assert diagnosis_units, "diagnosis content must produce a unit"
    for unit in diagnosis_units:
        # comma-level fragments would be tiny; diagnosis lines should not be
        # fragments shorter than the typical diagnosis phrase.
        assert len(unit["text"]) >= len("慢性阻塞性肺疾病急性加重"), (
            "diagnosis must not be split to comma-level fragments"
        )


def test_build_evidence_units_offsets_match_merged_text():
    blood_gas_line = "血气：pH 7.40、pCO2 36.00mmHg、pO2 76.00mmHg、Na+ 130.00mmol/L、FIO2 21.00、氧合指数：361"
    text = "辅助检查\n\n" + blood_gas_line
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": "辅助检查\n\n" + blood_gas_line},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    assert units, "expected at least one unit"
    for unit in units:
        start = unit["start_offset"]
        end = unit["end_offset"]
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 <= start < end <= len(text)
        assert text[start:end] == unit["text"], (
            f"offset slice must equal unit text; got {text[start:end]!r} vs {unit['text']!r}"
        )


def test_build_evidence_units_keeps_negated_past_history_sentence_together():
    history_line = (
        "既往史：平素身体一般，有“高血压”病史1年余，血压最高达160/90+mmHg，"
        "长期口服“厄贝沙坦氢氯喹嗪片1片1/日”降压治疗，自测血压波动在130-140/60-70mmHg左右。"
        "否认“糖尿病”、“冠心病”等病史，否认肝炎、结核等传染病史。"
        "否认外伤及手术史，否认输血史。"
    )
    text = "入院记录\n" + history_line
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": text},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    negated_history_units = [
        unit for unit in units
        if "否认“糖尿病”" in unit["text"] and "“冠心病”等病史" in unit["text"]
    ]
    assert len(negated_history_units) == 1, (
        "否认糖尿病、冠心病等病史必须保留在同一 evidence unit，"
        "否则模型和高亮都会丢失否定范围"
    )
    unit = negated_history_units[0]
    assert "否认肝炎、结核等传染病史" in unit["text"]
    assert unit["section_key"] == "past_medical_history"
    assert text[unit["start_offset"]:unit["end_offset"]] == unit["text"]


def test_build_evidence_units_uses_saved_page_order():
    # Page 1 in saved order contains "诊断" content; page 2 contains "主诉" content.
    # The order is unnatural but represents what the backend saved; offsets must
    # follow this saved order regardless of natural reading order.
    page1 = "## 品后诊断\n\n慢性阻塞性肺疾病急性加重"
    page2 = "主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。"
    text = page1 + "\n\n" + page2
    pages = [
        {"page_id": "p1", "page_no": 1, "status": "success", "text": page1},
        {"page_id": "p2", "page_no": 2, "status": "success", "text": page2},
    ]
    doc = _document_result(pages, text)

    units = build_evidence_units(doc)

    # The unit covering `主诉` must come after the diagnosis unit in offset order,
    # matching the saved page order (page 1 before page 2).
    diagnosis_unit = next(u for u in units if "品后诊断" in u["text"])
    chief_complaint_unit = next(u for u in units if "反复咳嗽、咳痰20年" in u["text"])

    assert diagnosis_unit["start_offset"] < chief_complaint_unit["start_offset"], (
        "offsets must follow saved page order, not natural reading order"
    )
    assert diagnosis_unit["page_no"] == 1
    assert chief_complaint_unit["page_no"] == 2


def test_long_history_or_exam_is_not_protected_as_vital_sign_row():
    """普通长病史/查体不能因出现两个生命体征词而吞掉句子边界。"""
    long_exam = (
        "发育正常，营养良好，体重无明显变化，神志清楚，精神可。"
        "皮肤粘膜正常，无黄染，无皮疹。"
        "正常呼吸，双肺呼吸音清，心率规则。"
    )
    text = "体格检查\n" + long_exam
    units = build_evidence_units({
        "pages": [{"page_no": 1, "status": "success", "text": text}],
        "merged_text": text,
    })

    assert len(units) >= 3
    assert max(len(unit["text"]) for unit in units) < len(long_exam)
    assert any("皮肤粘膜正常" in unit["text"] for unit in units)
    assert any("正常呼吸" in unit["text"] for unit in units)


def test_short_vital_sign_row_stays_together_after_strong_split():
    row = "体温:36.7℃ 脉搏:99次/分 呼吸:21次/分 血压:142/87mmHg"
    units = build_evidence_units({
        "pages": [{"page_no": 1, "status": "success", "text": row}],
        "merged_text": row,
    })

    assert [unit["text"] for unit in units] == [row]
