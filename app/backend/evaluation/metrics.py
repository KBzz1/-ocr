"""Deterministic value, status and atomic grounding metrics."""
from __future__ import annotations

import re
import unicodedata

from ..services.copd_extraction.field_policies import NORMAL_JUDGEMENT_FIELD_KEYS

# 评估口径版本：跨版本比较不得输出可比 delta（run_eval._print_compare 只警告）。
METRIC_VERSION = "evaluator.v2"

_KEEP = r"\w一-鿿·\-/%.+"
_STRONG_SEPARATORS = re.compile(r"[。；;\n]+")
# J 字段集合以 prompt 策略共享真源为准（T1 R2 MINOR-2）：这里保留兼容别名，
# 直接引用 field_policies 的集合，不得复制独立集合造成两侧漂移。
_KNOWN_J_FIELDS = NORMAL_JUDGEMENT_FIELD_KEYS


def normalize_text(text: str | None) -> str:
    """Normalize width, whitespace and punctuation without changing facts."""
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text)
    value = re.sub(r"[\s　]+", "", value)
    return re.sub(rf"[^{_KEEP}]+", "", value)


def compare_value(golden_value: str | None, predicted_value: str | None) -> str:
    """value two-level comparison: exact / substring / mismatch."""
    golden = normalize_text(golden_value)
    predicted = normalize_text(predicted_value)
    if golden == predicted:
        return "exact"
    if golden and predicted and (golden in predicted or predicted in golden):
        return "substring"
    return "mismatch"


def value_located_in_text(
    value: str | None,
    ocr_text: str | None,
    ocr_correction_applied: bool = False,
) -> bool:
    """Legacy whole-value diagnostic retained for callers outside the runner."""
    if not value:
        return True
    if ocr_correction_applied:
        return True
    normalized_value = normalize_text(value)
    return bool(normalized_value) and normalized_value in normalize_text(ocr_text or "")


def split_grounding_fragments(value: str | None) -> list[str]:
    """Split only on strong sentence boundaries, never ordinary commas."""
    return [part.strip() for part in _STRONG_SEPARATORS.split(value or "") if part.strip()]


def _contains(value: str, text: str) -> bool:
    normalized_value = normalize_text(value)
    return bool(normalized_value) and normalized_value in normalize_text(text)


def _join_evidence_texts(evidence_texts: list[str] | None) -> str:
    return "\n".join(str(text or "") for text in evidence_texts or [])


def correction_is_valid(
    correction: dict | None,
    cited_text: str,
    ocr_text: str,
) -> bool:
    """Return whether an OCR correction is eligible for a grounding exemption.

    ``applied=true`` alone is never enough: raw must be locatable and the raw,
    normalized value and reason must all be present.
    """
    if not isinstance(correction, dict) or not correction.get("applied"):
        return False
    raw = correction.get("raw")
    normalized = correction.get("normalized")
    reason = correction.get("reason")
    if not all(isinstance(item, str) and item.strip() for item in (raw, normalized, reason)):
        return False
    return _contains(raw, cited_text) or _contains(raw, ocr_text)


def _normal_family_supported(value: str, cited_text: str, full_text: str) -> bool:
    """Check the explicitly allowed normal-family abstraction for J fields."""
    # v2 收紧：豁免只允许预测是规范值"正常"，不能豁免任意含正常词的长文本。
    if not is_canonical_normal(value):
        return False
    # The normal-family exemption is a cited-evidence policy, not a blanket
    # full-document exemption; otherwise an unrelated ``正常`` elsewhere in
    # the record could mask a missing field citation.
    return bool(cited_text) and j_judgement_normalize(cited_text) == _J_NORMAL_TOKEN


def grounding_result(
    value: str | None,
    cited_evidence_texts: list[str] | None,
    ocr_text: str | None,
    *,
    normal_allowed: bool = False,
    correction: dict | None = None,
) -> dict:
    """Perform atomic grounding without ordinary-comma fragmentation.

    The result deliberately separates a literal whole-value diagnostic from
    unsupported claims.  Unsupported fragments are candidates, not confirmed
    hallucinations; a caller must apply an independent adjudication rule before
    counting a confirmed new clinical fact.
    """
    value = value or ""
    cited_text = _join_evidence_texts(cited_evidence_texts)
    full_text = ocr_text or ""
    if not value.strip():
        return {
            "status": "located",
            "literal_unlocated": False,
            "unsupported_fragments": [],
            "located_fragments": [],
            "outside_cited_fragments": [],
            "correction_exempt": False,
        }
    if correction_is_valid(correction, cited_text, full_text):
        return {
            "status": "located",
            "literal_unlocated": False,
            "unsupported_fragments": [],
            "located_fragments": [value],
            "outside_cited_fragments": [],
            "correction_exempt": True,
        }
    if _contains(value, cited_text):
        return {
            "status": "located",
            "literal_unlocated": False,
            "unsupported_fragments": [],
            "located_fragments": [value],
            "outside_cited_fragments": [],
            "correction_exempt": False,
        }
    if normal_allowed and _normal_family_supported(value, cited_text, full_text):
        return {
            "status": "located",
            "literal_unlocated": False,
            "unsupported_fragments": [],
            "located_fragments": [value],
            "outside_cited_fragments": [],
            "correction_exempt": False,
            "allowed_normalization": "normal_family",
        }
    fragments = split_grounding_fragments(value)
    if not fragments:
        fragments = [value]
    unsupported: list[str] = []
    located: list[str] = []
    outside_cited: list[str] = []
    for fragment in fragments:
        if _contains(fragment, cited_text):
            located.append(fragment)
        elif _contains(fragment, full_text):
            located.append(fragment)
            outside_cited.append(fragment)
        else:
            unsupported.append(fragment)
    if unsupported:
        status = "unsupported_claim_candidate"
    elif located:
        status = "located_by_fragments"
    else:
        status = "unsupported_claim_candidate"
    return {
        "status": status,
        "literal_unlocated": True,
        "unsupported_fragments": unsupported,
        "located_fragments": located,
        "outside_cited_fragments": outside_cited,
        "correction_exempt": False,
    }


# Descriptive alias for callers that treat this as an atomic grounding API.
atomic_grounding = grounding_result


def status_matches(golden_status: str, predicted_status: str) -> bool:
    return golden_status == predicted_status


# —— J 型“正常族”归一 ——
_J_NORMAL_PHRASES = (
    "正常", "通畅", "未见异常", "无异常", "阴性", "无压痛", "无肿大", "无充血水肿", "无黄染", "无发绀", "无皮疹",
)
_J_NORMAL_TOKEN = "正常"
_NEGATION_PREFIX_CHARS = ("欠", "不", "非")


def _phrase_negated(text: str, phrase: str) -> bool:
    start = 0
    while True:
        index = text.find(phrase, start)
        if index < 0:
            return False
        if index > 0 and text[index - 1] in _NEGATION_PREFIX_CHARS:
            return True
        start = index + 1


def j_judgement_normalize(value: str | None) -> str:
    if not value:
        return ""
    text = normalize_text(value)
    if any(
        not _phrase_negated(text, phrase) and phrase in text
        for phrase in _J_NORMAL_PHRASES
    ):
        return _J_NORMAL_TOKEN
    return text


# —— evaluator.v2：严格规范值"正常"与大小便投影 ——
_STOOL_URINE_TARGETS = {"hpi_stool_status": "大便", "hpi_urine_status": "小便"}


def project_stool_urine_value(value: str | None, field_key: str | None) -> str | None:
    """把"大小便…"投影到"大便…"/"小便…"（仅 hpi_stool_status/hpi_urine_status）。

    作为这两个字段作用域的等价归一，比较时金标与预测统一投影：金标"大小便…"
    可与"大便…"/"小便…"预测等价，预测保留"大小便"原文也等价。只替换首个
    "大小便"；不推广到其他字段；投影先于 J 族路由/比较判定执行。
    """
    if not value or field_key not in _STOOL_URINE_TARGETS:
        return value
    return value.replace("大小便", _STOOL_URINE_TARGETS[field_key], 1)


# 异常体征词：值中任何一段出现未被否定前缀（无/未/不/非/欠）覆盖的异常体征，
# 即非"规范正常判断"。覆盖病历查体高频体征，避免"含正常词就通过"。
_ABNORMAL_SIGNS = (
    "浮肿", "水肿", "杂音", "扩大", "增强", "减弱", "粗糙", "细弱",
    "音粗", "加快", "减慢", "发绀", "充血", "黄染", "皮疹", "出血点",
    "蜘蛛痣", "疣状斑", "疤痕", "溃疡", "畸形", "包块", "压痛",
    "肿大", "异常", "升高", "降低", "偏低", "偏高", "增快", "缩小",
    "隆起", "凹陷", "↑", "↓",
)
_NEGATION_PREFIXES = ("无", "未", "不", "非", "欠")


def _segment_has_unnegated_abnormal(segment: str) -> bool:
    """段内存在未被否定前缀覆盖的异常体征词 → 含异常内容。"""
    norm = normalize_text(segment)
    if not norm:
        return False
    for sign in _ABNORMAL_SIGNS:
        pos = norm.find(sign)
        while pos != -1:
            if not any(prefix in norm[:pos] for prefix in _NEGATION_PREFIXES):
                return True
            pos = norm.find(sign, pos + 1)
    return False


def is_canonical_normal(value: str | None) -> bool:
    """严格"规范正常判断"谓词：整个值必须是无异常内容的正常/阴性表述。

    值为"正常"二字、或全段正常/阴性描述（如"皮肤粘膜正常，无黄疸、无皮疹，
    皮肤弹性正常"）都是规范正常判断；含正常短语但混有异常内容的文本（如
    "颜面眼睑浮肿，睑结膜正常"）不得通过——这是 DESIGN §4.4 对"长篇混合
    正常与异常文本不得因含'正常'而通过"的落地。
    """
    text = normalize_text(value or "")
    if not text:
        return False
    if j_judgement_normalize(text) != _J_NORMAL_TOKEN:
        return False
    return not any(
        _segment_has_unnegated_abnormal(segment)
        for segment in re.split(r"[，,；;。\n]+", value or "")
    )


def compare_j_value(
    golden_value: str | None,
    predicted_value: str | None,
    field_key: str | None = None,
) -> str:
    """evaluator.v2 J 型非对称比较：先投影大小便金标，再按金标内容分族。

    - 规范"正常"金标（正常族）：预测也必须是规范"正常"才判 exact，混合长
      文本不得因含"正常"而通过；
    - 其余金标（异常摘录族）：原文归一后预测必须包含金标的完整摘录（附带
      正常描述不扣分）；单向包含——预测只是金标子集（如把"基本正常"缩成
      "正常"）不记分。
    """
    golden = project_stool_urine_value(golden_value, field_key)
    predicted = project_stool_urine_value(predicted_value, field_key)
    if is_canonical_normal(golden):
        return "exact" if is_canonical_normal(predicted) else "mismatch"
    golden_norm = normalize_text(golden)
    predicted_norm = normalize_text(predicted)
    if golden_norm == predicted_norm:
        return "exact"
    # 摘录族双向子串：预测包含金标完整摘录（附正常描述不扣分），或预测是
    # 金标原文的节选（如金标"否认肝炎、结核、疟疾等传染病史"、预测"否认
    # 肝炎"）都判正确。这是 §4.4 a 的"exact/substring"语义落地。
    if golden_norm and predicted_norm and (
        golden_norm in predicted_norm or predicted_norm in golden_norm
    ):
        return "substring"
    return "mismatch"


def j_judgement_fields(schema: dict) -> set[str]:
    keys: set[str] = set()
    for group in schema.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            key = field.get("field_key")
            if not key:
                continue
            if "qwen_type" in field or "review_control" in field:
                is_judgement = (
                    field.get("qwen_type") == "J"
                    or field.get("review_control") == "judgement"
                )
            else:
                is_judgement = key in _KNOWN_J_FIELDS
            if is_judgement:
                keys.add(key)
    return keys


LONG_TEXT_FIELDS = {
    "chief_complaint",
    "hpi_initial_onset", "hpi_subsequent_course", "hpi_hospital_diagnosis",
    "hpi_treatment_medications", "hpi_recent_symptoms",
}


def sentence_overlap_ratio(golden: str, predicted: str) -> float:
    """Compare long fields by strong-boundary sentence coverage."""
    def split(text: str) -> list[str]:
        return [item for item in _STRONG_SEPARATORS.split(text or "") if item.strip()]

    golden_norm = [normalize_text(item) for item in split(golden)]
    golden_norm = [item for item in golden_norm if item]
    if not golden_norm:
        return 0.0
    predicted_norm = [normalize_text(item) for item in split(predicted)]
    predicted_norm = [item for item in predicted_norm if item]
    overlap = sum(
        1 for item in golden_norm
        if any(other in item or item in other for other in predicted_norm)
    )
    return round(overlap / len(golden_norm), 4)
