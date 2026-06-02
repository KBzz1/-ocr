def test_split_sections_handles_inline_headings():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    text = "主诉:咳嗽15年。现病史:1月前加重。体格检查\n体温:36.7°脉搏:99次/分"

    sections = split_sections(text)

    assert sections["主诉"] == "咳嗽15年。"
    assert sections["现病史"] == "1月前加重。"
    assert "体温:36.7" in sections["体格检查"]


def test_split_sections_normalizes_common_physical_exam_alias():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    text = "主诉：咳嗽15年。查体：体温36.7℃，脉搏99次/分。"

    sections = split_sections(text)

    assert "查体" not in sections
    assert sections["体格检查"] == "体温36.7℃，脉搏99次/分。"


def test_split_sections_starts_physical_exam_at_vitals_heading_without_title():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    text = (
        "家族史：无特殊疾病。\n\n"
        "### 体温36.6℃脉搏99次/分呼吸20次/分血压136/66mmHg身高：156cm体重：63kg\n\n"
        "双肺呼吸音减低，双肺闻及散在哮鸣音。\n\n"
        "辅助检查：暂无。"
    )

    sections = split_sections(text)

    assert sections["家族史"] == "无特殊疾病。"
    assert sections["体格检查"].startswith("体温36.6℃脉搏99次/分")
    assert "双肺呼吸音减低" in sections["体格检查"]
    assert sections["辅助检查"] == "暂无。"


def test_split_sections_returns_full_text_when_no_heading():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    sections = split_sections("反复咳嗽咳痰15年")

    assert sections["全文"] == "反复咳嗽咳痰15年"
