import time
from pathlib import Path

import pytest

from app.backend.services.algorithm_ports.paddleocr_vlm_server import (
    PaddleOCRVLMServerDocumentPort,
)


class FakeResult:
    def __init__(self, markdown):
        self.markdown = markdown


class FakePipeline:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def predict(self, input, **kwargs):
        self.calls.append({"input": input, **kwargs})
        if not self.outputs:
            return []
        return [FakeResult(self.outputs.pop(0))]


def test_vlm_server_port_parses_pages_in_order(tmp_path):
    image1 = tmp_path / "page1.jpg"
    image2 = tmp_path / "page2.jpg"
    image1.write_bytes(b"1")
    image2.write_bytes(b"2")
    pipeline = FakePipeline(["第一页正文", "第二页正文"])
    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: pipeline,
        max_new_tokens=1024,
        max_pixels=501760,
        timeout_seconds=240,
    )

    result = port.parse(
        {
            "task_id": "task-001",
            "pages": [
                {"page_id": "p2", "page_no": 2, "processed_path": str(image2)},
                {"page_id": "p1", "page_no": 1, "processed_path": str(image1)},
            ],
        }
    )

    assert result["merged_text"] == "第一页正文\n\n第二页正文"
    assert [page["page_id"] for page in result["pages"]] == ["p1", "p2"]
    assert [page["page_no"] for page in result["pages"]] == [1, 2]
    assert all(page["status"] == "success" for page in result["pages"])
    assert all(page["source"] == "paddleocr_vl_vllm_server" for page in result["pages"])
    assert pipeline.calls == [
        {"input": str(image1), "max_new_tokens": 1024, "max_pixels": 501760},
        {"input": str(image2), "max_new_tokens": 1024, "max_pixels": 501760},
    ]


def test_vlm_server_port_marks_missing_page_output_failed(tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"1")
    pipeline = FakePipeline([""])
    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: pipeline,
    )

    result = port.parse(
        {"task_id": "task-001", "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(image)}]}
    )

    assert result["merged_text"] == ""
    assert result["pages"][0]["status"] == "failed"
    assert result["pages"][0]["error_message"] == "OCR 输出缺少该页结果"


def test_vlm_server_port_rejects_missing_input_image(tmp_path):
    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: FakePipeline([]),
    )

    with pytest.raises(RuntimeError, match="OCR 输入图片不存在"):
        port.parse(
            {
                "task_id": "task-001",
                "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(tmp_path / "missing.jpg")}],
            }
        )


def test_vlm_server_port_emits_diagnostic_events(tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"1")
    events = []
    pipeline = FakePipeline(["正文"])
    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: pipeline,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    port.parse(
        {"task_id": "task-001", "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(image)}]}
    )

    assert [event[0] for event in events] == ["ocr_runner_started", "ocr_runner_finished"]
    assert events[0][1]["backend"] == "vlm_server"
    assert events[0][1]["server_url"] == "http://paddleocr-vlm-server:8080/v1"
    assert events[1][1]["output_bytes"] > 0


def test_vlm_server_port_raises_on_pipeline_timeout(tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"1")

    def slow_predict(*args, **kwargs):
        time.sleep(5)
        return [FakeResult("never reached")]

    class SlowPipeline:
        predict = staticmethod(slow_predict)

    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: SlowPipeline(),
        timeout_seconds=1,
    )

    with pytest.raises(RuntimeError, match="OCR 服务超时"):
        port.parse(
            {
                "task_id": "task-001",
                "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(image)}],
            }
        )


def test_vlm_server_port_timeout_event_logged_with_terminated_status(tmp_path):
    image = tmp_path / "page.jpg"
    image.write_bytes(b"1")
    events = []

    def slow_predict(*args, **kwargs):
        time.sleep(5)
        return [FakeResult("never reached")]

    class SlowPipeline:
        predict = staticmethod(slow_predict)

    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: SlowPipeline(),
        timeout_seconds=1,
        event_logger=lambda event, **payload: events.append((event, payload)),
    )

    with pytest.raises(RuntimeError, match="OCR 服务超时"):
        port.parse(
            {
                "task_id": "task-001",
                "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(image)}],
            }
        )

    finished_events = [payload for event, payload in events if event == "ocr_runner_finished"]
    assert finished_events, "应当发出 ocr_runner_finished 事件（含失败原因）"
    assert finished_events[0]["exit_code"] != 0
    assert "timeout" in finished_events[0].get("reason", "").lower() or "超时" in finished_events[0].get("reason", "")


def test_vlm_server_port_fast_pipeline_still_passes(tmp_path):
    """回归保护：未超时的快速调用必须照常成功。"""
    image1 = tmp_path / "p1.jpg"
    image2 = tmp_path / "p2.jpg"
    image1.write_bytes(b"1")
    image2.write_bytes(b"2")
    pipeline = FakePipeline(["第一页", "第二页"])
    port = PaddleOCRVLMServerDocumentPort(
        server_url="http://paddleocr-vlm-server:8080/v1",
        pipeline_factory=lambda server_url: pipeline,
        timeout_seconds=10,
    )

    result = port.parse(
        {
            "task_id": "task-001",
            "pages": [
                {"page_id": "p1", "page_no": 1, "processed_path": str(image1)},
                {"page_id": "p2", "page_no": 2, "processed_path": str(image2)},
            ],
        }
    )

    assert result["merged_text"] == "第一页\n\n第二页"
    assert all(page["status"] == "success" for page in result["pages"])
