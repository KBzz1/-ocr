"""评估 CLI：跑金标样本、出报告、支持消融与基线对比。

用法见模块 docstring 与 docs/superpowers/plans/2026-08-01-evaluation-harness-implementation-plan.md
Task 4。默认管线与 COPDAdmissionQwenFieldPort.extract 一致；消融参数
--no-quality-flags / --no-contract / --no-verifier 走 run_pipeline 变体。

真实 LLM 客户端（QwenVLLMClient.complete_json）在服务不可用/超时时抛
RuntimeError 等非 AppError 异常，会穿透 run_pipeline 的内部捕获；本 CLI
的样本循环对每个样本兜底：任何未捕获异常记为 EVAL_LLM_FAILURE error，
evaluate_sample 把它计为 contract_invalid，评估继续下一个样本。
"""
import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
from ..services.copd_extraction.llm_client import OpenAICompatibleJsonClient
from ..services.copd_extraction.prompts import ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION
from ..services.schema_loader import load_schema
from .feedback import load_review_golden
from .runner import build_report, evaluate_sample, run_pipeline

# 批处理 schema（含 qwen_type/review_control 注解），用于给 v1 评估 schema
# 补同名 J 字段注解（见 _merge_j_annotations）。
_BATCH_SCHEMA_PATH = str(
    Path(__file__).resolve().parents[3]
    / "app" / "config" / "schemas" / "qwen_batch_admission_record.v2.yaml"
)


def _merge_j_annotations(schema: dict, batch_schema: dict) -> dict:
    """把批处理 schema 中同名字段的 J 注解合并进评估 schema（仅评估路径）。

    v1 评估 schema 无 qwen_type/review_control 注解，j_judgement_fields 对它会
    返回空集，J 型"正常族"归一一度是死代码。本函数只把两 schema 共有的字段名
    上、且批处理侧标注为 J（qwen_type=J 或 review_control=judgement）的注解
    复制到 v1 同名字段；v1 独有字段不动，批处理独有字段不引入。
    """
    j_fields: dict[str, dict] = {}
    for group in batch_schema.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            if field.get("qwen_type") == "J" or field.get("review_control") == "judgement":
                j_fields[field.get("field_key")] = field
    merged = copy.deepcopy(schema)
    for group in merged.get("field_groups", []) or []:
        for field in group.get("fields", []) or []:
            jf = j_fields.get(field.get("field_key"))
            if jf:
                field["qwen_type"] = jf["qwen_type"]
                field["review_control"] = jf["review_control"]
    return merged


def build_llm_client(args) -> OpenAICompatibleJsonClient:
    qwen_client = QwenVLLMClient(
        base_url=args.base_url,
        model=args.model,
        api_key="not-needed",
        timeout_seconds=360,
    )
    return OpenAICompatibleJsonClient(qwen_client, max_tokens=args.max_tokens, temperature=args.temperature)


def load_golden_samples(golden_dir: Path) -> list[dict]:
    samples = []
    for path in sorted(golden_dir.glob("case_*.json")):
        samples.append(json.loads(path.read_text(encoding="utf-8")))
    return samples


def _input_for(sample: dict, schema: dict) -> dict:
    return {
        "schema": schema,
        "document_result": {"merged_text": sample.get("ocr_text") or ""},
        "evidence_units": [],
    }


def _run_pipeline_with_fallback(sample: dict, schema: dict, llm_client, args) -> dict:
    """跑单样本抽取；非 AppError 异常兜底为 EVAL_LLM_FAILURE error，不中断循环。

    run_pipeline 内部只捕获 AppError；真实 QwenVLLMClient.complete_json 在
    服务不可用/超时时抛 RuntimeError 等异常会穿透，必须在这里兜底为样本
    error（evaluate_sample 计为 contract_invalid），循环继续下一个样本。
    """
    try:
        return run_pipeline(
            _input_for(sample, schema),
            llm_client,
            check_contract=not args.no_contract,
            apply_quality=not args.no_quality_flags,
            apply_verify=not args.no_verifier,
        )
    except Exception as exc:  # noqa: BLE001 — LLM/HTTP 异常类型不可枚举，兜底为样本 error
        return {"payload": {}, "candidates": [], "error": {"code": "EVAL_LLM_FAILURE", "message": str(exc)}}


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="COPD 病历抽取评估")
    parser.add_argument("--golden-dir", default="data/evaluation/golden")
    parser.add_argument("--schema", required=True, help="admission_record_structured_fields.v1.yaml 路径")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--report-dir", default="data/evaluation/reports")
    parser.add_argument("--golden-review", default=None,
                        help="review 金标活资产目录(如 data/evaluation/golden_review)，单独统计修正字段子集")
    parser.add_argument("--no-quality-flags", action="store_true")
    parser.add_argument("--no-contract", action="store_true")
    parser.add_argument("--no-verifier", action="store_true")
    parser.add_argument("--compare", default=None, help="基线报告 JSON 路径，输出指标 diff")
    args = parser.parse_args(argv)

    schema = load_schema(args.schema)
    try:
        batch_schema = load_schema(_BATCH_SCHEMA_PATH)
    except Exception as exc:  # noqa: BLE001 — 批处理 schema 缺失时降级为不合并，评估仍可跑
        print(f"警告: 加载批处理 schema 失败({_BATCH_SCHEMA_PATH})，跳过 J 注解合并: {exc}", file=sys.stderr)
        batch_schema = None
    if batch_schema:
        schema = _merge_j_annotations(schema, batch_schema)
    samples = load_golden_samples(Path(args.golden_dir))
    if not samples:
        print(f"未找到金标样本: {args.golden_dir}", file=sys.stderr)
        raise SystemExit(1)

    llm_client = build_llm_client(args)
    sample_results = []
    for sample in samples:
        result = _run_pipeline_with_fallback(sample, schema, llm_client, args)
        sample_results.append(evaluate_sample(sample, result, schema))

    meta = {
        "model": args.model,
        "prompt_version": ADMISSION_STRUCTURED_FIELDS_PROMPT_VERSION,
        "schema_version": schema.get("version", ""),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "ablation": {
            "quality_flags": not args.no_quality_flags,
            "contract": not args.no_contract,
            "verifier": not args.no_verifier,
        },
        "sample_count": len(samples),
    }
    report = build_report(sample_results, meta)

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{stamp}_{meta['prompt_version']}_{args.model.replace('/', '_')}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _print_console_summary(report)
    if args.golden_review:
        review_samples = load_review_golden(Path(args.golden_review))
        if review_samples:
            review_results = []
            for sample in review_samples:
                result = _run_pipeline_with_fallback(sample, schema, llm_client, args)
                review_results.append(evaluate_sample(sample, result, schema))
            review_meta = dict(meta, source="review", sample_count=len(review_samples))
            review_report = build_report(review_results, review_meta)
            review_path = report_dir / f"{stamp}_{meta['prompt_version']}_{args.model.replace('/', '_')}_review.json"
            review_path.write_text(json.dumps(review_report, ensure_ascii=False, indent=2), encoding="utf-8")
            _print_review_summary(review_report)
            print(f"review 报告已写入: {review_path}")
        else:
            print(f"未找到 review 活资产: {args.golden_review}", file=sys.stderr)
    if args.compare:
        _print_compare(Path(args.compare), report)
    print(f"\n报告已写入: {report_path}")
    return report_path


def _print_console_summary(report: dict) -> None:
    m = report["metrics"]
    print("=" * 46)
    print(f"评估报告  {report['meta']['model']} / {report['meta']['prompt_version']}")
    print("=" * 46)
    print(f"样本数          : {m['sample_count']}   (噪声带宽 ±{m['noise_bandwidth']})")
    print(f"status 准确率   : {m['status_accuracy']:.2%}")
    print(f"value 准确率    : {m['value_accuracy']:.2%}")
    print(f"幻觉数(veto)    : {m['hallucination_count']}")
    print(f"契约非法数      : {m['contract_invalid_count']}")
    print(f"任务级成功      : {m['task_success_count']}/{m['sample_count']}")
    if report["by_field"]:
        worst = sorted(report["by_field"].items(), key=lambda kv: kv[1]["value_total"] - kv[1]["value_correct"], reverse=True)[:5]
        print("\n最差字段 top5:")
        for key, d in worst:
            print(f"  {key}: {d['value_correct']}/{d['value_total']}")


def _print_review_summary(review_report: dict) -> None:
    """控制台打印 review 子集统计（修正字段错误率，与 manual 分开）。"""
    value_total = sum(d["value_total"] for d in review_report["by_field"].values())
    value_correct = sum(d["value_correct"] for d in review_report["by_field"].values())
    error_rate = (value_total - value_correct) / value_total if value_total else 0.0
    print("\n" + "=" * 46)
    print(f"review 子集  {review_report['meta']['model']} / {review_report['meta']['prompt_version']}")
    print("=" * 46)
    print(f"样本数          : {review_report['metrics']['sample_count']}")
    print(f"修正字段总数    : {value_total}")
    print(f"命中修正值      : {value_correct}")
    print(f"review 修正字段错误率: {error_rate:.2%}")


def _print_compare(baseline_path: Path, report: dict) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    bm, nm = baseline["metrics"], report["metrics"]
    print("\n=== 与基线对比 ===")
    print(f"基线: {baseline_path.name}")
    for k in ("status_accuracy", "value_accuracy"):
        diff = nm[k] - bm[k]
        print(f"  {k}: {bm[k]:.2%} → {nm[k]:.2%} ({diff:+.2%})")
    for k in ("hallucination_count", "contract_invalid_count"):
        print(f"  {k}: {bm[k]} → {nm[k]} ({nm[k] - bm[k]:+d})")
    b_errs = {(e['case_id'], e['field_key']) for e in baseline.get("errors", [])}
    n_errs = {(e['case_id'], e['field_key']) for e in report.get("errors", [])}
    new_errs = sorted(n_errs - b_errs)
    fixed = sorted(b_errs - n_errs)
    print(f"  新增错误: {len(new_errs)}  已修复: {len(fixed)}")
    for e in new_errs:
        print(f"    + {e}")


if __name__ == "__main__":
    main()
