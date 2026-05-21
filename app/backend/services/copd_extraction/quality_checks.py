"""薄规则质量核验 —— 只输出 quality_flags，不自动纠错、不抽取字段、不导致任务失败。"""

import copy
import re
from datetime import date

NEGATION_OR_UNCERTAIN = ("无", "否认", "未见", "可能", "考虑", "建议复查")

FLAG_VALUE_NOT_IN_EVIDENCE = "value_not_in_evidence"
FLAG_SUSPICIOUS_DATE = "suspicious_date"
FLAG_NEGATION_OR_UNCERTAINTY_RISK = "negation_or_uncertainty_risk"
FLAG_POSSIBLE_DUPLICATE_OR_STITCHING = "possible_duplicate_or_stitching"

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


def apply_quality_checks(fields: list[dict], full_text: str) -> list[dict]:
    """对字段列表施加薄规则核验，为可疑字段添加 quality_flags 并将
    verification_status 设为 "suspicious"。

    - 不自动纠错
    - 不抽取新字段
    - 不导致任务失败
    """
    checked = copy.deepcopy(fields)
    doc_flags = document_quality_flags(full_text)
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

        if any(word in evidence for word in NEGATION_OR_UNCERTAIN) and value and value not in ("", "无", "未见", "否认"):
            item["quality_flags"].append(
                _flag(FLAG_NEGATION_OR_UNCERTAINTY_RISK, "evidence 附近存在否定或不确定语气")
            )

        if doc_flags:
            item["quality_flags"].extend(doc_flags)

        if item["quality_flags"] and item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
    return checked
