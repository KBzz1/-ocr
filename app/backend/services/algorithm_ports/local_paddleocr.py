import os
import re
import signal
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from .document_parsing import DocumentParsingPort


_PAGE_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$")


def parse_paddleocr_markdown(markdown: str, expected_names: set[str] | None = None) -> dict[str, str]:
    """Parse the batch runner output, keyed by the image filename heading."""
    pages: dict[str, list[str]] = {}
    current_name: str | None = None

    for line in markdown.splitlines():
        match = _PAGE_HEADING_RE.match(line)
        if match:
            matched_name = match.group(1).strip()
            if expected_names is None or matched_name in expected_names:
                current_name = matched_name
                pages[current_name] = []
                continue
        if current_name is None:
            continue
        if line.strip() == "---":
            current_name = None
            continue
        pages[current_name].append(line)

    return {name: "\n".join(lines).strip() for name, lines in pages.items()}


class LocalPaddleOCRDocumentPort(DocumentParsingPort):
    def __init__(
        self,
        python_executable: str,
        script_path: str,
        work_root: str,
        cache_dir: str | None = None,
        device: str | None = None,
        max_new_tokens: int = 1024,
        max_pixels: int | None = 501760,
        timeout_seconds: int = 180,
        event_logger: Callable[..., None] | None = None,
    ):
        self._python_executable = python_executable
        self._script_path = script_path
        self._work_root = work_root
        self._cache_dir = cache_dir
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._max_pixels = max_pixels
        self._timeout_seconds = timeout_seconds
        self._event_logger = event_logger

    def parse(self, input: dict) -> dict:
        if not os.path.isfile(self._script_path):
            raise RuntimeError(f"OCR runner 不存在: {self._script_path}")

        task_id = input["task_id"]
        work_dir = Path(self._work_root) / task_id
        input_dir = work_dir / "input"
        output_file = work_dir / "output" / "all_results.md"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        input_dir.mkdir(parents=True, exist_ok=True)

        page_files = self._copy_pages(input.get("pages", []), input_dir)
        command = [
            self._python_executable,
            self._script_path,
            "--input-dir",
            str(input_dir),
            "--output-file",
            str(output_file),
            "--max-new-tokens",
            str(self._max_new_tokens),
        ]
        if self._device:
            command.extend(["--device", self._device])
        if self._max_pixels is not None:
            command.extend(["--max-pixels", str(self._max_pixels)])
        env = os.environ.copy()
        env.setdefault("PADDLE_PDX_CACHE_HOME", self._cache_dir or str(work_dir / "paddlex_cache"))
        env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        started = time.monotonic()
        self._emit_event(
            "ocr_runner_started",
            task_id=task_id,
            page_count=len(page_files),
            timeout_seconds=self._timeout_seconds,
            work_dir=str(work_dir),
            command=_summarize_command(command),
            python_executable=self._python_executable,
            script_path=self._script_path,
            cache_dir=env["PADDLE_PDX_CACHE_HOME"],
            device=self._device,
            max_new_tokens=self._max_new_tokens,
            max_pixels=self._max_pixels,
            input_files=_input_file_diagnostics(page_files, input_dir),
        )
        try:
            completed = _run_with_process_group_timeout(
                command,
                cwd=str(work_dir),
                env=env,
                timeout=self._timeout_seconds,
                is_cancelled=input.get("is_cancelled"),
            )
        except _ProcessingCancelled as exc:
            self._emit_event(
                "ocr_runner_cancelled",
                task_id=task_id,
                work_dir=str(work_dir),
            )
            raise RuntimeError("本地 OCR runner 已取消") from exc
        except subprocess.TimeoutExpired as exc:
            self._emit_event(
                "ocr_runner_timeout",
                task_id=task_id,
                timeout_seconds=self._timeout_seconds,
                work_dir=str(work_dir),
                stdout_tail=_tail(exc.stdout),
                stderr_tail=_tail(exc.stderr),
            )
            raise RuntimeError(f"本地 OCR runner 执行超时: {self._timeout_seconds}s") from exc
        self._emit_runner_finished(task_id, started, completed, output_file)
        if completed.returncode != 0:
            self._emit_runner_failed(task_id, started, completed, output_file)
            detail = _summarize_process_failure(completed)
            raise RuntimeError(f"本地 OCR runner 执行失败: {detail}")
        if not output_file.is_file():
            raise RuntimeError("本地 OCR runner 未生成输出文件")

        output = output_file.read_text(encoding="utf-8")
        return self._document_result_from_markdown(output, page_files)

    def _document_result_from_markdown(self, output: str, page_files: list[dict]) -> dict:
        parsed = parse_paddleocr_markdown(output, expected_names={page["filename"] for page in page_files})
        result_pages = []
        merged_parts = []
        for page in page_files:
            text = parsed.get(page["filename"], "")
            if text:
                merged_parts.append(text)
                result_pages.append(
                    {
                        "page_id": page["page_id"],
                        "page_no": page["page_no"],
                        "status": "success",
                        "text": text,
                        "blocks": [],
                        "tables": [],
                        "source": "local_paddleocr_vl",
                    }
                )
            else:
                result_pages.append(
                    {
                        "page_id": page["page_id"],
                        "page_no": page["page_no"],
                        "status": "failed",
                        "text": "",
                        "blocks": [],
                        "tables": [],
                        "source": "local_paddleocr_vl",
                        "error_message": "OCR 输出缺少该页结果",
                    }
                )

        return {"pages": result_pages, "merged_text": "\n\n".join(merged_parts)}

    def _copy_pages(self, pages: list[dict], input_dir: Path) -> list[dict]:
        copied = []
        for page in sorted(pages, key=lambda item: item["page_no"]):
            source_path = page.get("processed_path")
            if not source_path or not os.path.isfile(source_path):
                raise RuntimeError("OCR 输入图片不存在")
            suffix = Path(source_path).suffix.lower() or ".jpg"
            filename = f"{page['page_no']:03d}_{page['page_id']}{suffix}"
            target_path = input_dir / filename
            shutil.copy2(source_path, target_path)
            copied.append(
                {
                    "page_id": page["page_id"],
                    "page_no": page["page_no"],
                    "filename": filename,
                }
            )
        return copied

    def _emit_event(self, event: str, **payload) -> None:
        if self._event_logger is not None:
            self._event_logger(event, **payload)

    def _emit_runner_finished(
        self,
        task_id: str,
        started: float,
        completed: subprocess.CompletedProcess,
        output_file: Path,
    ) -> None:
        self._emit_event(
            "ocr_runner_finished",
            task_id=task_id,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            exit_code=completed.returncode,
            output_exists=output_file.is_file(),
            output_bytes=output_file.stat().st_size if output_file.exists() else 0,
            stdout_tail=_tail(completed.stdout),
            stderr_tail=_tail(completed.stderr),
        )

    def _emit_runner_failed(
        self,
        task_id: str,
        started: float,
        completed: subprocess.CompletedProcess,
        output_file: Path,
    ) -> None:
        self._emit_event(
            "ocr_runner_failed",
            task_id=task_id,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            exit_code=completed.returncode,
            output_exists=output_file.is_file(),
            output_bytes=output_file.stat().st_size if output_file.exists() else 0,
            stdout_tail=_tail(completed.stdout),
            stderr_tail=_tail(completed.stderr),
        )


def _summarize_process_failure(completed: subprocess.CompletedProcess) -> str:
    output = (completed.stderr or completed.stdout or "").strip()
    if not output:
        return f"exit_code={completed.returncode}"
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    tail = "\n".join(lines[-8:])
    return f"exit_code={completed.returncode}; {tail[:1200]}"


def _input_file_diagnostics(page_files: list[dict], input_dir: Path) -> list[dict]:
    diagnostics = []
    for page in page_files:
        path = input_dir / page["filename"]
        diagnostics.append(
            {
                "page_id": page["page_id"],
                "page_no": page["page_no"],
                "filename": page["filename"],
                "bytes": path.stat().st_size if path.exists() else None,
                "exists": path.exists(),
            }
        )
    return diagnostics


class _ProcessingCancelled(Exception):
    """Internal signal for user-initiated processing cancellation."""


def _run_with_process_group_timeout(
    command: list[str],
    cwd: str,
    env: dict,
    timeout: int,
    is_cancelled: Callable[[], bool] | None = None,
) -> subprocess.CompletedProcess:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    while process.poll() is None:
        if is_cancelled is not None and is_cancelled():
            _kill_process_group(process)
            process.communicate()
            raise _ProcessingCancelled("OCR runner cancelled")
        if time.monotonic() >= deadline:
            _kill_process_group(process)
            stdout, stderr = process.communicate()
            exc = subprocess.TimeoutExpired(command, timeout)
            exc.stdout = stdout
            exc.stderr = stderr
            raise exc
        time.sleep(0.1)
    stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _join_timeout_output(original: str | bytes | None, after_kill: str | bytes | None) -> str | bytes | None:
    if not original:
        return after_kill
    if not after_kill:
        return original
    return original + after_kill


def _summarize_command(command: list[str]) -> str:
    return _tail(shlex.join(command), limit=600)


def _tail(value: str | bytes | None, limit: int = 1200) -> str:
    if not value:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if len(value) > limit:
        value = value[-limit:]
    return value.strip()
