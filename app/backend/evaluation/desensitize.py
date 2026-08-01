"""轻量脱敏：手机号、身份证/住院号/长数字串。日期保留（病历日期是抽取语义）。"""
import re

_PHONE = re.compile(r"1[3-9]\d{9}")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{11,18}(?!\d)")


def desensitize_text(text: str) -> str:
    if not text:
        return text
    out = _PHONE.sub("***", text)
    out = _LONG_DIGITS.sub("***", out)
    return out
