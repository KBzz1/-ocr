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

SEVERITY_WARNING = "warning"


def _numbers(text: str) -> list[str]:
    """提取文本中的数字，仅保留整数部分 >= 2 位的（过滤单数字片段噪声）。"""
    return [n for n in re.findall(r"\d+(?:\.\d+)?", text or "") if len(n.split(".")[0]) >= 2]


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

        if _has_unit_symbol_ambiguity(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_UNIT_SYMBOL_AMBIGUITY, "检验单位符号疑似 OCR 错读，请核对原文")
            )

        if _has_numeric_conflict(item.get("field_key", ""), value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_OCR_NUMERIC_CONFLICT, "同一字段附近存在不一致数值，请核对原文")
            )

        evidence_flags = document_quality_flags(evidence) if evidence else []
        if evidence_flags:
            item["quality_flags"].extend(evidence_flags)

        if item["quality_flags"] and item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
    return checked
