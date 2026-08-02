"""评估管线组装与报告生成。

默认管线与 COPDAdmissionQwenFieldPort.extract 行为一致（prompt → LLM →
契约校验 → evidence 回填 → quality_checks → verifier 复核）；消融变体通过
check_contract / apply_quality / apply_verify 开关控制（spec 第 5 节）。
契约失败不抛出，捕获为 error；复核失败由 FieldVerifier 静默降级，不改变指标。
"""
from ..errors import AppError
from ..services.copd_extraction.admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)
from ..services.copd_extraction.prompts import build_admission_structured_fields_messages
from ..services.copd_extraction.quality_checks import apply_quality_checks
from ..services.copd_extraction.verifier import FieldVerifier, apply_verdicts
from .metrics import (
    LONG_TEXT_FIELDS,
    compare_value,
    j_judgement_fields,
    j_judgement_normalize,
    sentence_overlap_ratio,
    status_matches,
    value_located_in_text,
)

FIELD_STATUSES = ("found", "not_found", "uncertain")


def run_pipeline(
    input: dict,
    llm_client,
    *,
    check_contract: bool = True,
    apply_quality: bool = True,
    apply_verify: bool = True,
    verifier=None,
    append_reminder: bool = False,
) -> dict:
    """跑单条样本的抽取管线，返回 payload / candidates / error。

    append_reminder=True（变体 B）时 user 末尾追加结构提醒句，默认 False
    保持与生产端口行为一致（变体 A）。
    """
    schema = input.get("schema") or {}
    document_result = input.get("document_result") or {}
    evidence_units = input.get("evidence_units") or []
    document_text = document_result.get("merged_text") or ""

    system, user = build_admission_structured_fields_messages(
        schema=schema,
        evidence_units=evidence_units,
        document_text=document_text,
        append_reminder=append_reminder,
    )
    try:
        payload = llm_client.complete_json(user, system_prompt=system)
    except AppError as exc:
        return {"payload": {}, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    if check_contract:
        try:
            validate_qwen_payload(payload, schema)
        except AppError as exc:
            return {"payload": payload, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    try:
        candidates = map_qwen_fields_to_review_candidates(payload, schema, evidence_units=evidence_units)
    except AppError as exc:
        # map 内部会再做一次结构校验（与 validate 共用同一校验循环）。
        # --no-contract 消融语义：契约层被移除，该失败不算 error，样本无候选；
        # 开启契约时理论上到不了这里（validate 已先拦下），兜底记录 error。
        if check_contract:
            return {"payload": payload, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
        return {"payload": payload, "candidates": [], "error": None}
    if apply_quality:
        candidates = apply_quality_checks(
            candidates, document_text, include_document_flags=False
        )
    if apply_verify:
        verifier = verifier or FieldVerifier(llm_client)
        verdicts = verifier.verify(candidates, document_text)
        candidates = apply_verdicts(candidates, verdicts)
    return {"payload": payload, "candidates": candidates, "error": None}


def evaluate_sample(sample: dict, result: dict, schema: dict | None = None) -> dict:
    """单样本指标分量。candidates 与金标按 field_key 对齐。

    返回包裹结构 {"metrics", "field_totals", "pitfalls"}：metrics 含五指标
    分量与错误明细；field_totals 为逐字段 value 计数（build_report 按字段
    分组）；pitfalls 透传样本陷阱类别（build_report 按类别分组）。

    schema 提供时，qwen_type=J / review_control=judgement 字段的 value 先做
    "正常族"归一再比对（鼻腔通畅==正常）；长文本字段用核心句重合率替代
    全串比对；幻觉判定前先测金标 value 可定位性——金标本身在 OCR 不可定位
    （否定短语重建的期望输出）时跳过该字段的幻觉判定，真错误由 value_mismatch 兜底。
    """
    golden_by_key = {f["field_key"]: f for f in sample.get("golden", [])}
    candidates_by_key = {c["field_key"]: c for c in result.get("candidates", [])}
    ocr_text = sample.get("ocr_text") or ""
    j_fields = j_judgement_fields(schema) if isinstance(schema, dict) else set()
    metrics = {
        "value_correct": 0, "value_total": 0,
        "status_correct": 0, "status_total": 0,
        "hallucination": 0, "contract_invalid": 0, "errors": [],
    }
    field_totals: list[dict] = []
    if result.get("error"):
        metrics["contract_invalid"] = 1
        if result["error"].get("code") == "EVAL_LLM_FAILURE":
            # CLI 兜底的 LLM 失败：样本详情落 errors 明细，使失败样本在报告
            # JSON 与 --compare 错误集对比中可见。field_key 用空串占位，
            # 保持 {case_id, field_key, kind} 三元组结构兼容（sorted 安全）。
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": "",
                "kind": "eval_llm_failure",
                "message": result["error"].get("message", ""),
            })
        return {"metrics": metrics, "field_totals": field_totals, "pitfalls": sample.get("pitfalls", [])}
    for field_key, golden in golden_by_key.items():
        candidate = candidates_by_key.get(field_key)
        if candidate is None:
            continue
        golden_status = golden.get("status")
        predicted_status = candidate.get("status")
        if golden_status not in FIELD_STATUSES:
            continue
        # status 指标
        metrics["status_total"] += 1
        if status_matches(golden_status, predicted_status):
            metrics["status_correct"] += 1
        else:
            metrics["errors"].append(
                {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "status_mismatch"}
            )
        # value 指标（not_found 金标不做 value 比对；uncertain 仅 status）
        golden_value = golden.get("value", "")
        predicted_value = candidate.get("value", "")
        correction_applied = bool((candidate.get("ocr_correction") or {}).get("applied"))
        if golden_status == "not_found":
            if predicted_value != "":
                metrics["errors"].append(
                    {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_not_empty_when_not_found"}
                )
            continue
        if golden_status == "uncertain":
            continue
        metrics["value_total"] += 1
        field_totals.append({"field_key": field_key, "value_correct": 0, "value_total": 1})
        # value 判定：J 型字段先做"正常族"归一；长文本字段用核心句重合率；
        # 其余字段走默认归一化两级判定。
        if field_key in j_fields:
            g_n, p_n = j_judgement_normalize(golden_value), j_judgement_normalize(predicted_value)
            verdict = compare_value(g_n, p_n)
        elif field_key in LONG_TEXT_FIELDS:
            verdict = "exact" if sentence_overlap_ratio(golden_value, predicted_value) >= 0.6 else "mismatch"
        else:
            verdict = compare_value(golden_value, predicted_value)
        if verdict in ("exact", "substring"):
            metrics["value_correct"] += 1
            field_totals[-1]["value_correct"] = 1
        else:
            metrics["errors"].append(
                {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "value_mismatch"}
            )
        # 幻觉（veto）：value 必须在 OCR 原文可定位。值本身已错时 value_mismatch
        # 已记录该字段失败，错误明细只保留真正"值对但不可定位"的 veto 个案。
        # 金标 value 本身在 OCR 不可定位（否定短语重建的期望输出不可定位）时
        # 跳过该字段的幻觉判定，真错误由 value_mismatch 兜底。
        # J 型字段"正常族"语义等价（金标"鼻腔通畅"↔预测"正常"）时，预测 token
        # 不必在原文逐字出现，跳过该字段的幻觉判定；语义不等价（如金标异常
        # 描述被折叠为"正常"）仍按原逻辑判幻觉。
        j_equivalent = (
            field_key in j_fields
            and j_judgement_normalize(golden_value) == j_judgement_normalize(predicted_value)
        )
        golden_located = value_located_in_text(golden_value, ocr_text)
        if not j_equivalent and not value_located_in_text(predicted_value, ocr_text, correction_applied) and golden_located:
            metrics["hallucination"] += 1
            if verdict in ("exact", "substring"):
                metrics["errors"].append(
                    {"case_id": sample.get("case_id"), "field_key": field_key, "kind": "hallucination"}
                )
    return {"metrics": metrics, "field_totals": field_totals, "pitfalls": sample.get("pitfalls", [])}


def build_report(sample_results: list[dict], meta: dict) -> dict:
    """汇总五指标 + 按字段分组 + 按陷阱类别分组 + 错误明细。"""
    total = {
        "value_correct": 0, "value_total": 0,
        "status_correct": 0, "status_total": 0,
        "hallucination": 0, "contract_invalid": 0,
    }
    by_field: dict[str, dict] = {}
    by_pitfall: dict[str, dict] = {}
    errors: list[dict] = []

    # sample_results 需要携带 sample（case_id/pitfalls）与指标分量；由调用方在
    # evaluate_sample 后补上 pitfalls 再传入，见 run_eval 的组装（Task 4）。
    for r in sample_results:
        metrics = r["metrics"]
        for key in total:
            total[key] += metrics.get(key, 0)
        errors.extend(metrics.get("errors", []))
        for f in r.get("field_totals", []):
            d = by_field.setdefault(f["field_key"], {"value_correct": 0, "value_total": 0})
            d["value_total"] += f["value_total"]
            d["value_correct"] += f["value_correct"]
        for pitfall in r.get("pitfalls", []):
            d = by_pitfall.setdefault(pitfall, {"value_correct": 0, "value_total": 0})
            d["value_total"] += r["metrics"]["value_total"]
            d["value_correct"] += r["metrics"]["value_correct"]

    return {
        "meta": meta,
        "metrics": {
            "status_accuracy": _safe_div(total["status_correct"], total["status_total"]),
            "value_accuracy": _safe_div(total["value_correct"], total["value_total"]),
            "hallucination_count": total["hallucination"],
            "contract_invalid_count": total["contract_invalid"],
            "task_success_count": sum(
                1 for r in sample_results
                if r["metrics"]["contract_invalid"] == 0
                and r["metrics"]["status_total"] > 0
                and r["metrics"]["status_correct"] == r["metrics"]["status_total"]
                and r["metrics"]["value_correct"] == r["metrics"]["value_total"]
                and r["metrics"]["hallucination"] == 0
            ),
            "sample_count": len(sample_results),
            "noise_bandwidth": _noise_bandwidth(len(sample_results)),
        },
        "by_field": by_field,
        "by_pitfall": by_pitfall,
        "errors": errors,
    }


def _safe_div(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _noise_bandwidth(n: int) -> float:
    """√(p(1-p)/n) 取 p=0.5 的最大带宽，标注样本量级噪声。"""
    return round(0.5 / (n ** 0.5), 4) if n else 0.0
