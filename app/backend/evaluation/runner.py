"""Evaluation pipeline, atomic grounding diagnostics and report assembly."""
from __future__ import annotations

from ..errors import AppError
from ..services.copd_extraction.admission_contract import (
    map_qwen_fields_to_review_candidates,
    validate_qwen_payload,
)
from ..services.copd_extraction.prompts import build_admission_structured_fields_messages
from ..services.copd_extraction.quality_checks import apply_quality_checks
from ..services.copd_extraction.response_schemas import build_extraction_json_schema
from ..services.copd_extraction.verifier import FieldVerifier, apply_verdicts
from .metrics import (
    LONG_TEXT_FIELDS,
    METRIC_VERSION,
    compare_j_value,
    compare_value,
    grounding_result,
    j_judgement_fields,
    project_stool_urine_value,
    sentence_overlap_ratio,
    status_matches,
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
    """Run extraction → contract → evidence refill → quality → verification."""
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
        payload = llm_client.complete_json(
            user,
            system_prompt=system,
            json_schema=build_extraction_json_schema(schema),
        )
    except AppError as exc:
        return {"payload": {}, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    if check_contract:
        try:
            validate_qwen_payload(payload, schema)
        except AppError as exc:
            return {"payload": payload, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
    try:
        candidates = map_qwen_fields_to_review_candidates(
            payload, schema, evidence_units=evidence_units
        )
    except AppError as exc:
        if check_contract:
            return {"payload": payload, "candidates": [], "error": {"code": exc.code, "message": str(exc)}}
        return {"payload": payload, "candidates": [], "error": None}
    if apply_quality:
        candidates = apply_quality_checks(
            candidates, document_text, include_document_flags=False
        )
    if apply_verify:
        verifier = verifier or FieldVerifier(llm_client, append_reminder=append_reminder)
        verdicts = _verify_with_context(verifier, candidates, document_text, evidence_units)
        candidates = apply_verdicts(candidates, verdicts)
    return {"payload": payload, "candidates": candidates, "error": None}


def _verify_with_context(verifier, candidates, document_text, evidence_units):
    try:
        return verifier.verify(
            candidates,
            document_text,
            group_by="field",          # verifier.v3：字段级分组，单字段一请求
            evidence_units=evidence_units,
        )
    except TypeError as exc:
        if "evidence_units" not in str(exc) and "group_by" not in str(exc):
            raise
        return verifier.verify(candidates, document_text)


def _initial_metrics() -> dict:
    return {
        "value_correct": 0,
        "value_total": 0,
        "status_correct": 0,
        "status_total": 0,
        "literal_unlocated_count": 0,
        "unsupported_claim_candidate": 0,
        "unsupported_claim_candidate_count": 0,
        "confirmed_hallucination": 0,
        "confirmed_hallucination_count": 0,
        # Compatibility alias: it now means confirmed hallucinations only.
        "hallucination": 0,
        "extraction_fn": 0,
        "over_extraction_fp": 0,
        "contract_invalid": 0,
        "errors": [],
        "grounding_details": [],
    }


def _evidence_texts(candidate: dict) -> list[str]:
    evidence_items = [
        evidence for evidence in candidate.get("evidence") or []
        if isinstance(evidence, dict) and isinstance(evidence.get("text", ""), str)
    ]
    evidence_items.sort(
        key=lambda item: item.get("start_offset")
        if isinstance(item.get("start_offset"), int) else 10**12
    )
    return [evidence.get("text", "") for evidence in evidence_items]


def evaluate_sample(sample: dict, result: dict, schema: dict | None = None) -> dict:
    """Evaluate status/value and report three grounding layers.

    ``literal_unlocated_count`` is a diagnostic for a non-contiguous whole
    value.  ``unsupported_claim_candidate`` is intentionally not a veto.
    Only the deterministic, high-confidence over-extraction case (gold
    ``not_found`` + predicted ``found`` + absent from cited/full OCR) is counted
    as ``confirmed_hallucination``.
    """
    golden_by_key = {field["field_key"]: field for field in sample.get("golden", [])}
    candidates_by_key = {
        candidate["field_key"]: candidate
        for candidate in result.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("field_key")
    }
    ocr_text = sample.get("ocr_text") or ""
    j_fields = j_judgement_fields(schema) if isinstance(schema, dict) else set()
    metrics = _initial_metrics()
    field_totals: list[dict] = []
    if result.get("error"):
        metrics["contract_invalid"] = 1
        if result["error"].get("code") == "EVAL_LLM_FAILURE":
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": "",
                "kind": "eval_llm_failure",
                "message": result["error"].get("message", ""),
            })
        return {
            "metrics": metrics,
            "field_totals": field_totals,
            "pitfalls": sample.get("pitfalls", []),
        }

    for field_key, golden in golden_by_key.items():
        candidate = candidates_by_key.get(field_key)
        if candidate is None:
            continue
        golden_status = golden.get("status")
        predicted_status = candidate.get("status")
        if golden_status not in FIELD_STATUSES:
            continue
        metrics["status_total"] += 1
        if status_matches(golden_status, predicted_status):
            metrics["status_correct"] += 1
        else:
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "kind": "status_mismatch",
            })

        golden_value = golden.get("value", "") or ""
        predicted_value = candidate.get("value", "") or ""
        if golden_status == "found" and predicted_status == "not_found":
            metrics["extraction_fn"] += 1
        if golden_status == "not_found" and predicted_status == "found":
            metrics["over_extraction_fp"] += 1
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "kind": "value_not_empty_when_not_found",
            })

        # Value accuracy is defined over every gold ``found`` field.  Reserve
        # its denominator before any predicted-status shortcut so a predicted
        # not_found/uncertain cannot disappear from value metrics.
        value_item = None
        if golden_status == "found":
            metrics["value_total"] += 1
            value_item = {"field_key": field_key, "value_correct": 0, "value_total": 1}
            field_totals.append(value_item)

        if predicted_status != "found" or not predicted_value.strip():
            if golden_status == "found":
                metrics["errors"].append({
                    "case_id": sample.get("case_id"),
                    "field_key": field_key,
                    "kind": "value_mismatch",
                })
            continue

        # Ground every predicted found value, including gold not_found.  This
        # is the deliberate fix for the previous false-negative accounting.
        grounding = grounding_result(
            predicted_value,
            _evidence_texts(candidate),
            ocr_text,
            normal_allowed=field_key in j_fields,
            correction=candidate.get("ocr_correction"),
        )
        if grounding.get("literal_unlocated"):
            metrics["literal_unlocated_count"] += 1
        unsupported = grounding.get("unsupported_fragments") or []
        metrics["unsupported_claim_candidate"] += len(unsupported)
        metrics["unsupported_claim_candidate_count"] += len(unsupported)
        if unsupported:
            for fragment in unsupported:
                metrics["grounding_details"].append({
                    "case_id": sample.get("case_id"),
                    "field_key": field_key,
                    "level": "unsupported_claim_candidate",
                    "fragment": fragment,
                })
        if grounding.get("literal_unlocated"):
            metrics["grounding_details"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "level": "literal_unlocated",
                "status": grounding.get("status"),
            })

        # A gold not_found field that has a found value absent from both cited
        # evidence and full OCR is an unambiguous new-fact over-extraction.
        if golden_status == "not_found" and unsupported:
            metrics["confirmed_hallucination"] += 1
            metrics["confirmed_hallucination_count"] += 1
            metrics["hallucination"] += 1
            metrics["grounding_details"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "level": "confirmed_hallucination",
                "fragment": unsupported[0],
            })
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "kind": "confirmed_hallucination",
            })

        if golden_status == "not_found" or golden_status == "uncertain":
            continue
        if field_key in j_fields:
            # v2 非对称 J 比较：投影（大小便）→ 按金标内容分族 → exact/substring
            verdict = compare_j_value(golden_value, predicted_value, field_key)
        elif field_key in LONG_TEXT_FIELDS:
            verdict = "exact" if sentence_overlap_ratio(golden_value, predicted_value) >= 0.6 else "mismatch"
        else:
            # hpi_stool_status 走 T 分支，但同样支持大小便投影（金标与预测统一投影）
            verdict = compare_value(
                project_stool_urine_value(golden_value, field_key),
                project_stool_urine_value(predicted_value, field_key),
            )
        if verdict in ("exact", "substring"):
            metrics["value_correct"] += 1
            if value_item is not None:
                value_item["value_correct"] = 1
        else:
            metrics["errors"].append({
                "case_id": sample.get("case_id"),
                "field_key": field_key,
                "kind": "value_mismatch",
            })

    return {
        "metrics": metrics,
        "field_totals": field_totals,
        "pitfalls": sample.get("pitfalls", []),
    }


def build_report(sample_results: list[dict], meta: dict) -> dict:
    """Aggregate accuracy, grounding layers and status FN/FP counters.

    Report meta is always stamped with ``metric_version=evaluator.v2``
    (DESIGN §4.4); cross-version comparisons must not emit comparable deltas.
    """
    meta = dict(meta)
    meta["metric_version"] = METRIC_VERSION
    total = _initial_metrics()
    by_field: dict[str, dict] = {}
    by_pitfall: dict[str, dict] = {}
    errors: list[dict] = []
    grounding_details: list[dict] = []
    numeric_keys = [
        "value_correct", "value_total", "status_correct", "status_total",
        "literal_unlocated_count", "unsupported_claim_candidate",
        "unsupported_claim_candidate_count", "confirmed_hallucination",
        "confirmed_hallucination_count", "hallucination", "extraction_fn",
        "over_extraction_fp", "contract_invalid",
    ]
    for result in sample_results:
        metrics = result["metrics"]
        for key in numeric_keys:
            total[key] += metrics.get(key, 0)
        errors.extend(metrics.get("errors", []))
        grounding_details.extend(metrics.get("grounding_details", []))
        for field in result.get("field_totals", []):
            item = by_field.setdefault(field["field_key"], {"value_correct": 0, "value_total": 0})
            item["value_total"] += field["value_total"]
            item["value_correct"] += field["value_correct"]
        for pitfall in result.get("pitfalls", []):
            item = by_pitfall.setdefault(pitfall, {"value_correct": 0, "value_total": 0})
            item["value_total"] += metrics["value_total"]
            item["value_correct"] += metrics["value_correct"]

    task_success_count = sum(
        1 for result in sample_results
        if result["metrics"]["contract_invalid"] == 0
        and result["metrics"]["status_total"] > 0
        and result["metrics"]["status_correct"] == result["metrics"]["status_total"]
        and result["metrics"]["value_correct"] == result["metrics"]["value_total"]
    )
    report_metrics = {
        "status_accuracy": _safe_div(total["status_correct"], total["status_total"]),
        "value_accuracy": _safe_div(total["value_correct"], total["value_total"]),
        "literal_unlocated_count": total["literal_unlocated_count"],
        "unsupported_claim_candidate": total["unsupported_claim_candidate"],
        "unsupported_claim_candidate_count": total["unsupported_claim_candidate_count"],
        "confirmed_hallucination": total["confirmed_hallucination"],
        "confirmed_hallucination_count": total["confirmed_hallucination_count"],
        "hallucination_count": total["confirmed_hallucination"],
        "extraction_fn": total["extraction_fn"],
        "over_extraction_fp": total["over_extraction_fp"],
        "contract_invalid_count": total["contract_invalid"],
        "task_success_count": task_success_count,
        "sample_count": len(sample_results),
        "noise_bandwidth": _noise_bandwidth(len(sample_results)),
    }
    return {
        "meta": meta,
        "metrics": report_metrics,
        "by_field": by_field,
        "by_pitfall": by_pitfall,
        "errors": errors,
        "grounding_details": grounding_details,
    }


def _safe_div(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _noise_bandwidth(n: int) -> float:
    return round(0.5 / (n ** 0.5), 4) if n else 0.0
