<!-- 组件口径全文（prompt-full.md 统一模板）
组件: evaluator（评估指标）
版本: evaluator.v1
恢复来源: git show f8cabaa（v1 终态）（commit f8cabaa）——评估器无 prompt，以指标源码为口径全文
快照日期: 2026-08-05
-->

# evaluator metrics.py 快照（指标口径全文）

```python
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


# —— J 型"正常族"归一 ——
_J_NORMAL_PHRASES = ("正常", "通畅", "未见异常", "无异常", "阴性", "无压痛", "无肿大", "无充血水肿", "无黄染", "无发绀", "无皮疹")
_J_NORMAL_TOKEN = "正常"
# 正常族短语前的否定前缀：欠通畅 / 不通畅 / 稍欠通畅 / 非阴性 等否定形态
# 不属于"正常族"（"欠通畅"≠"通畅"），不得折叠为"正常"。
_NEGATION_PREFIX_CHARS = ("欠", "不", "非")


def _phrase_negated(t: str, phrase: str) -> bool:
    """t 中是否存在紧邻否定前缀（欠/不/非）的 phrase 出现（如 欠通畅）。"""
    start = 0
    while True:
        i = t.find(phrase, start)
        if i < 0:
            return False
        if i > 0 and t[i - 1] in _NEGATION_PREFIX_CHARS:
            return True
        start = i + 1
    return False


def j_judgement_normalize(value: str | None) -> str:
    """J 型字段"正常族"语义归一：正常/通畅/未见异常/阴性 等 → 统一 token。

    否定形态（欠/不/非 前缀，如"鼻腔欠通畅"）保持原文，不折叠为"正常"。
    """
    if not value:
        return ""
    t = normalize_text(value)
    if any(not _phrase_negated(t, phrase) and phrase in t for phrase in _J_NORMAL_PHRASES):
        return _J_NORMAL_TOKEN
    return t


def j_judgement_fields(schema: dict) -> set[str]:
    """从 schema 提取 J 型字段（qwen_type=J 或 review_control=judgement）。"""
    keys: set[str] = set()
    for group in schema.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            fk = field.get("field_key")
            if not fk:
                continue
            if field.get("qwen_type") == "J" or field.get("review_control") == "judgement":
                keys.add(fk)
    return keys


# —— 长文本字段宽松判定 ——
LONG_TEXT_FIELDS = {
    "chief_complaint",
    "hpi_initial_onset", "hpi_subsequent_course", "hpi_hospital_diagnosis",
    "hpi_treatment_medications", "hpi_recent_symptoms",
}


def sentence_overlap_ratio(golden: str, predicted: str) -> float:
    """按句切分后共有句占比（取金标视角）。容忍摘录范围差异，不放过大面积错摘。

    金标句被覆盖 = 某预测句与其归一化后相同/互为子串（摘录或扩写都算共有），
    与 compare_value 的子串语义一致。归一化后为空串的句（纯标点段）两边都不
    保留——空串对任意句恒"包含"，会污染判定（ratio 虚高为 1.0）。
    """
    import re as _re

    def split(text: str) -> list[str]:
        return [s for s in _re.split(r"[。；;\n]", text or "") if s.strip()]

    g_norm = [s for s in (normalize_text(x) for x in split(golden)) if s]
    if not g_norm:
        return 0.0
    p_norm = [s for s in (normalize_text(x) for x in split(predicted)) if s]
    overlap = sum(1 for s in g_norm if any(p in s or s in p for p in p_norm))
    return round(overlap / len(g_norm), 4)

```
