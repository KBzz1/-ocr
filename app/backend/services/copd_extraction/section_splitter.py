import re

DEFAULT_HEADINGS = ["主诉", "现病史", "既往史", "个人史", "婚育史", "家族史", "体格检查", "辅助检查"]
HEADING_ALIASES = {
    "查体": "体格检查",
    "入院查体": "体格检查",
    "体查": "体格检查",
    "实验室检查": "辅助检查",
    "影像学检查": "辅助检查",
    "胸部CT": "辅助检查",
    "肺功能": "辅助检查",
    "血气分析": "辅助检查",
}
FULL_TEXT_KEY = "全文"


def normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(
        r"(?m)^(?:#+\s*)?(?=(?:体温\s*\d|T\s*[:：]?\s*\d).{0,40}(?:脉搏|P\s*[:：]?\s*\d))",
        "体格检查：",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(raw_text: str, headings: list[str] | None = None) -> dict[str, str]:
    text = normalize_text(raw_text)
    headings = headings if headings is not None else DEFAULT_HEADINGS + list(HEADING_ALIASES)
    pattern = re.compile(rf"(?P<title>{'|'.join(map(re.escape, headings))})(?:[:：]|\n)")
    matches = list(pattern.finditer(text))
    if not matches:
        return {FULL_TEXT_KEY: text}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = HEADING_ALIASES.get(match.group("title"), match.group("title"))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if title in sections and section_text:
            sections[title] = f"{sections[title]}\n{section_text}"
        else:
            sections[title] = section_text
    return sections
