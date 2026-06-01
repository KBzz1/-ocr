import concurrent.futures
import time
from pathlib import Path
from typing import Callable

from .document_parsing import DocumentParsingPort


class PaddleOCRVLMServerDocumentPort(DocumentParsingPort):
    def __init__(
        self,
        server_url: str,
        pipeline_factory: Callable[[str], object] | None = None,
        max_new_tokens: int = 1024,
        max_pixels: int | None = 501760,
        timeout_seconds: int = 240,
        event_logger: Callable[..., None] | None = None,
    ):
        self._server_url = server_url.rstrip("/")
        self._pipeline_factory = pipeline_factory or _default_pipeline_factory
        self._max_new_tokens = max_new_tokens
        self._max_pixels = max_pixels
        self._timeout_seconds = timeout_seconds
        self._event_logger = event_logger
        self._pipeline = None

    def parse(self, input: dict) -> dict:
        task_id = input["task_id"]
        pages = sorted(input.get("pages") or [], key=lambda page: page["page_no"])
        if not pages:
            raise RuntimeError("OCR 输入页面为空")

        for page in pages:
            processed_path = page.get("processed_path")
            if not processed_path or not Path(processed_path).is_file():
                raise RuntimeError("OCR 输入图片不存在")

        started = time.monotonic()
        self._emit_event(
            "ocr_runner_started",
            task_id=task_id,
            backend="vlm_server",
            page_count=len(pages),
            timeout_seconds=self._timeout_seconds * max(1, len(pages)),
            server_url=self._server_url,
            max_new_tokens=self._max_new_tokens,
            max_pixels=self._max_pixels,
            input_files=[_input_file_diagnostic(page) for page in pages],
        )

        pipeline = self._get_pipeline()
        result_pages = []
        merged_parts = []
        try:
            for page in pages:
                text = self._predict_page(pipeline, page["processed_path"])
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
                            "source": "paddleocr_vl_vllm_server",
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
                            "source": "paddleocr_vl_vllm_server",
                            "error_message": "OCR 输出缺少该页结果",
                        }
                    )
        except RuntimeError as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._emit_event(
                "ocr_runner_finished",
                task_id=task_id,
                backend="vlm_server",
                elapsed_ms=elapsed_ms,
                exit_code=-1,
                output_exists=False,
                output_bytes=0,
                reason=str(exc),
            )
            raise

        merged_text = "\n\n".join(merged_parts)
        self._emit_event(
            "ocr_runner_finished",
            task_id=task_id,
            backend="vlm_server",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            exit_code=0,
            output_exists=bool(merged_text),
            output_bytes=len(merged_text.encode("utf-8")),
        )
        return {"pages": result_pages, "merged_text": merged_text}

    def _get_pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._pipeline_factory(self._server_url)
        return self._pipeline

    def _predict_page(self, pipeline, image_path: str) -> str:
        predict_kwargs = {"max_new_tokens": self._max_new_tokens}
        if self._max_pixels is not None:
            predict_kwargs["max_pixels"] = self._max_pixels

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(pipeline.predict, input=image_path, **predict_kwargs)
            try:
                output = future.result(timeout=self._timeout_seconds)
            except concurrent.futures.TimeoutError as exc:
                raise RuntimeError(
                    f"OCR 服务超时（> {self._timeout_seconds} 秒）"
                ) from exc

        markdown_pages = []
        for item in output:
            markdown = getattr(item, "markdown", "")
            if isinstance(markdown, str) and markdown.strip():
                markdown_pages.append(markdown.strip())
        return "\n\n".join(markdown_pages).strip()

    def _emit_event(self, event: str, **payload) -> None:
        if self._event_logger is not None:
            self._event_logger(event, **payload)


def _default_pipeline_factory(server_url: str):
    from paddleocr import PaddleOCRVL

    return PaddleOCRVL(
        vl_rec_backend="vllm-server",
        vl_rec_server_url=server_url,
    )


def _input_file_diagnostic(page: dict) -> dict:
    path = Path(page["processed_path"])
    return {
        "page_id": page["page_id"],
        "page_no": page["page_no"],
        "filename": path.name,
        "bytes": path.stat().st_size if path.exists() else None,
        "exists": path.exists(),
    }
