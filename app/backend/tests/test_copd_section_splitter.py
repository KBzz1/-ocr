def test_split_sections_handles_inline_headings():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    text = "主诉:咳嗽15年。现病史:1月前加重。体格检查\n体温:36.7°脉搏:99次/分"

    sections = split_sections(text)

    assert sections["主诉"] == "咳嗽15年。"
    assert sections["现病史"] == "1月前加重。"
    assert "体温:36.7" in sections["体格检查"]


def test_split_sections_returns_full_text_when_no_heading():
    from app.backend.services.copd_extraction.section_splitter import split_sections

    sections = split_sections("反复咳嗽咳痰15年")

    assert sections["全文"] == "反复咳嗽咳痰15年"
