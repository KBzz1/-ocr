"""Qwen batch engine adapter port.

Provides ``QwenBatchAlgorithmPort`` -- the backend-side port that creates
job directories, writes manifests, invokes the stable ``run_job`` entry
point and parses the resulting ``result.json`` (or ``error.json``).
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default runner - calls run_job directly (not via subprocess).
# The test suite injects a fake runner.
# ---------------------------------------------------------------------------

ENGINE_ROOT = Path(__file__).resolve().parents[6] / "algorithms" / "qwen_batch_engine"
VERSION_PATH = ENGINE_ROOT / "VERSION"


def _default_runner(job_dir: str, schema_path: str, timeout_seconds: int) -> int:
    """Invoke ``run_job`` from the Qwen batch engine adapter directly."""
    from algorithms.qwen_batch_engine.adapter.run_job import run_job

    return run_job(
        job_dir=job_dir,
        schema_path=schema_path,
        normalize_only=False,
        upstream_command=None,
        timeout_seconds=timeout_seconds,
    )


def read_upstream_commit_from_version() -> str:
    """Read the ``upstream_commit`` field from ``algorithms/qwen_batch_engine/VERSION``."""
    if not VERSION_PATH.is_file():
        logger.warning("VERSION file not found at %s", VERSION_PATH)
        return ""
    raw = VERSION_PATH.read_text(encoding="utf-8").strip()
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("upstream_commit="):
            return line.split("=", 1)[1].strip()
    logger.warning("upstream_commit not found in VERSION file")
    return ""


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class QwenBatchAlgorithmPort:
    """Backend port that creates a Qwen batch job and reads its result.

    Parameters
    ----------
    job_root:
        Base directory under which ``{task_id}/input/`` and
        ``{task_id}/output/`` are created.
    schema_path:
        Path to the YAML field schema file passed through to the runner.
    runner:
        Callable ``(job_dir, schema_path, timeout_seconds) -> int``.
        Defaults to ``_default_runner`` which calls ``run_job`` directly.
    timeout_seconds:
        Hard timeout forwarded to the runner.
    engine_root:
        Root of the qwen_batch_engine tree (used for VERSION reading).
        Exposed for test injection but currently unused by the adapter
        directly; the runner uses its own ``ENGINE_ROOT``.
    """

    def __init__(
        self,
        job_root: str,
        schema_path: str,
        runner: Optional[Callable[[str, str, int], int]] = None,
        timeout_seconds: int = 1800,
        engine_root: Optional[str] = None,
    ):
        self._job_root = Path(job_root)
        self._schema_path = schema_path
        self._runner = runner if runner is not None else _default_runner
        self._timeout_seconds = timeout_seconds
        self._engine_root = engine_root  # reserved for future use

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: dict) -> dict:
        """Execute a Qwen batch job for *task*.

        *task* must contain::

            {
                "task_id": str,
                "images": [
                    {"page_id": str, "page_no": int, "original_image_path": str},
                    ...
                ],
                "schema_version": str,  # e.g. "qwen_batch_admission_record.v1"
            }

        Returns a dict with ``status`` (``"success"`` or ``"failed"``) and
        the normalised ``document_result`` / ``review_fields`` on success,
        or an ``error`` block on failure.
        """
        task_id = task["task_id"]
        job_dir = self._job_root / task_id
        try:
            return self._do_run(task, job_dir, task_id)
        except Exception as exc:
            logger.exception("task=%s QwenBatchAlgorithmPort unexpected error", task_id)
            return {
                "status": "failed",
                "error": {
                    "reason": "adapter_exception",
                    "message": f"{type(exc).__name__}: {exc}",
                },
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_run(self, task: dict, job_dir: Path, task_id: str) -> dict:
        # 1. Prepare directories
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 2. Copy images sorted by page_no, preserving file extension
        images = sorted(task.get("images", []), key=lambda img: img.get("page_no", 0))
        input_files: list[dict] = []
        for idx, img in enumerate(images, start=1):
            src = Path(img["original_image_path"])
            ext = src.suffix or ".jpg"
            filename = f"page_{idx:03d}{ext}"
            dst = input_dir / filename
            shutil.copy2(str(src), str(dst))
            input_files.append(
                {
                    "page_id": img.get("page_id", ""),
                    "page_no": img.get("page_no", idx),
                    "filename": filename,
                    "original_path": str(src),
                }
            )

        # 3. Write manifest.json
        upstream_commit = read_upstream_commit_from_version()
        manifest = {
            "job_id": task_id,
            "task_id": task_id,
            "schema_version": task.get("schema_version", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "input_files": input_files,
            "engine": {
                "name": "qwen_batch_engine",
                "upstream_commit": upstream_commit,
            },
        }
        manifest_path = job_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 4. Call runner
        exit_code = self._runner(
            str(job_dir), self._schema_path, self._timeout_seconds
        )

        # 5. If runner returned non-zero, read error.json
        if exit_code != 0:
            error_payload = self._read_json(job_dir / "error.json")
            if isinstance(error_payload, dict):
                return {
                    "status": "failed",
                    "error": error_payload,
                }
            return {
                "status": "failed",
                "error": {
                    "reason": "runner_failed",
                    "message": f"runner exited with code {exit_code}",
                },
            }

        # 6. Read result.json
        result = self._read_json(job_dir / "result.json")
        if result is None:
            return {
                "status": "failed",
                "error": {"reason": "missing_result_json"},
            }
        if not isinstance(result, dict):
            return {
                "status": "failed",
                "error": {"reason": "invalid_result_json"},
            }
        return result

    @staticmethod
    def _read_json(path: Path) -> Any:
        """Safely read and parse a JSON file; return *None* on any error."""
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError, OSError):
            return None
