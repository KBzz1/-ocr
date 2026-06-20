"""Qwen Vision vLLM DocumentParsingPort 契约测试。"""
from pathlib import Path

import pytest

from app.backend.services.algorithm_ports.qwen_vision_vllm import (
    QwenVisionVLLMDocumentPort,
)


class FakeQwenClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete_text_from_image(self, image_path, system_prompt, user_prompt, max_tokens, temperature):
        self.calls.append({
            "image_path": str(image_path),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return self.outputs.pop(0)


def _make_image(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    return path


def test_qwen_vision_port_parses_pages_in_saved_order(tmp_path):
    img1 = _make_image(tmp_path, "p1.jpg")
    img2 = _make_image(tmp_path, "p2.jpg")
    client = FakeQwenClient(["第一页正文", "第二页正文"])
    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
    )

    result = port.parse({
        "task_id": "task-001",
        "pages": [
            {"page_id": "p2", "page_no": 2, "processed_path": str(img2)},
            {"page_id": "p1", "page_no": 1, "processed_path": str(img1)},
        ],
    })

    assert result["merged_text"] == "第一页正文\n\n第二页正文"
    assert [p["source"] for p in result["pages"]] == ["qwen_vision_vllm", "qwen_vision_vllm"]
    assert [p["page_no"] for p in result["pages"]] == [1, 2]
    assert [p["status"] for p in result["pages"]] == ["success", "success"]
    assert client.calls[0]["temperature"] == 0.0
    assert client.calls[0]["max_tokens"] == 4096
    assert "签名" in client.calls[0]["system_prompt"] or "页眉" in client.calls[0]["system_prompt"]


def test_qwen_vision_port_emits_ocr_vlm_started_and_finished_events(tmp_path):
    img = _make_image(tmp_path, "p1.jpg")
    client = FakeQwenClient(["第一页"])
    events = []

    def event_logger(event, **payload):
        events.append((event, payload))

    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
        event_logger=event_logger,
    )

    port.parse({
        "task_id": "task-002",
        "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(img)}],
    })

    assert events[0][0] == "ocr_vlm_started"
    assert events[0][1]["backend"] == "qwen_vision_vllm"
    assert events[0][1]["server_url"] == "http://qwen-vision-vllm-server:8000/v1"
    assert events[0][1]["model"] == "Qwen3.5-4B-AWQ-4bit"
    assert events[0][1]["page_count"] == 1
    assert events[0][1]["temperature"] == 0.0
    assert events[0][1]["max_tokens"] == 4096
    assert events[0][1]["top_p"] == 1.0
    assert "input_files" in events[0][1]
    # 不允许日志携带 OCR 文本或图片 base64
    assert "ocr_text" not in events[0][1]
    assert "image_base64" not in events[0][1]
    assert "merged_text" not in events[0][1]

    assert events[1][0] == "ocr_vlm_finished"
    assert events[1][1]["backend"] == "qwen_vision_vllm"
    assert events[1][1]["exit_code"] == 0
    assert events[1][1]["output_exists"] is True
    assert "elapsed_ms" in events[1][1]


def test_qwen_vision_port_raises_when_image_missing(tmp_path):
    client = FakeQwenClient(["unused"])
    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
    )

    with pytest.raises(RuntimeError, match="OCR 输入图片不存在"):
        port.parse({
            "task_id": "task-003",
            "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(tmp_path / "missing.jpg")}],
        })


def test_qwen_vision_port_raises_when_pages_empty(tmp_path):
    client = FakeQwenClient([])
    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
    )

    with pytest.raises(RuntimeError, match="OCR 输入页面为空"):
        port.parse({"task_id": "task-004", "pages": []})


def test_qwen_vision_port_marks_empty_page_as_failed(tmp_path):
    img1 = _make_image(tmp_path, "p1.jpg")
    img2 = _make_image(tmp_path, "p2.jpg")
    client = FakeQwenClient(["", "第二页正文"])
    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
    )

    result = port.parse({
        "task_id": "task-005",
        "pages": [
            {"page_id": "p1", "page_no": 1, "processed_path": str(img1)},
            {"page_id": "p2", "page_no": 2, "processed_path": str(img2)},
        ],
    })

    assert result["pages"][0]["status"] == "failed"
    assert result["pages"][0]["text"] == ""
    assert result["pages"][1]["status"] == "success"
    assert result["merged_text"] == "第二页正文"


def test_qwen_vision_port_rejects_prompt_injection_in_user_prompt(tmp_path):
    """系统 prompt 不得正向指示改写/补全/重排/标题替换/医学推理。"""
    img = _make_image(tmp_path, "p1.jpg")
    client = FakeQwenClient(["OCR 文本"])
    port = QwenVisionVLLMDocumentPort(
        client=client,
        model="Qwen3.5-4B-AWQ-4bit",
        server_url="http://qwen-vision-vllm-server:8000/v1",
        max_tokens=4096,
        temperature=0.0,
        timeout_seconds=240,
    )
    port.parse({
        "task_id": "task-006",
        "pages": [{"page_id": "p1", "page_no": 1, "processed_path": str(img)}],
    })

    system_prompt = client.calls[0]["system_prompt"]
    # 正向禁指令（出现即代表 prompt 在告诉模型做这些事）
    forbidden_instructions = [
        "请重排", "应当重排", "请补全", "应当补全", "请医学推理",
        "请把品后诊断替换", "应当标题替换", "请标题替换", "请写最后诊断",
    ]
    for marker in forbidden_instructions:
        assert marker not in system_prompt, f"系统 prompt 不应包含正向禁指令 {marker!r}"
    # 至少出现一个允许的过滤项
    allowed_markers = ["页眉", "页脚", "页码", "签名"]
    assert any(marker in system_prompt for marker in allowed_markers)
    # 至少出现一个负向禁指令（不重排 / 不补全 / 不纠错 / 不改写 / 不总结）
    negative_constraints = ["不重排", "不补全", "不纠错", "不改写", "不总结"]
    assert any(marker in system_prompt for marker in negative_constraints)
