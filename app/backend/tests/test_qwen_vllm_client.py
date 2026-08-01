"""Qwen Vision vLLM 共享 OpenAI-compatible 客户端契约测试。

后端通过 OpenAI Python SDK 调本地 qwen-vision-vllm-server 的 /v1，本测试只验证
调用方传给 OpenAI 客户端的请求形状、剥离 thinking、MIME 推断、失败映射。
"""
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backend.services.algorithm_ports.qwen_vllm_client import (
    QwenVLLMClient,
    detect_image_mime,
    strip_think_blocks,
)


class FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeOpenAIClient:
    def __init__(self, content):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def _make_image(tmp_path: Path, name: str = "p1.jpg") -> Path:
    image = tmp_path / name
    image.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    return image


def test_detect_image_mime_supports_required_extensions(tmp_path):
    assert detect_image_mime(tmp_path / "a.jpg") == "image/jpeg"
    assert detect_image_mime(tmp_path / "a.jpeg") == "image/jpeg"
    assert detect_image_mime(tmp_path / "a.png") == "image/png"
    assert detect_image_mime(tmp_path / "a.bmp") == "image/bmp"
    assert detect_image_mime(tmp_path / "a.tif") == "image/tiff"
    assert detect_image_mime(tmp_path / "a.tiff") == "image/tiff"
    assert detect_image_mime(tmp_path / "a.webp") == "image/webp"


def test_detect_image_mime_rejects_unsupported_extension(tmp_path):
    with pytest.raises(ValueError, match="unsupported image extension"):
        detect_image_mime(tmp_path / "a.gif")


def test_strip_think_blocks_removes_whole_block():
    raw = "<think>reasoning here</think>正文：主诉咳嗽"
    assert strip_think_blocks(raw) == "正文：主诉咳嗽"


def test_strip_think_blocks_keeps_inner_text_when_unclosed():
    raw = "<think>未关闭\n正文内容"
    # 未关闭的 <think> 标签必须被丢弃，避免污染 OCR/抽取输出
    assert "正文内容" in strip_think_blocks(raw)
    assert "<think>" not in strip_think_blocks(raw)


def test_qwen_vllm_client_sends_image_url_message_with_local_base_url(tmp_path):
    image = _make_image(tmp_path)
    fake = FakeOpenAIClient(content="<page>OCR 模型输出</page>")
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=240,
    )

    text = client.complete_text_from_image(
        image_path=image,
        system_prompt="你是一个医疗文档 OCR 助手。",
        user_prompt="请识别这张图片。",
        max_tokens=4096,
        temperature=0.0,
    )

    assert text == "<page>OCR 模型输出</page>"

    call = fake.chat.completions.calls[-1]
    assert call["model"] == "Qwen3.5-4B-AWQ-4bit"
    assert call["temperature"] == 0.0
    assert call["top_p"] == 1.0
    assert call["max_tokens"] == 4096
    assert call["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert "OCR" in messages[0]["content"]
    user_message = messages[1]
    parts = user_message["content"]
    image_part = next(p for p in parts if p["type"] == "image_url")
    data_url = image_part["image_url"]["url"]
    assert data_url.startswith("data:image/jpeg;base64,")
    encoded = data_url.split(",", 1)[1]
    assert base64.b64decode(encoded) == b"\xff\xd8\xff\xe0fake-jpeg"
    text_part = next(p for p in parts if p["type"] == "text")
    assert "请识别" in text_part["text"]


def test_qwen_vllm_client_sends_text_json_request_with_response_format():
    fake = FakeOpenAIClient(content='{"fields": []}')
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )

    result = client.complete_json("fixed field prompt", max_tokens=8192, temperature=0.0)

    assert result == {"fields": []}
    call = fake.chat.completions.calls[-1]
    assert call["model"] == "Qwen3.5-4B-AWQ-4bit"
    assert call["temperature"] == 0.0
    assert call["top_p"] == 1.0
    assert call["max_tokens"] == 8192
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert call["messages"] == [{"role": "user", "content": "fixed field prompt"}]


def test_qwen_vllm_client_accepts_fenced_json_with_trailing_commas():
    fake = FakeOpenAIClient(content="""
下面是结果：
```json
{
  "fields": [
    {
      "field_key": "chief_complaint",
    },
  ],
}
```
""")
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )

    assert client.complete_json("prompt", max_tokens=8192, temperature=0.0) == {
        "fields": [{"field_key": "chief_complaint"}]
    }


def test_qwen_vllm_client_does_not_modify_string_literals_when_removing_trailing_commas():
    fake = FakeOpenAIClient(
        content='{"note":"保留原文 ,} 片段","fields":[{"field_key":"chief_complaint",},]}'
    )
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )

    assert client.complete_json("prompt", max_tokens=8192, temperature=0.0) == {
        "note": "保留原文 ,} 片段",
        "fields": [{"field_key": "chief_complaint"}],
    }


def test_qwen_vllm_client_strips_think_blocks_from_text(tmp_path):
    image = _make_image(tmp_path)
    fake = FakeOpenAIClient(content="<think>chain-of-thought</think>主诉：咳嗽")
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=240,
    )

    text = client.complete_text_from_image(
        image_path=image,
        system_prompt="OCR",
        user_prompt="",
        max_tokens=1024,
        temperature=0.0,
    )
    assert text == "主诉：咳嗽"


def test_complete_json_accepts_system_prompt():
    fake = FakeOpenAIClient('{"ok": true}')
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )
    client.complete_json(
        prompt="user 内容", max_tokens=100, temperature=0.0,
        system_prompt="system 规则",
    )
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["messages"] == [
        {"role": "system", "content": "system 规则"},
        {"role": "user", "content": "user 内容"},
    ]


def test_complete_json_without_system_prompt_keeps_single_user_message():
    fake = FakeOpenAIClient('{"ok": true}')
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )
    client.complete_json(prompt="仅 user", max_tokens=100, temperature=0.0)
    kwargs = fake.chat.completions.calls[0]
    assert kwargs["messages"] == [{"role": "user", "content": "仅 user"}]


def test_qwen_vllm_client_raises_on_empty_response():
    fake = FakeOpenAIClient(content="")
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )

    with pytest.raises(RuntimeError, match="Qwen vLLM 返回为空"):
        client.complete_json("prompt", max_tokens=512, temperature=0.0)


def test_qwen_vllm_client_raises_on_openai_error():
    class ErrorCompletions:
        def create(self, **kwargs):
            raise TimeoutError("vLLM socket timeout")

        @property
        def calls(self):
            return []

    class ErrorClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=ErrorCompletions())

    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=ErrorClient(),
        timeout_seconds=360,
    )

    with pytest.raises(RuntimeError, match="Qwen vLLM 调用失败"):
        client.complete_json("prompt", max_tokens=512, temperature=0.0)


def test_qwen_vllm_client_uses_local_base_url_when_constructed_without_injection():
    """未注入 openai_client 时，必须用 OpenAI(base_url=..., api_key=not-needed) 拼本地连接。"""
    captured = {}
    class CapturingOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class CapturingHttpx:
        class Client:
            def __init__(self, **kwargs):
                assert kwargs == {"trust_env": False}
                captured["httpx_client_kwargs"] = kwargs

    from app.backend.services.algorithm_ports import qwen_vllm_client as mod

    mod.OpenAI = CapturingOpenAI
    mod.httpx = CapturingHttpx
    client = QwenVLLMClient(
        base_url="http://127.0.0.1:8082/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=None,
        api_key="placeholder",
        timeout_seconds=240,
    )
    assert isinstance(client._client, CapturingOpenAI)
    assert captured["base_url"] == "http://127.0.0.1:8082/v1"
    assert captured["api_key"] == "placeholder"
    assert captured["timeout"] == 240
    assert isinstance(captured["http_client"], CapturingHttpx.Client)
    assert captured["httpx_client_kwargs"] == {"trust_env": False}


def test_qwen_vllm_client_image_path_missing_raises(tmp_path):
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=FakeOpenAIClient(content="unused"),
        timeout_seconds=240,
    )
    missing = tmp_path / "absent.jpg"
    with pytest.raises(FileNotFoundError, match="OCR 输入图片不存在"):
        client.complete_text_from_image(
            image_path=missing,
            system_prompt="OCR",
            user_prompt="",
            max_tokens=1024,
            temperature=0.0,
        )
