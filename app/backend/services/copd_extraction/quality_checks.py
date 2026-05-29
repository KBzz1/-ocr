"""薄规则质量核验 —— 只输出 quality_flags，不自动纠错、不抽取字段、不导致任务失败。"""

import copy
import re
from datetime import date

NEGATION_OR_UNCERTAIN = ("无", "否认", "未见", "可能", "考虑", "建议复查")

FLAG_VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"
FLAG_SUSPICIOUS_DATE = "suspicious_date"
FLAG_NEGATION_OR_UNCERTAINTY_RISK = "negation_or_uncertainty_risk"
FLAG_POSSIBLE_DUPLICATE_OR_STITCHING = "possible_duplicate_or_stitching"
FLAG_OCR_LABEL_AMBIGUITY = "ocr_label_ambiguity"
FLAG_UNIT_SYMBOL_AMBIGUITY = "unit_symbol_ambiguity"
FLAG_OCR_NUMERIC_CONFLICT = "ocr_numeric_conflict"
FLAG_COUNTERINTUITIVE_ZERO_WEIGHT_LOSS = "counterintuitive_zero_weight_loss"
FLAG_PHYSIOLOGIC_RANGE_RISK = "physiologic_range_risk"
FLAG_BLOOD_GAS_LABEL_NOT_WHITELISTED = "blood_gas_label_not_whitelisted"

SEVERITY_WARNING = "warning"


def _numbers(text: str) -> list[str]:
    """提取文本中的数字，保留单数字以覆盖 mMRC、pH 等字段。"""
    return re.findall(r"\d+(?:\.\d+)?", text or "")


def _number_in_evidence(number: str, evidence: str) -> bool:
    """检查数字是否作为独立数值出现在 evidence 中（不允许内嵌于更长数字串中）。"""
    escaped = re.escape(number)
    return bool(re.search(rf"(?<!\d){escaped}(?!\d)", evidence))


def _flag(flag: str, message: str, severity: str = SEVERITY_WARNING) -> dict:
    return {"flag": flag, "severity": severity, "message": message}


def _has_flag(flags: list[dict], flag_name: str) -> bool:
    return any(flag.get("flag") == flag_name for flag in flags if isinstance(flag, dict))


def document_quality_flags(text: str) -> list[dict]:
    """检测整份文档的质量问题（如重复拼接）。"""
    flags = []
    sentences = [item.strip() for item in re.split(r"[。；;\n]", text or "") if item.strip()]
    seen = set()
    for sentence in sentences:
        if len(sentence) >= 8 and sentence in seen:
            flags.append(_flag(FLAG_POSSIBLE_DUPLICATE_OR_STITCHING, "文本中存在高相似重复片段"))
            break
        seen.add(sentence)
    return flags


def _has_suspicious_date(text: str) -> bool:
    """检测文本中是否存在未来年份。"""
    current_year = date.today().year
    for year in re.findall(r"(20\d{2})[-年]", text or ""):
        if int(year) > current_year:
            return True
    return False


def _value_contexts(value: str, evidence: str, radius: int = 8) -> list[str]:
    if not value or not evidence:
        return []
    contexts = []
    for match in re.finditer(re.escape(value), evidence):
        start = max(0, match.start() - radius)
        end = min(len(evidence), match.end() + radius)
        contexts.append(evidence[start:end])
    return contexts


def _has_local_negation_or_uncertainty(value: str, evidence: str) -> bool:
    return any(
        any(word in context for word in NEGATION_OR_UNCERTAIN)
        for context in _value_contexts(value, evidence)
    )


def _has_unit_symbol_ambiguity(field_key: str, value: str, evidence: str) -> bool:
    if field_key not in {"wbc", "crp", "electrolyte_imbalance"}:
        return False
    text = f"{value} {evidence}"
    return bool(re.search(r"\d+(?:\.\d+)?\s*[+*xX]\s*10\^", text))


def _has_numeric_conflict(field_key: str, value: str, evidence: str) -> bool:
    if field_key != "pulse":
        return False
    value_match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", value)
    if not value_match:
        return False
    value_number = int(value_match.group(1))
    if value_number >= 10:
        return False
    for match in re.finditer(r"(?:脉搏|心率)[:：]?\s*(\d{2,3})\s*次/分", evidence):
        if int(match.group(1)) != value_number:
            return True
    return False


def _has_counterintuitive_zero_weight_loss(field_key: str, value: str, evidence: str) -> bool:
    if field_key != "weight_loss":
        return False
    text = f"{value} {evidence}"
    if not re.search(r"(?:体重|体质量).{0,8}(?:下降|减轻|降低|减少)", text):
        return False
    return bool(re.search(r"(?<!\d)0(?:\.\s*0+)?\s*(?:g|kg|克|千克|公斤)\b", text, flags=re.IGNORECASE))


def _first_number(value: str) -> float | None:
    numbers = _numbers(value)
    if not numbers:
        return None
    try:
        return float(numbers[0])
    except ValueError:
        return None


def _has_physiologic_range_risk(field_key: str, value: str) -> bool:
    number = _first_number(value)
    if number is None:
        return False
    if field_key == "temperature":
        return number < 32 or number > 43
    if field_key == "pulse":
        return number < 20 or number > 240
    if field_key == "respiration":
        return number < 5 or number > 80
    if field_key == "bmi":
        return number < 8 or number > 80
    if field_key == "blood_gas_ph":
        return number < 6.9 or number > 7.8
    if field_key == "blood_gas_pao2":
        return number < 20 or number > 700
    if field_key == "blood_gas_paco2":
        return number < 10 or number > 150
    if field_key == "blood_pressure":
        return _has_blood_pressure_range_risk(value)
    return False


def _has_blood_pressure_range_risk(value: str) -> bool:
    match = re.search(r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})(?!\d)", value or "")
    if not match:
        return False
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    return systolic < 50 or systolic > 260 or diastolic < 30 or diastolic > 160


def _has_blood_gas_label_ocr_ambiguity(field_key: str, value: str, evidence: str) -> bool:
    """检测血气字段数值前的项目名是否疑似 OCR 错读。

    只做风险提示，不把标签改写为标准项目名。
    """
    if field_key not in {"blood_gas_pao2", "blood_gas_paco2"}:
        return False

    for number in _numbers(value):
        for match in re.finditer(rf"(?<!\d){re.escape(number)}(?!\d)", evidence):
            prefix = evidence[max(0, match.start() - 16):match.start()]
            if field_key == "blood_gas_pao2":
                if re.search(r"(?i)\bpa?o2\s*$", prefix):
                    continue
                if re.search(r"(?i)\bP[0-9O]{2}\s*$", prefix):
                    return True
            if field_key == "blood_gas_paco2":
                if re.search(r"(?i)\bpa?co2\s*$", prefix):
                    continue
                if re.search(r"(?i)\bpa?c[0O]2\s*$", prefix):
                    return True
    return False


def _has_blood_gas_label_not_whitelisted(field_key: str, value: str, evidence: str) -> bool:
    if field_key not in {"blood_gas_pao2", "blood_gas_paco2"}:
        return False
    label = _blood_gas_label_before_value(value, evidence)
    if not label:
        return False
    normalized = label.upper().replace("０", "0").replace("Ｏ", "O")
    whitelists = {
        "blood_gas_pao2": {"PO2", "PAO2", "P02", "P62"},
        "blood_gas_paco2": {"PCO2", "PACO2", "PC02", "PAC02"},
    }
    return normalized not in whitelists[field_key]


def _blood_gas_label_before_value(value: str, evidence: str) -> str:
    numbers = _numbers(value)
    if not numbers or not evidence:
        return ""
    number = numbers[0]
    for match in re.finditer(rf"(?<!\d){re.escape(number)}(?!\d)", evidence):
        prefix = evidence[max(0, match.start() - 16):match.start()]
        label_match = re.search(r"([A-Za-z0-9]{1,6})\s*$", prefix)
        if label_match:
            return label_match.group(1)
    return ""


def apply_quality_checks(fields: list[dict], full_text: str) -> list[dict]:
    """对字段列表施加薄规则核验，为可疑字段添加 quality_flags 并将
    verification_status 设为 "suspicious"。

    - 不自动纠错
    - 不抽取新字段
    - 不导致任务失败
    """
    checked = copy.deepcopy(fields)
    for item in checked:
        item.setdefault("quality_flags", [])
        value = item.get("original_value") or ""
        evidence = item.get("evidence") or ""

        for number in _numbers(value):
            if not _number_in_evidence(number, evidence):
                item["quality_flags"].append(
                    _flag(FLAG_VALUE_NOT_IN_EVIDENCE, "字段值中的数字未能在 evidence 中直接找到")
                )
                break

        if _has_suspicious_date(value) or _has_suspicious_date(evidence):
            item["quality_flags"].append(
                _flag(FLAG_SUSPICIOUS_DATE, "日期明显晚于当前日期或与上下文不一致")
            )

        if _has_local_negation_or_uncertainty(value, evidence) and value and value not in ("", "无", "未见", "否认"):
            item["quality_flags"].append(
                _flag(FLAG_NEGATION_OR_UNCERTAINTY_RISK, "evidence 附近存在否定或不确定语气")
            )

        if _has_blood_gas_label_ocr_ambiguity(item.get("field_key", ""), value, evidence) and not _has_flag(item["quality_flags"], FLAG_OCR_LABEL_AMBIGUITY):
            item["quality_flags"].append(
                _flag(FLAG_OCR_LABEL_AMBIGUITY, "OCR 中检验项目名疑似错读，请核对原文")
            )

        if _has_blood_gas_label_not_whitelisted(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_BLOOD_GAS_LABEL_NOT_WHITELISTED, "血气项目标签不在白名单内，请核对原文")
            )

        if _has_unit_symbol_ambiguity(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_UNIT_SYMBOL_AMBIGUITY, "检验单位符号疑似 OCR 错读，请核对原文")
            )

        if _has_numeric_conflict(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_OCR_NUMERIC_CONFLICT, "同一字段附近存在不一致数值，请核对原文")
            )

        if _has_counterintuitive_zero_weight_loss(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_COUNTERINTUITIVE_ZERO_WEIGHT_LOSS, "体重下降/减轻为 0 与字段含义相矛盾，请核对原文")
            )

        if _has_physiologic_range_risk(item.get("field_key", ""), value):
            item["quality_flags"].append(
                _flag(FLAG_PHYSIOLOGIC_RANGE_RISK, "字段数值超出生理合理范围，请核对原文")
            )

        evidence_flags = document_quality_flags(evidence) if evidence else []
        if evidence_flags:
            item["quality_flags"].extend(evidence_flags)

        if item["quality_flags"] and item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
    return checked
