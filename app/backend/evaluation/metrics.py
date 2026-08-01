"""评估指标模块：确定性金标比对（不依赖 LLM 打分）。

指标语义见 docs/superpowers/specs/2026-08-01-evaluation-harness-design.md 第 4 节：
- compare_value: 归一化一致 → exact；互为子串 → substring；否则 mismatch。
- value_located_in_text: 幻觉判定（value 必须在 ocr_text 中可定位）。
- status_matches: found/not_found/uncertain 严格比对。
"""
import re
import unicodedata

_KEEP = r"\w一-鿿·\-/%.+"


def normalize_text(text: str | None) -> str:
    """归一化：全角→半角、去空白、去标点。

    保留汉字、字母、数字与数值关键符号（· - / % . +），
    使数值类字段（136/68mmHg、10-20口/日）比对不失真。
    """
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\s　]+", "", t)
    t = re.sub(rf"[^{_KEEP}]+", "", t)
    return t


def compare_value(golden_value: str | None, predicted_value: str | None) -> str:
    """value 两级判定：exact / substring / mismatch。"""
    g = normalize_text(golden_value)
    p = normalize_text(predicted_value)
    if g == p:
        return "exact"
    if g and p and (g in p or p in g):
        return "substring"
    return "mismatch"


def value_located_in_text(
    value: str | None,
    ocr_text: str | None,
    ocr_correction_applied: bool = False,
) -> bool:
    """幻觉判定：value 必须在 OCR 原文中可定位。

    空 value 恒 True（not_found 不判幻觉）；应用了 ocr_correction
    的字段豁免（受控纠偏，spec 第 4 节指标 3 例外）。
    """
    if not value:
        return True
    if ocr_correction_applied:
        return True
    v = normalize_text(value)
    return bool(v) and v in normalize_text(ocr_text or "")


def status_matches(golden_status: str, predicted_status: str) -> bool:
    """status 严格比对（found/not_found/uncertain）。"""
    return golden_status == predicted_status
