"""Stable job entry for the Qwen batch engine adapter.

This wrapper intentionally exposes a narrow product contract around the
upstream batch script. It is importable for tests and callable as a script by
the backend adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


ENGINE_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_PROCESS = ENGINE_ROOT / "upstream" / "scripts" / "process.py"
UPSTREAM_CONFIG = ENGINE_ROOT / "upstream" / "config.yaml"


def _write_error(job_dir: Path, reason: str, message: str) -> None:
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "error.json").write_text(
        json.dumps(
            {"status": "failed", "reason": reason, "message": message},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_schema(schema_path: Path) -> dict:
    with schema_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    if not isinstance(loaded, dict):
        raise ValueError("schema must be a mapping")
    return loaded


def _iter_schema_fields(schema: dict) -> list[dict]:
    fields: list[dict] = []
    for group in schema.get("field_groups", []):
        if not isinstance(group, dict):
            continue
        for field in group.get("fields", []):
            if isinstance(field, dict):
                fields.append(field)
    return fields


def _value_at_path(data: dict, path: list[str]):
    cursor = data
    for part in path:
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _value_from_raw_response(raw_response: str | None, path: list[str]):
    if not raw_response or not path:
        return None
    label = path[-1]
    needle = json.dumps(label, ensure_ascii=False) + ":"
    start = raw_response.find(needle)
    if start < 0:
        return None
    value_start = start + len(needle)
    try:
        value, _ = json.JSONDecoder().raw_decode(raw_response[value_start:])
    except json.JSONDecodeError:
        return None
    return value


def _build_anchor_map(text: str) -> dict[str, str]:
    parts = re.split(r"([。！？\n，,；;.:：]+)", text)
    anchor_map: dict[str, str] = {}
    anchor_idx = 1
    current_chunk = ""
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        current_chunk += chunk + punct
        if current_chunk.strip():
            anchor_map[f"<s{anchor_idx}>"] = current_chunk.strip()
            anchor_idx += 1
            current_chunk = ""
        else:
            current_chunk = ""
    return anchor_map


def _restore_evidence_from_position(position, anchor_map: dict[str, str]) -> str | None:
    if not isinstance(position, list) or len(position) != 2:
        return None
    start_match = re.search(r"\d+", str(position[0]))
    end_match = re.search(r"\d+", str(position[1]))
    if not start_match or not end_match:
        return None
    start = int(start_match.group())
    end = int(end_match.group())
    if start > end:
        start, end = end, start
    chunks = [anchor_map[tag] for i in range(start, end + 1) if (tag := f"<s{i}>") in anchor_map]
    return "".join(chunks) if chunks else None


def _find_text_span(merged_text: str, evidence_text: str | None) -> tuple[int | None, int | None]:
    if not evidence_text:
        return None, None
    start = merged_text.find(evidence_text)
    if start < 0:
        return None, None
    return start, start + len(evidence_text)


def _normalize_review_fields(*, structured: dict, merged_text: str, schema: dict, raw_response: str | None = None) -> list[dict]:
    review_fields: list[dict] = []
    anchor_map = _build_anchor_map(merged_text)
    for field in _iter_schema_fields(schema):
        field_key = field.get("field_key", "")
        qwen_path = field.get("qwen_path", [])
        qwen_type = field.get("qwen_type", "T")
        node = _value_at_path(structured, qwen_path) if isinstance(qwen_path, list) else None
        if node is None and isinstance(qwen_path, list):
            node = _value_from_raw_response(raw_response, qwen_path)

        value = ""
        evidence_text = None
        qwen_status = None
        if isinstance(node, dict):
            is_judgement_node = qwen_type == "J" or "状态" in node or "s" in node
            if is_judgement_node:
                status = node.get("状态", node.get("s"))
                evidence_text = node.get("证据") or _restore_evidence_from_position(node.get("p"), anchor_map)
                if status == "正常":
                    value = "正常"
                    qwen_status = "normal"
                elif status == "异常":
                    value = "异常"
                    qwen_status = "abnormal"
                elif status in (0, "0"):
                    value = "正常"
                    qwen_status = "normal"
                elif status in (1, "1"):
                    value = "异常"
                    qwen_status = "abnormal"
                elif status == "未提及" or status in (2, "2") or status is None:
                    value = ""
                    qwen_status = "not_mentioned"
                else:
                    value = "不确定"
                    qwen_status = "uncertain"
            else:
                raw_value = node.get("值", node.get("v"))
                evidence_text = node.get("证据") or _restore_evidence_from_position(node.get("p"), anchor_map)
                value = raw_value if isinstance(raw_value, str) else ""
        elif isinstance(node, str):
            value = node

        extraction_status = "extracted" if value.strip() else "not_found"
        evidence = []
        evidence_lookup_text = evidence_text if isinstance(evidence_text, str) and evidence_text.strip() else value
        if evidence_lookup_text and extraction_status != "not_found":
            start, end = _find_text_span(merged_text, evidence_lookup_text)
            evidence_item = {
                "id": f"{field_key}-e1",
                "text": evidence_lookup_text,
            }
            if start is not None and end is not None:
                evidence_item["start_offset"] = start
                evidence_item["end_offset"] = end
            evidence.append(evidence_item)

        candidate = {
            "field_key": field_key,
            "original_value": value,
            "evidence": evidence,
            "extraction_status": extraction_status,
            "verification_status": "not_checked",
            "quality_flags": [],
            "ocr_correction": {
                "applied": False,
                "raw": "",
                "normalized": "",
                "reason": "",
            },
        }
        if qwen_status is not None:
            candidate["qwen_status"] = qwen_status
        if extraction_status == "extracted" and not evidence:
            candidate["attention_required"] = True
            candidate["attention_message"] = "字段已抽取但缺少可定位证据，请核对原文"
        review_fields.append(candidate)
    return review_fields


def normalize_upstream_output(*, job_dir: Path, schema_path: Path) -> None:
    """Convert upstream batch outputs into the backend stable result contract."""
    schema = _load_schema(schema_path)
    upstream_output = job_dir / "upstream_output"
    merged_text_paths = sorted(upstream_output.glob("*/merged_ocr.txt"))
    structured_paths = sorted(upstream_output.glob("*/merged_structured.json"))
    if not merged_text_paths:
        raise FileNotFoundError("upstream merged_ocr.txt not found")
    if not structured_paths:
        raise FileNotFoundError("upstream merged_structured.json not found")

    merged_text = merged_text_paths[0].read_text(encoding="utf-8")
    structured_raw = json.loads(structured_paths[0].read_text(encoding="utf-8"))
    if not isinstance(structured_raw, dict):
        raise ValueError("upstream merged_structured.json must be an object")
    raw_response = structured_raw.get("_raw_response") if isinstance(structured_raw.get("_raw_response"), str) else None
    if raw_response:
        try:
            structured_raw = json.loads(raw_response.strip())
        except json.JSONDecodeError:
            pass

    review_fields = _normalize_review_fields(
        structured=structured_raw,
        merged_text=merged_text,
        schema=schema,
        raw_response=raw_response,
    )
    result = {
        "job_id": job_dir.name,
        "status": "success",
        "engine": {"name": "qwen_batch_engine"},
        "schema_version": schema.get("version", ""),
        "document_type": schema.get("document_type", ""),
        "document_result": {
            "merged_text": merged_text,
            "pages": [],
            "upstream_output_dir": str(upstream_output),
        },
        "review_fields": review_fields,
        "warnings": [],
    }
    (job_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prepare_runtime_config(job_path: Path) -> Path:
    config = yaml.safe_load(UPSTREAM_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("upstream config must be a mapping")
    processing = config.setdefault("processing", {})
    if isinstance(processing, dict):
        processing["archive_processed"] = True
    config_path = job_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return config_path


def run_job(
    *,
    job_dir: str,
    schema_path: str,
    normalize_only: bool = False,
    upstream_command: list[str] | None = None,
    timeout_seconds: int = 1800,
) -> int:
    """Run a prepared Qwen batch job and return a process-style exit code."""
    job_path = Path(job_dir).resolve()
    schema = Path(schema_path).resolve()
    job_path.mkdir(parents=True, exist_ok=True)
    stale_error = job_path / "error.json"
    if stale_error.exists():
        stale_error.unlink()

    if not schema.is_file():
        _write_error(job_path, "schema_missing", f"schema file not found: {schema}")
        return 2

    if normalize_only:
        try:
            normalize_upstream_output(job_dir=job_path, schema_path=schema)
            return 0
        except Exception as exc:
            _write_error(job_path, "normalize_failed", f"{type(exc).__name__}: {exc}")
            return 1

    upstream_output = job_path / "upstream_output"
    if upstream_output.exists():
        shutil.rmtree(upstream_output)
    upstream_output.mkdir(parents=True, exist_ok=True)
    try:
        config_path = _prepare_runtime_config(job_path)
    except Exception as exc:
        _write_error(job_path, "config_prepare_failed", f"{type(exc).__name__}: {exc}")
        return 1

    command = upstream_command or [sys.executable, str(UPSTREAM_PROCESS)]
    env = os.environ.copy()
    env.setdefault("VLLM_SERVER_URL", "http://127.0.0.1:8082/v1")
    env.setdefault("MAX_NUM_SEQS", "1")
    env["QWEN_BATCH_WORKSPACE_DIR"] = str(job_path)
    env["QWEN_BATCH_INPUT_DIR"] = str(job_path / "input")
    env["QWEN_BATCH_OUTPUT_DIR"] = str(upstream_output)
    env["QWEN_BATCH_CONFIG_PATH"] = str(config_path)
    try:
        completed = subprocess.run(
            command,
            cwd=str(ENGINE_ROOT),
            env=env,
            timeout=timeout_seconds,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.TimeoutExpired:
        _write_error(job_path, "runner_timeout", f"runner exceeded {timeout_seconds} seconds")
        return 124
    except Exception as exc:
        _write_error(job_path, "runner_exception", f"{type(exc).__name__}: {exc}")
        return 1

    if completed.returncode != 0:
        _write_error(job_path, "runner_failed", completed.stderr[-1000:] or completed.stdout[-1000:])
        return int(completed.returncode)
    try:
        normalize_upstream_output(job_dir=job_path, schema_path=schema)
    except Exception as exc:
        _write_error(job_path, "normalize_failed", f"{type(exc).__name__}: {exc}")
        return 1
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Qwen batch engine job")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--schema-path", "--schema", dest="schema_path", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    return run_job(
        job_dir=args.job_dir,
        schema_path=args.schema_path,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
