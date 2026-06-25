"""薄规则质量核验 —— 只输出 quality_flags，不自动纠错、不抽取字段、不导致任务失败。

当前状态：固定字段 Qwen 抽取路径（admission_contract）自行生成内部 quality_flags，
不再调用本模块的 apply_quality_checks；本模块仅由 test_copd_quality_checks.py
直接单测覆盖。保留为可复用的薄规则库，供后续质控层按需接入；删除旧版
COPDFieldExtractor 后它已不在活动处理路径上。spec 允许旧版 quality_flags 中有
价值的能力保留为医生可读 risk，不要求随 Qwen 契约一起删除。
"""

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

# —— 生理合理范围阈值（模块级常量，方便按科室/场景调整）——
PHYSIO_RANGE_TEMPERATURE = (32.0, 43.0)       # ℃
PHYSIO_RANGE_PULSE = (20, 240)                # 次/分
PHYSIO_RANGE_RESPIRATION = (3, 80)            # 次/分（下限 3 覆盖严重呼吸抑制）
PHYSIO_RANGE_BMI = (8.0, 80.0)                # kg/m²
PHYSIO_RANGE_BLOOD_GAS_PH = (6.9, 7.8)
PHYSIO_RANGE_BLOOD_GAS_PAO2 = (20.0, 700.0)   # mmHg
PHYSIO_RANGE_BLOOD_GAS_PACO2 = (10.0, 150.0)  # mmHg
PHYSIO_RANGE_BP_SYSTOLIC = (50, 260)           # mmHg
PHYSIO_RANGE_BP_DIASTOLIC = (30, 160)          # mmHg

# —— 数值矛盾检测的字段配置 ——
# key: field_key, value: (evidence 中搜索矛盾数值的正则, 触发阈值: value_number < threshold)
_NUMERIC_CONFLICT_CONFIG = {
    "pulse": (r"(?:脉搏|心率)[:：]?\s*(\d{2,3})\s*次/分", 50),
    "respiration": (r"(?:呼吸)[:：]?\s*(\d{1,2})\s*次/分", 10),
    "temperature": (r"(?:体温)[:：]?\s*(\d{2,3}(?:\.\d)?)\s*[℃°C]", 10),
}

_FIELD_KEY_ALIASES = {
    "pe_temperature": "temperature",
    "pe_pulse": "pulse",
    "pe_respiration_rate": "respiration",
    "pe_blood_pressure": "blood_pressure",
    "pe_bmi": "bmi",
}


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


def _quality_field_key(field_key: str) -> str:
    return _FIELD_KEY_ALIASES.get(field_key, field_key)


def _evidence_text(evidence) -> str:
    if isinstance(evidence, str):
        return evidence
    if isinstance(evidence, list):
        return "\n".join(
            item.get("text", "")
            for item in evidence
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
    return ""


# —————————————————————————————— 文档级质量检查 ——————————————————————————————


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


# —————————————————————————————— 单字段检查函数 ——————————————————————————————


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
    if not value or not evidence:
        return False
    # 值本身包含否定/不确定词 = 病历标准阴性表述（如“无吸烟史”“否认手术史”），
    # 不应误报为“evidence 附近存在否定语气”
    if any(word in value for word in NEGATION_OR_UNCERTAIN):
        return False
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
    """检测同一字段附近是否存在矛盾数值。

    对脉率/呼吸/体温等体征字段，当抽取值为单数字（<10，极可能为 OCR
    截断）时，在 evidence 中搜索是否有另一个合理数值。
    """
    config = _NUMERIC_CONFLICT_CONFIG.get(field_key)
    if config is None:
        return False
    pattern, threshold = config
    value_match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d)?)(?!\d)", value)
    if not value_match:
        return False
    try:
        value_number = float(value_match.group(1))
    except ValueError:
        return False
    if value_number >= threshold:
        return False
    for match in re.finditer(pattern, evidence):
        try:
            evidence_number = float(match.group(1))
        except ValueError:
            continue
        if evidence_number != value_number:
            return True
    return False


def _has_counterintuitive_zero_weight_loss(field_key: str, value: str, evidence: str) -> bool:
    """检测体重下降字段的零值矛盾。

    当 evidence 明确提到体重下降/减轻但字段值为 0 时标记，
    覆盖 OCR 可能的 O/0 混淆。
    """
    if field_key != "weight_loss":
        return False
    text = f"{value} {evidence}"
    # 上下文窗口放宽到 15 字以容纳时间修饰语（如"近1月来逐渐"）；
    # "消瘦"可独立作为体重下降的语义指示词，不强制要求"体重"前缀
    if not re.search(r"(?:体重|体质量).{0,15}(?:下降|减轻|降低|减少|消瘦)|消瘦", text):
        return False
    return bool(re.search(r"(?<!\d)[0Oo](?:\.\s*[0Oo]+)?\s*(?:g|kg|克|千克|公斤|斤)\b", text, flags=re.IGNORECASE))


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
        return number < PHYSIO_RANGE_TEMPERATURE[0] or number > PHYSIO_RANGE_TEMPERATURE[1]
    if field_key == "pulse":
        return number < PHYSIO_RANGE_PULSE[0] or number > PHYSIO_RANGE_PULSE[1]
    if field_key == "respiration":
        return number < PHYSIO_RANGE_RESPIRATION[0] or number > PHYSIO_RANGE_RESPIRATION[1]
    if field_key == "bmi":
        return number < PHYSIO_RANGE_BMI[0] or number > PHYSIO_RANGE_BMI[1]
    if field_key == "aux_blood_gas_ph":
        return number < PHYSIO_RANGE_BLOOD_GAS_PH[0] or number > PHYSIO_RANGE_BLOOD_GAS_PH[1]
    if field_key == "aux_blood_gas_po2":
        return number < PHYSIO_RANGE_BLOOD_GAS_PAO2[0] or number > PHYSIO_RANGE_BLOOD_GAS_PAO2[1]
    if field_key == "aux_blood_gas_pco2":
        return number < PHYSIO_RANGE_BLOOD_GAS_PACO2[0] or number > PHYSIO_RANGE_BLOOD_GAS_PACO2[1]
    if field_key == "blood_pressure":
        return _has_blood_pressure_range_risk(value)
    return False


def _has_blood_pressure_range_risk(value: str) -> bool:
    match = re.search(r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})(?!\d)", value or "")
    if not match:
        return False
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    return (
        systolic < PHYSIO_RANGE_BP_SYSTOLIC[0]
        or systolic > PHYSIO_RANGE_BP_SYSTOLIC[1]
        or diastolic < PHYSIO_RANGE_BP_DIASTOLIC[0]
        or diastolic > PHYSIO_RANGE_BP_DIASTOLIC[1]
    )


# —————————————————————————————— 血气标签检查 ——————————————————————————————


def _has_blood_gas_label_ocr_ambiguity(field_key: str, value: str, evidence: str) -> bool:
    """检测血气字段数值前的项目名是否疑似 OCR 错读。

    只做风险提示，不把标签改写为标准项目名。
    """
    if field_key not in {"aux_blood_gas_po2", "aux_blood_gas_pco2"}:
        return False

    for _number, prefix in _extract_value_prefixes(value, evidence):
        if field_key == "aux_blood_gas_po2":
            if re.search(r"(?i)\bpa?o2\s*$", prefix):
                continue
            if re.search(r"(?i)\bP[0-9O]{2}\s*$", prefix):
                return True
        if field_key == "aux_blood_gas_pco2":
            if re.search(r"(?i)\bpa?co2\s*$", prefix):
                continue
            if re.search(r"(?i)\bpa?c[0O]2\s*$", prefix):
                return True
    return False


def _has_blood_gas_label_not_whitelisted(field_key: str, value: str, evidence: str) -> bool:
    if field_key not in {"aux_blood_gas_po2", "aux_blood_gas_pco2"}:
        return False
    label = _blood_gas_label_before_value(value, evidence)
    if not label:
        return False
    normalized = label.upper().replace("０", "0").replace("Ｏ", "O")
    # P62 是 OCR 典型误读产物（P→P, a/O→6, O/2→2），加入白名单以避免双重标记；
    # ocr_label_ambiguity 规则会独立捕获该模式并标记风险。
    whitelists = {
        "aux_blood_gas_po2": {"PO2", "PAO2", "P02", "P62"},
        "aux_blood_gas_pco2": {"PCO2", "PACO2", "PC02", "PAC02"},
    }
    return normalized not in whitelists[field_key]


def _extract_value_prefixes(value: str, evidence: str):
    """Yield (number, prefix) tuples for each number in value found in evidence."""
    for number in _numbers(value):
        escaped = re.escape(number)
        for match in re.finditer(rf"(?<!\d){escaped}(?!\d)", evidence):
            yield number, evidence[max(0, match.start() - 16):match.start()]


def _blood_gas_label_before_value(value: str, evidence: str) -> str:
    for _number, prefix in _extract_value_prefixes(value, evidence):
        label_match = re.search(r"([A-Za-z0-9]{1,6})\s*$", prefix)
        if label_match:
            return label_match.group(1)
    return ""


# —————————————————————————————— 主入口 ——————————————————————————————


def _deduplicate_flags(item: dict) -> None:
    """去除 item['quality_flags'] 中同 flag 名的重复条目，保留首次出现。"""
    flags = item.get("quality_flags")
    if not flags:
        return
    seen: set[str] = set()
    unique: list[dict] = []
    for flag in flags:
        if not isinstance(flag, dict):
            unique.append(flag)
            continue
        name = flag.get("flag", "")
        if name and name in seen:
            continue
        seen.add(name)
        unique.append(flag)
    item["quality_flags"] = unique


def apply_quality_checks(
    fields: list[dict],
    full_text: str,
    *,
    include_document_flags: bool = True,
) -> list[dict]:
    """对字段列表施加薄规则核验，为可疑字段添加 quality_flags 并将
    verification_status 设为 "suspicious"。

    - 不自动纠错
    - 不抽取新字段
    - 不导致任务失败
    """
    checked = copy.deepcopy(fields)

    # 文档级质量检查（对完整 OCR 文本执行一次，而非每个字段的 evidence 片段）
    doc_flags = document_quality_flags(full_text) if full_text else []

    for item in checked:
        item.setdefault("quality_flags", [])
        value = item.get("original_value") or ""
        evidence = _evidence_text(item.get("evidence"))
        field_key = _quality_field_key(item.get("field_key", ""))

        # —— 数字值是否在 evidence 中出现 ——
        value_has_numbers = False
        for number in _numbers(value):
            value_has_numbers = True
            if not _number_in_evidence(number, evidence):
                item["quality_flags"].append(
                    _flag(FLAG_VALUE_NOT_IN_EVIDENCE, "字段值中的数字未能在 evidence 中直接找到")
                )
                break

        # —— 纯文本值（不含数字）是否在 evidence 中出现 ——
        if not value_has_numbers and value and evidence:
            if value not in evidence:
                item["quality_flags"].append(
                    _flag(FLAG_VALUE_NOT_IN_EVIDENCE, "字段值未在 evidence 中找到")
                )

        # —— 可疑日期 ——
        if _has_suspicious_date(value) or _has_suspicious_date(evidence):
            item["quality_flags"].append(
                _flag(FLAG_SUSPICIOUS_DATE, "日期明显晚于当前日期或与上下文不一致")
            )

        # —— 否定/不确定语气 ——
        if _has_local_negation_or_uncertainty(value, evidence) and value and value not in ("", "无", "未见", "否认"):
            item["quality_flags"].append(
                _flag(FLAG_NEGATION_OR_UNCERTAINTY_RISK, "evidence 附近存在否定或不确定语气")
            )

        # —— OCR 检验项目名疑似错读 ——
        if _has_blood_gas_label_ocr_ambiguity(field_key, value, evidence) and not _has_flag(item["quality_flags"], FLAG_OCR_LABEL_AMBIGUITY):
            item["quality_flags"].append(
                _flag(FLAG_OCR_LABEL_AMBIGUITY, "OCR 中检验项目名疑似错读，请核对原文")
            )

        # —— 血气标签不在白名单 ——
        if _has_blood_gas_label_not_whitelisted(field_key, value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_BLOOD_GAS_LABEL_NOT_WHITELISTED, "血气项目标签不在白名单内，请核对原文")
            )

        # —— 检验单位符号 OCR 错读 ——
        if _has_unit_symbol_ambiguity(field_key, value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_UNIT_SYMBOL_AMBIGUITY, "检验单位符号疑似 OCR 错读，请核对原文")
            )

        # —— 同一字段附近数值矛盾（已泛化至脉率/呼吸/体温） ——
        numeric_context = f"{evidence}\n{full_text}" if full_text else evidence
        if _has_numeric_conflict(field_key, value, numeric_context):
            item["quality_flags"].append(
                _flag(FLAG_OCR_NUMERIC_CONFLICT, "同一字段附近存在不一致数值，请核对原文")
            )

        # —— 体重下降零值矛盾（已增强正则覆盖） ——
        if _has_counterintuitive_zero_weight_loss(field_key, value, evidence):
            item["quality_flags"].append(
                _flag(FLAG_COUNTERINTUITIVE_ZERO_WEIGHT_LOSS, "体重下降/减轻为 0 与字段含义相矛盾，请核对原文")
            )

        # —— 生理合理范围 ——
        if _has_physiologic_range_risk(field_key, value):
            item["quality_flags"].append(
                _flag(FLAG_PHYSIOLOGIC_RANGE_RISK, "字段数值超出生理合理范围，请核对原文")
            )

        # —— 文档级重复/拼接 flag 附加到所有字段 ——
        if include_document_flags and doc_flags:
            for flag in doc_flags:
                if not _has_flag(item["quality_flags"], flag["flag"]):
                    item["quality_flags"].append(flag)

        # —— 去重：同名字段级别的 flag 只保留一条 ——
        _deduplicate_flags(item)

        # —— 汇总：有 flag 则标记 suspicious ——
        if item["quality_flags"] and item.get("verification_status") != "failed":
            item["verification_status"] = "suspicious"
    return checked
