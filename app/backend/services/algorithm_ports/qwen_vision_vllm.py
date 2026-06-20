"""Qwen Vision vLLM 文档解析端口。

按页调用同一个本地 qwen-vision-vllm-server 做图片 OCR；服务契约与
`qwen_vllm_client.QwenVLLMClient` 对齐，事件 payload 仅含诊断字段，不含
OCR 文本、图片 base64、prompt 或模型完整输出。
"""
import logging
import time
from pathlib import Path
from typing import Callable

from .document_parsing import DocumentParsingPort
from .qwen_vllm_client import QwenVLLMClient

logger = logging.getLogger(__name__)


_OCR_SYSTEM_PROMPT = (
    "你是一个医疗文档 OCR 识别助手。\n"
    "请只输出图片里的病历正文文本；不输出解释、寒暄、JSON、Markdown 代码块或思考过程。\n"
    "保持当前页可见正文的自然阅读顺序；不纠错、不改写、不总结、不补全、不重排。\n"
    "当前页末尾未完句保持原样，不补标点、不补后文。\n"
    "可以忽略页眉、页脚、页码、打印时间、医院页眉页脚、医生签名、手签等非病历正文干扰；"
    "但禁止纠正文书正文、做标题字符串替换、用医学知识补写诊断、症状、检查或治疗。\n"
    "不要把结构化字段名反向写进 OCR 文本。"
)


class QwenVisionVLLMDocumentPort(DocumentParsingPort):
    def __init__(
        self,
        client: QwenVLLMClient,
        model: str,
        server_url: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout_seconds: int = 240,
        event_logger: Callable[..., None] | None = None,
    ):
        self._client = client
        self._model = model
        self._server_url = server_url
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout_seconds = timeout_seconds
        self._event_logger = event_logger

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
            "ocr_vlm_started",
            task_id=task_id,
            backend="qwen_vision_vllm",
            server_url=self._server_url,
            model=self._model,
            page_count=len(pages),
            timeout_seconds=self._timeout_seconds,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            top_p=1.0,
            input_files=[_input_file_diagnostic(page) for page in pages],
        )

        result_pages = []
        merged_parts = []
        try:
            for page in pages:
                text = self._client.complete_text_from_image(
                    image_path=page["processed_path"],
                    system_prompt=_OCR_SYSTEM_PROMPT,
                    user_prompt="请识别这张图片里的病历正文。",
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
                if text and text.strip():
                    merged_parts.append(text)
                    result_pages.append({
                        "page_id": page["page_id"],
                        "page_no": page["page_no"],
                        "status": "success",
                        "text": text,
                        "blocks": [],
                        "tables": [],
                        "source": "qwen_vision_vllm",
                    })
                else:
                    result_pages.append({
                        "page_id": page["page_id"],
                        "page_no": page["page_no"],
                        "status": "failed",
                        "text": "",
                        "blocks": [],
                        "tables": [],
                        "source": "qwen_vision_vllm",
                        "error_message": "OCR 输出缺少该页结果",
                    })
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            self._emit_event(
                "ocr_vlm_finished",
                task_id=task_id,
                backend="qwen_vision_vllm",
                elapsed_ms=elapsed_ms,
                exit_code=-1,
                output_exists=False,
                output_bytes=0,
                failed_page_count=len(pages),
                reason=type(exc).__name__,
            )
            raise

        merged_text = "\n\n".join(merged_parts)
        failed_page_count = sum(1 for p in result_pages if p["status"] == "failed")
        self._emit_event(
            "ocr_vlm_finished",
            task_id=task_id,
            backend="qwen_vision_vllm",
            elapsed_ms=int((time.monotonic() - started) * 1000),
            exit_code=0,
            output_exists=bool(merged_text),
            output_bytes=len(merged_text.encode("utf-8")),
            failed_page_count=failed_page_count,
        )
        return {"pages": result_pages, "merged_text": merged_text}

    def _emit_event(self, event: str, **payload) -> None:
        if self._event_logger is not None:
            self._event_logger(event, **payload)


def _input_file_diagnostic(page: dict) -> dict:
    path = Path(page["processed_path"])
    return {
        "page_id": page["page_id"],
        "page_no": page["page_no"],
        "filename": path.name,
        "bytes": path.stat().st_size if path.exists() else None,
        "exists": path.exists(),
    }
