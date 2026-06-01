# PaddleOCR VLLM Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the cold-start PaddleOCR-VL runner path with a Dockerized, always-on PaddleOCR-VL vLLM server while preserving existing task, OCR result, LLM extraction, retry, and review contracts.

**Architecture:** Add a service-mode OCR document port that uses the verified `PaddleOCRVL(vl_rec_backend="vllm-server")` path from `temp/paddlepaddle`, then select it via config. Add a process-local GPU stage queue around document parsing and field extraction so RTX 5060 8GB never runs OCR and LLM at the same time. Keep the current local runner as fallback until Windows Docker validation is complete.

**Tech Stack:** Python 3.12, Flask app factory, pytest, PyYAML, Docker Compose, PaddleOCR-VL 1.6, PaddleOCR vLLM server image, local JSON result store.

---

## Design References

- Spec: `docs/superpowers/specs/2026-06-01-paddleocr-vllm-server-design.md`
- Algorithm port TDD: `docs/Backend/Backend_TDD/02-algorithm-ports.md`
- Failure contract TDD: `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`
- Existing runner port: `app/backend/services/algorithm_ports/local_paddleocr.py`
- Existing runner script: `app/backend/services/algorithm_ports/paddleocr_vl_batch_runner.py`
- Temp baseline: `/home/kbzz1/manzufei_ocr/temp/paddlepaddle`

## File Map

- Create `app/backend/services/algorithm_ports/paddleocr_vlm_server.py`: service-mode `DocumentParsingPort` using an injectable pipeline factory and the vLLM server URL.
- Create `app/backend/services/gpu_stage_queue.py`: small process-local lock/context manager with event logging.
- Modify `app/backend/config.py`: add `local_ocr_mode`, `local_ocr_vlm_server_url`, `local_ocr_vlm_timeout_seconds`, and `gpu_stage_queue_enabled`.
- Modify `app/backend/__init__.py`: instantiate service-mode OCR port when `local_ocr_mode: vlm_server`; instantiate and pass `GpuStageQueue`.
- Modify `app/backend/services/algorithm_ports/orchestrator.py`: wrap document parsing and field extraction in the GPU stage queue.
- Modify `app/backend/services/local_event_log.py`: allow `gpu_stage_waiting`, `gpu_stage_started`, `gpu_stage_finished`, and service-mode OCR diagnostics.
- Modify `app/config/default.yaml` and `app/config/local.docker.yaml`: expose service-mode defaults.
- Modify `docker-compose.yml`: add `paddleocr-vlm-server` service with verified image/digest strategy and model mount.
- Modify `requirements.docker.txt`: this plan's first implementation uses PaddleOCR client code in the backend container to call the vLLM server, so the backend image must include the verified `paddleocr==3.5.0` and `paddlex[ocr]==3.5.2` combo.
- Modify docs under `docs/部署/GPU-Docker部署.md` and `app/config/algorithm-modules.README.md`.

---

### Task 1: Add Service-Mode OCR Config

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/backend/tests/test_config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/config/local.docker.yaml`

- [ ] **Step 1: Write failing config tests**

Append these tests to `app/backend/tests/test_config.py`:

```python
def test_load_config_supports_vlm_server_ocr_settings(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  enable_local_ocr: true
  local_ocr_mode: vlm_server
  local_ocr_vlm_server_url: http://paddleocr-vlm-server:8080/v1
  local_ocr_vlm_timeout_seconds: 240
  local_ocr_max_new_tokens: 1024
  local_ocr_max_pixels: 501760
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["enable_local_ocr"] is True
    assert config["local_ocr_mode"] == "vlm_server"
    assert config["local_ocr_vlm_server_url"] == "http://paddleocr-vlm-server:8080/v1"
    assert config["local_ocr_vlm_timeout_seconds"] == 240
    assert config["local_ocr_max_new_tokens"] == 1024
    assert config["local_ocr_max_pixels"] == 501760
    assert config["gpu_stage_queue_enabled"] is True


def test_local_ocr_mode_must_be_supported(tmp_path):
    import pytest
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  local_ocr_mode: direct_socket
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local_ocr_mode"):
        load_config(str(config_dir))


def test_local_ocr_vlm_timeout_must_be_positive(tmp_path):
    import pytest
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  local_ocr_vlm_timeout_seconds: 0
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="local_ocr_vlm_timeout_seconds"):
        load_config(str(config_dir))
```

- [ ] **Step 2: Run config tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py -q
```

Expected: FAIL because the new config keys are not flattened or validated.

- [ ] **Step 3: Add config defaults and flattening**

In `app/backend/config.py`, extend `DEFAULT_CONFIG`:

```python
    "local_ocr_mode": "runner",
    "local_ocr_vlm_server_url": "http://paddleocr-vlm-server:8080/v1",
    "local_ocr_vlm_timeout_seconds": 240,
    "gpu_stage_queue_enabled": True,
```

In `_flatten_config()`, after existing local OCR keys:

```python
    if "local_ocr_mode" in algorithms_config:
        flattened["local_ocr_mode"] = algorithms_config["local_ocr_mode"]
    if "local_ocr_vlm_server_url" in algorithms_config:
        flattened["local_ocr_vlm_server_url"] = algorithms_config["local_ocr_vlm_server_url"]
    if "local_ocr_vlm_timeout_seconds" in algorithms_config:
        flattened["local_ocr_vlm_timeout_seconds"] = algorithms_config["local_ocr_vlm_timeout_seconds"]
    if "gpu_stage_queue_enabled" in algorithms_config:
        flattened["gpu_stage_queue_enabled"] = algorithms_config["gpu_stage_queue_enabled"]
```

In `_validate_config()`:

```python
    local_ocr_mode = config.get("local_ocr_mode")
    if local_ocr_mode not in {"runner", "vlm_server"}:
        raise ValueError(f"local_ocr_mode 必须是 runner 或 vlm_server，当前值: {local_ocr_mode}")

    vlm_server_url = config.get("local_ocr_vlm_server_url")
    parsed_vlm_server_url = urlparse(vlm_server_url) if isinstance(vlm_server_url, str) else None
    if (
        not isinstance(vlm_server_url, str)
        or parsed_vlm_server_url is None
        or parsed_vlm_server_url.scheme not in {"http", "https"}
        or not parsed_vlm_server_url.hostname
        or any(char.isspace() for char in vlm_server_url)
    ):
        raise ValueError(f"local_ocr_vlm_server_url 必须是 http(s) URL，当前值: {vlm_server_url}")

    vlm_timeout = config.get("local_ocr_vlm_timeout_seconds")
    if not isinstance(vlm_timeout, int) or vlm_timeout <= 0:
        raise ValueError(f"local_ocr_vlm_timeout_seconds 必须为正整数，当前值: {vlm_timeout}")

    if not isinstance(config.get("gpu_stage_queue_enabled"), bool):
        raise ValueError(f"gpu_stage_queue_enabled 必须为布尔值，当前值: {config.get('gpu_stage_queue_enabled')}")
```

- [ ] **Step 4: Update YAML templates**

In `app/config/default.yaml`, under `algorithms`, add:

```yaml
  local_ocr_mode: "runner"
  local_ocr_vlm_server_url: "http://paddleocr-vlm-server:8080/v1"
  local_ocr_vlm_timeout_seconds: 240
  gpu_stage_queue_enabled: true
```

In `app/config/local.docker.yaml`, set service mode:

```yaml
  local_ocr_mode: "vlm_server"
  local_ocr_vlm_server_url: "http://paddleocr-vlm-server:8080/v1"
  local_ocr_vlm_timeout_seconds: 240
  gpu_stage_queue_enabled: true
```

- [ ] **Step 5: Run config tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/config.py app/backend/tests/test_config.py app/config/default.yaml app/config/local.docker.yaml
git commit -m "增加OCR常驻服务配置"
```

---

### Task 2: Add PaddleOCR VLM Server Document Port

**Files:**
- Create: `app/backend/services/algorithm_ports/paddleocr_vlm_server.py`
- Create: `app/backend/tests/test_paddleocr_vlm_server_port.py`

- [ ] **Step 1: Write failing tests for successful multi-page parsing**

Create `app/backend/tests/test_paddleocr_vlm_server_port.py`:

```python
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
```

- [ ] **Step 2: Add failing tests for error contracts**

Append:

```python
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
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_paddleocr_vlm_server_port.py -q
```

Expected: FAIL with import error because `paddleocr_vlm_server.py` does not exist.

- [ ] **Step 4: Implement the service-mode port**

Create `app/backend/services/algorithm_ports/paddleocr_vlm_server.py`:

```python
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
        output = pipeline.predict(input=image_path, **predict_kwargs)
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
```

- [ ] **Step 5: Run port tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_paddleocr_vlm_server_port.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/services/algorithm_ports/paddleocr_vlm_server.py app/backend/tests/test_paddleocr_vlm_server_port.py
git commit -m "增加PaddleOCR常驻服务端口"
```

---

### Task 3: Add GPU Stage Queue

**Files:**
- Create: `app/backend/services/gpu_stage_queue.py`
- Create: `app/backend/tests/test_gpu_stage_queue.py`
- Modify: `app/backend/services/local_event_log.py`
- Modify: `app/backend/tests/test_local_event_log.py`

- [ ] **Step 1: Write failing tests for queue serialization and event emission**

Create `app/backend/tests/test_gpu_stage_queue.py`:

```python
import threading
import time

from app.backend.services.gpu_stage_queue import GpuStageQueue


def test_gpu_stage_queue_emits_events_for_single_stage():
    events = []
    queue = GpuStageQueue(event_logger=lambda event, **payload: events.append((event, payload)))

    with queue.stage(task_id="task-001", stage="document_parsing"):
        pass

    assert [event for event, _payload in events] == [
        "gpu_stage_waiting",
        "gpu_stage_started",
        "gpu_stage_finished",
    ]
    assert events[0][1]["task_id"] == "task-001"
    assert events[0][1]["stage"] == "document_parsing"
    assert events[2][1]["status"] == "success"


def test_gpu_stage_queue_serializes_threads():
    queue = GpuStageQueue()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def run_stage(task_id):
        nonlocal active, max_active
        with queue.stage(task_id=task_id, stage="field_extraction"):
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    threads = [threading.Thread(target=run_stage, args=(f"task-{idx}",)) for idx in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_gpu_stage_queue_marks_exception_status():
    events = []
    queue = GpuStageQueue(event_logger=lambda event, **payload: events.append((event, payload)))

    try:
        with queue.stage(task_id="task-001", stage="document_parsing"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert events[-1][0] == "gpu_stage_finished"
    assert events[-1][1]["status"] == "error"
```

- [ ] **Step 2: Add failing local event log test**

Append to `app/backend/tests/test_local_event_log.py`:

```python
def test_allows_gpu_stage_events(tmp_path):
    from app.backend.services.local_event_log import LocalEventLog

    log = LocalEventLog(str(tmp_path))
    log.write("gpu_stage_waiting", task_id="task-001", stage="document_parsing")
    log.write("gpu_stage_started", task_id="task-001", stage="document_parsing", wait_ms=3)
    log.write("gpu_stage_finished", task_id="task-001", stage="document_parsing", elapsed_ms=5, status="success")

    content = (tmp_path / "backend-events.jsonl").read_text(encoding="utf-8")
    assert "gpu_stage_waiting" in content
    assert "gpu_stage_started" in content
    assert "gpu_stage_finished" in content
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_gpu_stage_queue.py app/backend/tests/test_local_event_log.py -q
```

Expected: FAIL because `gpu_stage_queue.py` and event names do not exist.

- [ ] **Step 4: Implement queue**

Create `app/backend/services/gpu_stage_queue.py`:

```python
import threading
import time
from contextlib import contextmanager
from typing import Callable


class GpuStageQueue:
    def __init__(self, event_logger: Callable[..., None] | None = None, enabled: bool = True):
        self._event_logger = event_logger
        self._enabled = enabled
        self._lock = threading.Lock()

    @contextmanager
    def stage(self, task_id: str, stage: str):
        if not self._enabled:
            yield
            return

        waiting_started = time.monotonic()
        self._emit("gpu_stage_waiting", task_id=task_id, stage=stage)
        self._lock.acquire()
        stage_started = time.monotonic()
        self._emit(
            "gpu_stage_started",
            task_id=task_id,
            stage=stage,
            wait_ms=int((stage_started - waiting_started) * 1000),
        )
        status = "success"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            elapsed_ms = int((time.monotonic() - stage_started) * 1000)
            self._lock.release()
            self._emit(
                "gpu_stage_finished",
                task_id=task_id,
                stage=stage,
                elapsed_ms=elapsed_ms,
                status=status,
            )

    def _emit(self, event: str, **payload) -> None:
        if self._event_logger is not None:
            self._event_logger(event, **payload)
```

- [ ] **Step 5: Allow event names**

In `app/backend/services/local_event_log.py`, add to `ALLOWED_EVENTS`:

```python
    "gpu_stage_waiting",
    "gpu_stage_started",
    "gpu_stage_finished",
```

Add to `EVENT_FIELDS`:

```python
    # Add "server_url" to the existing ocr_runner_started field set.
    "gpu_stage_waiting": {"task_id", "stage"},
    "gpu_stage_started": {"task_id", "stage", "wait_ms"},
    "gpu_stage_finished": {"task_id", "stage", "elapsed_ms", "status"},
```

The existing `ocr_runner_started` field set should include `"server_url"` so service-mode diagnostics are not dropped:

```python
    "ocr_runner_started": {
        "task_id",
        "backend",
        "server_url",
        "page_count",
        "timeout_seconds",
        "work_dir",
        "run_log_path",
        "container_name",
        "command",
        "python_executable",
        "script_path",
        "cache_dir",
        "device",
        "max_new_tokens",
        "max_pixels",
        "input_files",
    },
```

- [ ] **Step 6: Run queue and log tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_gpu_stage_queue.py app/backend/tests/test_local_event_log.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/gpu_stage_queue.py app/backend/tests/test_gpu_stage_queue.py app/backend/services/local_event_log.py app/backend/tests/test_local_event_log.py
git commit -m "增加GPU阶段队列"
```

---

### Task 4: Wire Service Port and GPU Queue into Backend

**Files:**
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Modify: `app/backend/tests/test_backend_e2e.py`
- Modify: `app/backend/tests/test_orchestrator.py`

- [ ] **Step 1: Write app factory test for service-mode port**

Append to `app/backend/tests/test_backend_e2e.py`:

```python
def test_backend_configures_vlm_server_ocr_port(tmp_path, monkeypatch):
    from app.backend import create_backend_app
    from app.backend.services.algorithm_ports.paddleocr_vlm_server import PaddleOCRVLMServerDocumentPort

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    export_dir = tmp_path / "exports"
    export_dir.mkdir()
    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{data_dir}"
  log_dir: "{log_dir}"
  model_dir: "{tmp_path}/models"
  export_dir: "{export_dir}"
  static_dir: "{static_dir}"
  storage_dir: "{data_dir}"
algorithms:
  enable_local_ocr: true
  local_ocr_mode: vlm_server
  local_ocr_vlm_server_url: http://paddleocr-vlm-server:8080/v1
  gpu_stage_queue_enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])

    app = create_backend_app(str(config_dir))
    orchestrator = app.config["TASK_SERVICE"]._orchestrator

    assert orchestrator._image_port is not None
    assert isinstance(orchestrator._doc_port, PaddleOCRVLMServerDocumentPort)
    assert orchestrator._gpu_stage_queue is not None
```

- [ ] **Step 2: Write orchestrator queue integration test**

Add a focused test to `app/backend/tests/test_orchestrator.py`:

```python
class RecordingGpuQueue:
    def __init__(self):
        self.stages = []

    def stage(self, task_id, stage):
        self.stages.append((task_id, stage))
        class _Context:
            def __enter__(_self):
                return None
            def __exit__(_self, exc_type, exc, tb):
                return False
        return _Context()


def test_orchestrator_wraps_document_and_field_gpu_stages(tmp_path):
    from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
    from app.backend.storage.json_store import JsonStore

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            return {
                "pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "正文"}],
                "merged_text": "正文",
            }

    class FieldPort:
        def extract(self, input):
            return [{
                "field_key": "chief_complaint",
                "original_value": "咳嗽",
                "evidence": "主诉：咳嗽",
                "confidence": 0.8,
                "extraction_status": "extracted",
                "verification_status": "not_checked",
                "quality_flags": [],
                "source_section": "主诉",
                "source_hint": "主诉",
                "source_text": "主诉：咳嗽",
                "source_group_id": "主诉",
                "ocr_correction": {"applied": False, "raw": "", "normalized": "", "reason": ""},
            }]

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

        def get_task(self, task_id):
            return {"task_id": task_id, "status": "processing"}

    store = JsonStore(str(tmp_path / "data"))
    queue = RecordingGpuQueue()
    (tmp_path / "p1.jpg").write_bytes(b"img")
    orchestrator = ProcessingOrchestrator(
        store=store,
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=FieldPort(),
        gpu_stage_queue=queue,
    )

    orchestrator.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "p1", "page_no": 1, "original_image_path": str(tmp_path / "p1.jpg")}],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    assert queue.stages == [
        ("task_001", "document_parsing"),
        ("task_001", "field_extraction"),
    ]
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_backend_configures_vlm_server_ocr_port app/backend/tests/test_orchestrator.py::test_orchestrator_wraps_document_and_field_gpu_stages -q
```

Expected: FAIL because backend does not select the new port and orchestrator does not accept queue.

- [ ] **Step 4: Wire app factory**

In `app/backend/__init__.py`, replace the local OCR setup block with a mode switch:

```python
    gpu_stage_queue = None
    if config.get("gpu_stage_queue_enabled"):
        from .services.gpu_stage_queue import GpuStageQueue
        gpu_stage_queue = GpuStageQueue(event_logger=event_log.safe_write)

    if config.get("enable_local_ocr"):
        from .services.algorithm_ports.image_processing import OriginalImagePassthroughPort

        image_port = OriginalImagePassthroughPort()
        local_ocr_mode = config.get("local_ocr_mode", "runner")
        if local_ocr_mode == "vlm_server":
            from .services.algorithm_ports.paddleocr_vlm_server import PaddleOCRVLMServerDocumentPort

            doc_port = PaddleOCRVLMServerDocumentPort(
                server_url=config["local_ocr_vlm_server_url"],
                max_new_tokens=config.get("local_ocr_max_new_tokens", 1024),
                max_pixels=config.get("local_ocr_max_pixels"),
                timeout_seconds=config["local_ocr_vlm_timeout_seconds"],
                event_logger=event_log.safe_write,
            )
        else:
            from .services.algorithm_ports.local_paddleocr import LocalPaddleOCRDocumentPort

            ocr_work_root = config.get("local_ocr_work_root") or os.path.join(config["storage_dir"], "ocr_runs")
            doc_port = LocalPaddleOCRDocumentPort(
                python_executable=config["local_ocr_python_executable"],
                script_path=config["local_ocr_script_path"],
                work_root=ocr_work_root,
                cache_dir=os.path.join(config["model_dir"], "ppstructure", "paddlex_cache"),
                device=config.get("local_ocr_device"),
                max_new_tokens=config.get("local_ocr_max_new_tokens", 1024),
                max_pixels=config.get("local_ocr_max_pixels"),
                timeout_seconds=config["local_ocr_timeout_seconds"],
                event_logger=event_log.safe_write,
            )
```

When creating `ProcessingOrchestrator`, pass:

```python
        gpu_stage_queue=gpu_stage_queue,
```

- [ ] **Step 5: Wire orchestrator queue**

In `ProcessingOrchestrator.__init__()`, add parameter:

```python
        gpu_stage_queue=None,
```

Set:

```python
        self._gpu_stage_queue = gpu_stage_queue
```

Add helper:

```python
    def _gpu_stage(self, task_id: str, stage: str):
        if self._gpu_stage_queue is None:
            return _NoopContext()
        return self._gpu_stage_queue.stage(task_id=task_id, stage=stage)
```

Add class at module bottom:

```python
class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
```

Wrap document parse call:

```python
                with self._gpu_stage(task_id, "document_parsing"):
                    doc_result = self._doc_port.parse(doc_input)
```

Wrap field extraction call:

```python
            with self._gpu_stage(task_id, "field_extraction"):
                candidates = field_port.extract(field_input)
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py::test_backend_configures_vlm_server_ocr_port app/backend/tests/test_orchestrator.py::test_orchestrator_wraps_document_and_field_gpu_stages -q
```

Expected: PASS.

- [ ] **Step 7: Run existing OCR/orchestrator tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_local_paddleocr_port.py app/backend/tests/test_orchestrator.py app/backend/tests/test_backend_e2e.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/backend/__init__.py app/backend/services/algorithm_ports/orchestrator.py app/backend/tests/test_backend_e2e.py app/backend/tests/test_orchestrator.py
git commit -m "接入OCR常驻服务和GPU队列"
```

---

### Task 5: Update Docker Compose and Runtime Dependencies

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Modify: `requirements.docker.txt`
- Modify: `app/backend/tests/test_windows_startup_scripts.py`

- [ ] **Step 1: Add failing deployment tests**

Append to `app/backend/tests/test_windows_startup_scripts.py`:

```python
def test_docker_compose_defines_paddleocr_vlm_server():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "paddleocr-vlm-server" in content
    assert "paddleocr-genai-vllm-server" in content
    assert "PaddleOCR-VL-1.6-0.9B" in content
    assert "vlm_backend_config.yaml" in content
    assert "gpus: all" in content


def test_docker_requirements_match_vlm_server_client_combo():
    content = Path("requirements.docker.txt").read_text(encoding="utf-8")

    assert "paddleocr==3.5.0" in content
    assert "paddlex==3.5.2" in content or "paddlex[ocr]==3.5.2" in content
```

- [ ] **Step 2: Run deployment tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py -q
```

Expected: FAIL because compose lacks `paddleocr-vlm-server` and requirements still use old combo.

- [ ] **Step 3: Update requirements**

Set `requirements.docker.txt` OCR lines to the service-mode client combo:

```text
paddleocr==3.5.0
paddlex[ocr]==3.5.2
```

Keep existing non-OCR requirements unchanged. Do not add `llama-cpp-python` here; it is built from source in `Dockerfile`.

- [ ] **Step 4: Update Dockerfile dependency install**

Keep `paddlepaddle-gpu==3.2.1` installation unchanged. Ensure `requirements.docker.txt` is installed after PaddlePaddle as it is today.

- [ ] **Step 5: Add vLLM backend config to repo**

Create `app/config/vlm_backend_config.yaml`:

```yaml
max_model_len: 4096
gpu_memory_utilization: 0.75
tensor_parallel_size: 1
max_num_seqs: 1
dtype: bfloat16
```

- [ ] **Step 6: Update compose**

Add service to `docker-compose.yml`:

```yaml
  paddleocr-vlm-server:
    image: ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu
    container_name: paddleocr-vlm-server
    restart: unless-stopped
    command: >
      paddleocr genai_server
      --model_name PaddleOCR-VL-1.6-0.9B
      --model_dir /workspace/model/PaddleOCR-VL-1.6
      --host 0.0.0.0
      --port 8080
      --backend vllm
      --backend_config /workspace/vlm_backend_config.yaml
    volumes:
      - ./models/ppstructure:/workspace/model
      - ./app/config/vlm_backend_config.yaml:/workspace/vlm_backend_config.yaml:ro
    gpus: all
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8080/v1/models || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 20
      start_period: 180s
```

Add backend dependency:

```yaml
    depends_on:
      paddleocr-vlm-server:
        condition: service_healthy
```

Keep `manzufei-ocr` `gpus: all` because LLM extraction still needs GPU.

- [ ] **Step 7: Run deployment tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py -q
```

Expected: PASS.

- [ ] **Step 8: Validate compose syntax if Docker is available**

Run:

```bash
docker compose config >/tmp/manzufei_ocr_compose.out
```

Expected: exit code 0. If Docker is unavailable, record that this validation was skipped.

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml Dockerfile requirements.docker.txt app/config/vlm_backend_config.yaml app/backend/tests/test_windows_startup_scripts.py
git commit -m "更新PaddleOCR常驻服务部署"
```

---

### Task 6: Update Documentation and Offline Packaging Notes

**Files:**
- Modify: `docs/部署/GPU-Docker部署.md`
- Modify: `app/config/algorithm-modules.README.md`
- Modify: `docs/部署/离线验收记录.md`
- Modify: `docs/PRD任务清单.md`

- [ ] **Step 1: Update GPU Docker deployment doc**

In `docs/部署/GPU-Docker部署.md`, replace the “OCR 接入” strategy text with:

```markdown
后端默认通过 `paddleocr-vlm-server` 常驻服务调用 PaddleOCR-VL。该服务使用官方 `paddleocr-genai-vllm-server` 镜像、vLLM backend 和挂载的 `models/ppstructure/PaddleOCR-VL-1.6/` 模型目录。后端不再为每个任务重复启动 OCR runner 和加载模型；任务只通过 `DocumentParsingPort` 提交多页图片并保存 `document_result.json`。

5060 8GB 显存下启用 GPU 阶段队列：OCR 阶段和 LLM 字段抽取阶段串行执行，不允许同时抢占显存。OCR 成功而 LLM 失败时，重试复用已保存的 `document_result.json`，只重跑字段抽取。

服务化 OCR 当前验证组合来自 `temp/paddlepaddle`：`paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex==3.5.2`、`PaddleOCR-VL-1.6-0.9B`、官方 vLLM server 镜像离线 tar digest `sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621`。该组合已在 RTX 4070 Laptop 8GB 上流畅运行，目标 RTX 5060 8GB 按同显存级别保守参数部署。
```

- [ ] **Step 2: Update algorithm modules README**

In `app/config/algorithm-modules.README.md`, add a “服务化 OCR” subsection that states:

```markdown
正式 Docker 部署优先使用 `local_ocr_mode: vlm_server`。旧 `runner` 模式保留为 fallback，不再作为性能优化主路径。服务化模式复用 `temp/paddlepaddle` 的常驻 vLLM server 运行栈，但不复用其 `manage.bat`、`input/output/processed` 归档流程；任务生命周期仍由后端管理。
```

- [ ] **Step 3: Update offline acceptance checklist**

In `docs/部署/离线验收记录.md`, add checklist items:

```markdown
- [ ] `docker compose ps` 显示 `paddleocr-vlm-server` 为 healthy。
- [ ] `docker compose exec paddleocr-vlm-server curl -sf http://localhost:8080/v1/models` 返回成功。
- [ ] `nvidia-smi` 显示 PaddleOCR-VL 服务常驻显存。
- [ ] 连续处理两单脱敏样本时，第二单 OCR 阶段不重复出现长时间模型冷启动。
- [ ] 并发触发两个任务时，事件日志出现 `gpu_stage_waiting`，且 OCR/LLM 阶段未并发运行。
```

- [ ] **Step 4: Update PRD task list**

In `docs/PRD任务清单.md`, update OCR deployment note to mention:

```markdown
OCR 优化方向收敛为 PaddleOCR-VL vLLM server 常驻服务 + 8GB GPU 阶段队列；旧 runner 保留为 fallback。
```

- [ ] **Step 5: Check docs formatting**

Run:

```bash
rg -n "PaddleOCR-VL|vlm_server|gpu_stage|paddlex==3.5.2" docs app/config/algorithm-modules.README.md
```

Expected: results show the new service-mode path and no contradictory statement saying Docker deployment does not use a separate OCR container.

- [ ] **Step 6: Commit**

```bash
git add docs/部署/GPU-Docker部署.md app/config/algorithm-modules.README.md docs/部署/离线验收记录.md docs/PRD任务清单.md
git commit -m "更新OCR常驻服务部署文档"
```

---

### Task 7: Final Verification

**Files:**
- No new source files unless earlier tasks reveal necessary fixes.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest \
  app/backend/tests/test_config.py \
  app/backend/tests/test_paddleocr_vlm_server_port.py \
  app/backend/tests/test_gpu_stage_queue.py \
  app/backend/tests/test_local_event_log.py \
  app/backend/tests/test_local_paddleocr_port.py \
  app/backend/tests/test_orchestrator.py \
  app/backend/tests/test_backend_e2e.py \
  app/backend/tests/test_windows_startup_scripts.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend suite**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 3: Validate compose**

Run:

```bash
docker compose config >/tmp/manzufei_ocr_compose.out
```

Expected: PASS. If sandbox or Docker blocks this, record the exact error in the final implementation notes.

- [ ] **Step 4: Inspect dependency pins**

Run:

```bash
rg -n "paddlepaddle-gpu==3.2.1|paddleocr==3.5.0|paddlex.*3.5.2|PaddleOCR-VL-1.6|paddleocr-vlm-server" Dockerfile requirements.docker.txt docker-compose.yml app/config docs
```

Expected: service-mode Docker path references the verified combo; old runner fallback docs may still mention `paddlex[ocr]==3.5.0` only when explicitly labeled as old runner fallback.

- [ ] **Step 5: Commit final fixes if needed**

If verification required fixes:

```bash
git add app backend docs docker-compose.yml Dockerfile requirements.docker.txt
git commit -m "修正OCR常驻服务验证问题"
```

If no fixes were needed, do not create an empty commit.
