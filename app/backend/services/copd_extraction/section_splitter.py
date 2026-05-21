import re

HEADINGS = ["主诉", "现病史", "既往史", "个人史", "婚育史", "家族史", "体格检查", "辅助检查"]


def normalize_text(raw_text: str) -> str:
    text = raw_text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sections(raw_text: str) -> dict[str, str]:
    text = normalize_text(raw_text)
    pattern = re.compile(rf"(?P<title>{'|'.join(map(re.escape, HEADINGS))})(?:[:：]|\n)")
    matches = list(pattern.finditer(text))
    if not matches:
        return {"全文": text}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group("title")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections
