"""Stable job entry for the Qwen batch engine adapter.

This wrapper intentionally exposes a narrow product contract around the
upstream batch script. It is importable for tests and callable as a script by
the backend adapter.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_PROCESS = ENGINE_ROOT / "upstream" / "scripts" / "process.py"


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


def run_job(
    *,
    job_dir: str,
    schema_path: str,
    normalize_only: bool = False,
    upstream_command: list[str] | None = None,
    timeout_seconds: int = 1800,
) -> int:
    """Run a prepared Qwen batch job and return a process-style exit code."""
    job_path = Path(job_dir)
    schema = Path(schema_path)
    job_path.mkdir(parents=True, exist_ok=True)

    if not schema.is_file():
        _write_error(job_path, "schema_missing", f"schema file not found: {schema}")
        return 2

    if normalize_only:
        return 0 if (job_path / "result.json").is_file() else 1

    command = upstream_command or [sys.executable, str(UPSTREAM_PROCESS), "--job-dir", str(job_path), "--schema", str(schema)]
    try:
        completed = subprocess.run(
            command,
            cwd=str(ENGINE_ROOT),
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
