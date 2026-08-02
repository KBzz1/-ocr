"""验证器校准工具：导出复核 verdict → 裁定模板 → Cohen's kappa。

裁定执行方式：裁定由 Claude 子 agent 模拟人工（逐条判定"该字段是否应被
标记可疑"），写入裁定文件后 compute_kappa。kappa ≥ 0.7 才允许复核器上岗。
"""
import json
from pathlib import Path


def cohen_kappa(table: list[list[int]]) -> float:
    """2×2 一致表 Cohen's kappa。行=复核器判定，列=人工裁定。"""
    if len(table) != 2 or any(len(row) != 2 for row in table):
        raise ValueError("kappa 需要 2×2 一致表")
    n = sum(sum(row) for row in table)
    if n == 0:
        return 0.0
    p0 = (table[0][0] + table[1][1]) / n
    row_totals = [sum(r) for r in table]
    col_totals = [table[0][c] + table[1][c] for c in range(2)]
    pe = sum(row_totals[i] * col_totals[i] for i in range(2)) / (n * n)
    if pe == 1.0:
        return 0.0
    return round((p0 - pe) / (1 - pe), 4)


def export_verdicts_file(verdicts: list[dict], out_path: Path) -> None:
    """导出裁定模板：每条含 case_id/field_key/verdict/原因/声称值/证据片段。"""
    items = []
    for v in verdicts:
        items.append({
            "case_id": v.get("case_id"),
            "field_key": v.get("field_key"),
            "verdict": v.get("verdict"),
            "reason_code": v.get("reason_code"),
            "comment": v.get("comment"),
            "value": v.get("value"),
            "evidence_text": (v.get("evidence_text") or "")[:200],
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_adjudications(path: Path) -> dict[tuple[str, str], bool]:
    """加载裁定文件 → {(case_id, field_key): should_flag}。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for item in data.get("adjudications", []):
        result[(item["case_id"], item["field_key"])] = bool(item["should_flag"])
    return result


def compute_kappa(
    verdicts: list[dict], adjudications: dict[tuple[str, str], bool]
) -> dict:
    """verdict 二值化（suspicious/fail=应标侧）后与裁定比对，返回 kappa/n/table。"""
    table = [[0, 0], [0, 0]]  # [复核pass][复核suspicious/fail] × [裁定不应标][裁定应标]
    n = 0
    for v in verdicts:
        key = (v.get("case_id"), v.get("field_key"))
        if key not in adjudications:
            continue
        n += 1
        verifier_flagged = v.get("verdict") in ("suspicious", "fail")
        should_flag = adjudications[key]
        table[1 if verifier_flagged else 0][1 if should_flag else 0] += 1
    return {"kappa": cohen_kappa(table) if n else 0.0, "n": n, "table": table}


def main(argv: list[str] | None = None) -> None:
    import argparse
    import sys
    from datetime import datetime, timezone

    from ..services.algorithm_ports.qwen_vllm_client import QwenVLLMClient
    from ..services.copd_extraction.llm_client import OpenAICompatibleJsonClient
    from ..services.schema_loader import load_schema
    from .run_eval import _input_for, load_golden_samples
    from .runner import run_pipeline

    parser = argparse.ArgumentParser(description="验证器校准")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="跑抽取+复核，导出裁定模板")
    p_export.add_argument("--golden-dir", default="data/evaluation/golden")
    p_export.add_argument("--schema", required=True)
    p_export.add_argument("--base-url", default="http://localhost:8000/v1")
    p_export.add_argument("--model", required=True)
    p_export.add_argument("--max-tokens", type=int, default=8192)
    p_export.add_argument("--out", required=True, help="裁定模板 JSON 路径")
    p_export.add_argument("--inject-evidence", action="store_true",
                          help="复核前按字段值定位回填证据 units（评估口径修正：复核器吃字段证据=生产形态）")
    p_export.add_argument("--group-by", choices=["field", "section"], default=None,
                          help="复核器分组形态（需与 --inject-evidence 同用；None=一次全量）")

    p_kappa = sub.add_parser("kappa", help="裁定文件 → kappa")
    p_kappa.add_argument("--verdicts", required=True)
    p_kappa.add_argument("--adjudications", required=True)

    args = parser.parse_args(argv)
    if args.command == "export" and args.group_by and not args.inject_evidence:
        parser.error("--group-by 需要同时指定 --inject-evidence（分组模式以字段证据为输入）")
    if args.command == "kappa":
        verdicts = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))["items"]
        result = compute_kappa(verdicts, load_adjudications(Path(args.adjudications)))
        print(f"kappa={result['kappa']} n={result['n']} table={result['table']}")
        return
    if args.command == "export":
        schema = load_schema(args.schema)
        samples = load_golden_samples(Path(args.golden_dir))
        qwen = QwenVLLMClient(base_url=args.base_url, model=args.model, api_key="not-needed", timeout_seconds=360)
        llm_client = OpenAICompatibleJsonClient(qwen, max_tokens=args.max_tokens, temperature=0.0)
        from ..services.copd_extraction.verifier import FieldVerifier
        from .chunked_review import inject_field_evidence, units_from_ocr_text
        verifier = FieldVerifier(llm_client)
        items = []
        for sample in samples:
            result = run_pipeline(_input_for(sample, schema), llm_client, verifier=verifier)
            if result.get("error"):
                continue
            candidates = result["candidates"]
            if args.inject_evidence:
                candidates = inject_field_evidence(
                    candidates, units_from_ocr_text(sample.get("ocr_text") or "")
                )
            by_key = {c["field_key"]: c for c in candidates}
            for v in verifier.verify(candidates, sample.get("ocr_text") or "", group_by=args.group_by):
                field = by_key.get(v["field_key"]) or {}
                items.append({
                    "case_id": sample.get("case_id"),
                    "field_key": v["field_key"],
                    "verdict": v["verdict"],
                    "reason_code": v["reason_code"],
                    "comment": v["comment"],
                    "value": field.get("value", ""),
                    "evidence_text": "；".join(
                        (e.get("text") or "") for e in (field.get("evidence") or [])[:3]
                    ),
                })
        export_verdicts_file(items, Path(args.out))
        print(f"已导出 {len(items)} 条 verdict 到 {args.out}")


if __name__ == "__main__":
    main()
