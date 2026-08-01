"""轻量脱敏：手机号、身份证/住院号/长数字串。日期保留（病历日期是抽取语义）。"""
import re

_PHONE = re.compile(r"1[3-9]\d{9}")
_LONG_DIGITS = re.compile(r"(?<!\d)\d{11,18}(?!\d)")


def desensitize_text(text: str) -> str:
    if not text:
        return text
    # 长数字串必须先于手机号掩码：身份证/住院号前 11 位可能恰似手机号
    # （河北/山西/内蒙古地区码 13/14/15 开头），若手机号先执行会把整串
    # 拦腰截断、尾段原样泄漏。正常手机号 11 位整串仍会被 _LONG_DIGITS 完整掩码。
    out = _LONG_DIGITS.sub("***", text)
    out = _PHONE.sub("***", out)
    return out
