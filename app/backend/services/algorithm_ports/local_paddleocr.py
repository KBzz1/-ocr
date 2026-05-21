import os
import re
import shutil
import subprocess
from pathlib import Path

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
        max_new_tokens: int | None = None,
        max_pixels: int | None = None,
        timeout_seconds: int = 1800,
    ):
        self._python_executable = python_executable
        self._script_path = script_path
        self._work_root = work_root
        self._cache_dir = cache_dir
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._max_pixels = max_pixels
        self._timeout_seconds = timeout_seconds

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
        ]
        if self._device:
            command.extend(["--device", self._device])
        if self._max_new_tokens is not None:
            command.extend(["--max-new-tokens", str(self._max_new_tokens)])
        if self._max_pixels is not None:
            command.extend(["--max-pixels", str(self._max_pixels)])
        env = os.environ.copy()
        env.setdefault("PADDLE_PDX_CACHE_HOME", self._cache_dir or str(work_dir / "paddlex_cache"))
        env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        completed = subprocess.run(
            command,
            cwd=str(work_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("本地 OCR runner 执行失败")
        if not output_file.is_file():
            raise RuntimeError("本地 OCR runner 未生成输出文件")

        output = output_file.read_text(encoding="utf-8")
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
