# Qwen Vision vLLM OCR And Fixed-Field Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the workstation default OCR and fixed-field extraction runtime to one local Qwen Vision vLLM service, while preserving the 2026-06-18 fixed-field evidence contract and removing old PaddleOCR/llama.cpp default paths.

**Architecture:** Execute this plan from a new worktree based on `worktree-qwen-admission-structured-fields`, not from `master`. The backend will use one OpenAI-compatible `qwen-vision-vllm-server` for both image OCR and text-only fixed-field JSON extraction, with one shared OpenAI SDK client boundary. A single GPU queue stage will cover OCR through fixed-field extraction for each task, so another task cannot interleave between those two model calls.

**Tech Stack:** Python 3, Flask, pytest, OpenAI Python SDK against local vLLM, Docker Compose, Windows batch scripts, existing JSON storage and review contracts. No cloud API, runtime model download, telemetry, real patient data, model weights, logs, or local private paths may be committed.

---

## Spec Self-Review

The spec is implementable after the latest clarifications. It now records the critical decisions that were missing from the first draft:

- Implementation baseline is `worktree-qwen-admission-structured-fields`; do not reimplement fixed-field schema/evidence from `master`.
- One `qwen-vision-vllm-server` serves both OCR and fixed-field extraction.
- Model directory is `models/llm/Qwen3.5-4B-AWQ-4bit/`, mounted read-only.
- Backend calls vLLM through the OpenAI Python SDK.
- A task continuously holds the GPU queue from OCR through fixed-field extraction.

Issues the implementation must handle:

- The current 6-18 worktree is dirty with `admission_contract.py`, `test_admission_contract.py`, and a temporary hard-coded `llm_client.py` timeout edit. Do not overwrite these changes. Keep the `ocr_correction` contract fix; replace the hard-coded timeout with config or drop it when the OpenAI SDK path removes llama.cpp from the default runtime.
- `app/backend/services/copd_extraction/CLAUDE.md` still says raw OCR must be fully preserved. This conflicts with the new OCR contract that permits filtering page headers, footers, page numbers, print time, and signatures. Update local agent docs in the documentation task.
- Existing deployment docs and tests still assert PaddleOCR VLM digest and llama.cpp CUDA wheel requirements as default. The plan must update those assertions instead of leaving parallel default paths.
- Existing 6-18 fixed-field schema, `evidence_units`, prompt, and `admission_contract` are kept; this plan must not regress to old free-key section-group extraction.

## Execution Baseline

Before Task 1, create or choose a clean execution worktree from `worktree-qwen-admission-structured-fields`.

First inspect the current 6-18 worktree because it may contain uncommitted contract fixes that are not present on the branch tip:

```bash
git -C /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-structured-fields status --short
git -C /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-structured-fields diff -- app/backend/services/copd_extraction/admission_contract.py app/backend/tests/test_admission_contract.py app/backend/services/copd_extraction/llm_client.py
```

Expected: if the dirty files are only `admission_contract.py`, `test_admission_contract.py`, and `llm_client.py`, preserve the `ocr_correction` contract diff from the first two files and do not carry the temporary `DEFAULT_LLM_TIMEOUT = 360.0` edit as baseline code.

If the `ocr_correction` contract diff is still dirty, save just that diff before creating the execution worktree:

```bash
git -C /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-structured-fields diff -- app/backend/services/copd_extraction/admission_contract.py app/backend/tests/test_admission_contract.py > /tmp/qwen-admission-ocr-correction.patch
```

Expected: `/tmp/qwen-admission-ocr-correction.patch` contains only `ocr_correction` review-candidate contract changes and the matching regression test. It must not contain the `llm_client.py` timeout change.

Recommended command from the repository root if no such clean execution worktree exists:

```bash
git worktree add /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime -b qwen-admission-vllm-runtime worktree-qwen-admission-structured-fields
```

Expected: worktree created at `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime`.

If branch `qwen-admission-vllm-runtime` already exists but the worktree path does not, do not delete the branch. Attach a worktree to the existing branch:

```bash
git worktree add /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime qwen-admission-vllm-runtime
```

Expected: existing branch is checked out at the execution worktree path.

If `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime` already exists, inspect it before doing any work:

```bash
git -C /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime status --short
```

Expected: clean worktree. If it is dirty, stop and report the dirty paths before applying this plan.

If `/tmp/qwen-admission-ocr-correction.patch` is non-empty, apply and commit it in the execution worktree before Task 1:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime
git apply /tmp/qwen-admission-ocr-correction.patch
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_admission_contract.py::test_map_qwen_fields_returns_review_candidate_contract_shape -q
git add app/backend/services/copd_extraction/admission_contract.py app/backend/tests/test_admission_contract.py
git commit -m "保留OCR纠错审核契约"
```

Expected: the regression test passes and the preflight commit contains only `admission_contract.py` and `test_admission_contract.py`. If the patch is empty, skip this preflight commit.

## File Structure

| Path | Role | Change |
| --- | --- | --- |
| `app/backend/config.py` | Runtime config loading and validation | Add shared Qwen vLLM config, model dir, OCR/extraction tokens/timeouts, 8GB safeguards |
| `app/config/default.yaml` | Default local config namespace | Switch defaults to Qwen vLLM backend |
| `app/config/local.docker.yaml` | Windows Docker local config template | Use `qwen-vision-vllm-server`, model dir under `models/llm`, temperature 0 |
| `requirements.txt` | Dev backend dependencies | Add `openai` SDK if absent |
| `requirements.docker.txt` | Docker backend dependencies | Add `openai`; remove PaddleOCR and llama.cpp from default runtime if unused |
| `app/backend/services/algorithm_ports/qwen_vllm_client.py` | Shared OpenAI-compatible vLLM client | Create |
| `app/backend/services/algorithm_ports/qwen_vision_vllm.py` | OCR `DocumentParsingPort` using Qwen vision messages | Create |
| `app/backend/services/algorithm_ports/paddleocr_vlm_server.py` | Old OCR default | Remove from default path; delete or leave unreachable only if tests prove it is not default |
| `app/backend/services/copd_extraction/llm_client.py` | Current llama.cpp client | Replace default builder with OpenAI-compatible JSON client or move llama.cpp behind non-default compatibility |
| `app/backend/services/copd_extraction/port.py` | Fixed-field extraction port | Build default port from Qwen vLLM JSON client |
| `app/backend/services/algorithm_ports/orchestrator.py` | Processing sequence and GPU queue | Hold one `qwen_ocr_and_extraction` stage across OCR and extraction |
| `app/backend/services/gpu_stage_queue.py` | Queue primitive | Keep primitive; tests cover continuous stage behavior at orchestrator level |
| `app/backend/services/local_event_log.py` | Event privacy allowlist | Add Qwen OCR/extraction diagnostic fields without text or base64 |
| `app/backend/__init__.py` | App factory wiring | Instantiate Qwen OCR port and Qwen fixed-field port from shared config |
| `docker-compose.yml` | Local/Windows service graph | Replace `paddleocr-vlm-server` with `qwen-vision-vllm-server` |
| `scripts/dev/run.sh` / `scripts/dev/stop.sh` | WSL dev start/stop | Start/stop Qwen vLLM service and write local config |
| `scripts/deploy/package_offline_docker_bundle.sh` | Offline bundle packaging | Package Qwen vLLM service tar; avoid model/cache/data/logs |
| `deploy/windows/*.bat` | Offline Windows scripts | Import/start/stop/log Qwen vLLM service |
| `docs/部署/GPU-Docker部署.md` | Deployment contract | Replace PaddleOCR/llama.cpp default narrative |
| `docs/Backend/Backend_TDD/02-algorithm-ports.md` | Algorithm port contract | Document shared Qwen vLLM OCR + extraction |
| `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md` | Failure contract | Add Qwen OCR/extraction failure semantics |
| `app/backend/services/copd_extraction/CLAUDE.md` / `AGENTS.md` | Local agent rules | Allow non-record OCR noise filtering; keep no correction/no inference |

---

### Task 1: Add Shared Qwen vLLM Configuration

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/config/local.docker.yaml`
- Modify: `requirements.txt`
- Modify: `requirements.docker.txt`
- Test: `app/backend/tests/test_config.py`
- Test: `app/backend/tests/test_windows_startup_scripts.py`

- [ ] **Step 1: Write the failing test**

Add tests to `app/backend/tests/test_config.py`:

```python
def test_load_config_supports_shared_qwen_vllm_settings(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        """
algorithms:
  enable_local_ocr: true
  enable_copd_extractor: true
  qwen_vllm_server_url: http://qwen-vision-vllm-server:8000/v1
  qwen_vllm_model_name: Qwen3.5-4B-AWQ-4bit
  qwen_vllm_model_dir: ./models/llm/Qwen3.5-4B-AWQ-4bit
  qwen_vllm_max_model_len: 16384
  qwen_vllm_gpu_memory_utilization: 0.85
  qwen_vllm_max_num_seqs: 1
  qwen_ocr_temperature: 0.0
  qwen_ocr_max_tokens: 4096
  qwen_ocr_timeout_seconds: 240
  qwen_extraction_temperature: 0.0
  qwen_extraction_max_tokens: 8192
  qwen_extraction_timeout_seconds: 360
""",
        encoding="utf-8",
    )

    config = load_config(str(config_dir))

    assert config["qwen_vllm_server_url"] == "http://qwen-vision-vllm-server:8000/v1"
    assert config["qwen_vllm_model_name"] == "Qwen3.5-4B-AWQ-4bit"
    assert config["qwen_vllm_model_dir"].endswith("models/llm/Qwen3.5-4B-AWQ-4bit")
    assert config["qwen_vllm_max_model_len"] == 16384
    assert config["qwen_vllm_gpu_memory_utilization"] == 0.85
    assert config["qwen_vllm_max_num_seqs"] == 1
    assert config["qwen_ocr_temperature"] == 0.0
    assert config["qwen_extraction_temperature"] == 0.0
```

Also add:

```python
def test_qwen_vllm_max_model_len_rejects_30000_for_8gb_default(tmp_path):
    from app.backend.config import load_config

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        "algorithms:\n  qwen_vllm_max_model_len: 30000\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="qwen_vllm_max_model_len"):
        load_config(str(config_dir))
```

Add dependency assertions to an existing requirements test or `app/backend/tests/test_windows_startup_scripts.py`:

```python
def test_python_requirements_include_openai_sdk_for_local_vllm():
    assert "openai" in Path("requirements.txt").read_text(encoding="utf-8")
    assert "openai" in Path("requirements.docker.txt").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_supports_shared_qwen_vllm_settings app/backend/tests/test_config.py::test_qwen_vllm_max_model_len_rejects_30000_for_8gb_default app/backend/tests/test_windows_startup_scripts.py::test_python_requirements_include_openai_sdk_for_local_vllm -q
```

Expected: FAIL because `qwen_vllm_*` config keys and `openai` dependency assertions are not implemented.

- [ ] **Step 3: Implement minimal code**

Update `DEFAULT_CONFIG`, `_flatten_config`, `_normalize_paths`, and `_validate_config` in `app/backend/config.py`:

- `qwen_vllm_server_url`: default `http://qwen-vision-vllm-server:8000/v1`
- `qwen_vllm_model_name`: default `Qwen3.5-4B-AWQ-4bit`
- `qwen_vllm_model_dir`: default `./models/llm/Qwen3.5-4B-AWQ-4bit`
- `qwen_vllm_max_model_len`: default `16384`; reject `>=30000`
- `qwen_vllm_gpu_memory_utilization`: default `0.85`; require `0 < value <= 0.95`
- `qwen_vllm_max_num_seqs`: default `1`; require positive integer
- `qwen_ocr_temperature`: default `0.0`; require number `0 <= value <= 2`
- `qwen_ocr_max_tokens`: default `4096`; require positive integer
- `qwen_ocr_timeout_seconds`: default `240`; require positive integer
- `qwen_extraction_temperature`: default `0.0`; require number `0 <= value <= 2`
- `qwen_extraction_max_tokens`: default `8192`; require positive integer
- `qwen_extraction_timeout_seconds`: default `360`; require positive integer

Update `app/config/default.yaml` and `app/config/local.docker.yaml` with the same keys. Keep old `local_ocr_*` keys only if needed for compatibility, but do not use them as the new default path.

Add `openai>=1.0,<2.0` to `requirements.txt` and `requirements.docker.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py::test_load_config_supports_shared_qwen_vllm_settings app/backend/tests/test_config.py::test_qwen_vllm_max_model_len_rejects_30000_for_8gb_default app/backend/tests/test_windows_startup_scripts.py::test_python_requirements_include_openai_sdk_for_local_vllm -q
```

Expected: PASS; config is loaded, 30000 is rejected, and OpenAI SDK dependency is present.

- [ ] **Step 5: Commit**

```bash
git add app/backend/config.py app/config/default.yaml app/config/local.docker.yaml requirements.txt requirements.docker.txt app/backend/tests/test_config.py app/backend/tests/test_windows_startup_scripts.py
git commit -m "新增共享Qwen vLLM配置"
```

---

### Task 2: Add the Shared OpenAI-Compatible vLLM Client

**Files:**
- Create: `app/backend/services/algorithm_ports/qwen_vllm_client.py`
- Test: `app/backend/tests/test_qwen_vllm_client.py`

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_qwen_vllm_client.py` with local fake OpenAI client objects:

```python
from types import SimpleNamespace

import pytest

from app.backend.services.algorithm_ports.qwen_vllm_client import QwenVLLMClient


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
```

Cover:

- `test_qwen_vllm_client_sends_image_url_message_with_local_base_url`
- `test_qwen_vllm_client_sends_text_json_request_with_response_format`
- `test_qwen_vllm_client_strips_think_blocks_from_text`
- `test_qwen_vllm_client_raises_on_timeout_or_empty_response`

Key assertion sketch:

```python
def test_qwen_vllm_client_sends_text_json_request_with_response_format():
    fake = FakeOpenAIClient(content='{"ok": true}')
    client = QwenVLLMClient(
        base_url="http://qwen-vision-vllm-server:8000/v1",
        model="Qwen3.5-4B-AWQ-4bit",
        openai_client=fake,
        timeout_seconds=360,
    )

    result = client.complete_json("fixed field prompt", max_tokens=8192, temperature=0.0)

    assert result == {"ok": True}
    call = fake.chat.completions.calls[-1]
    assert call["model"] == "Qwen3.5-4B-AWQ-4bit"
    assert call["temperature"] == 0.0
    assert call["top_p"] == 1.0
    assert call["max_tokens"] == 8192
    assert call["response_format"] == {"type": "json_object"}
    assert call["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py -q
```

Expected: FAIL because `qwen_vllm_client.py` does not exist.

- [ ] **Step 3: Implement minimal code**

Create `QwenVLLMClient` in `app/backend/services/algorithm_ports/qwen_vllm_client.py`:

- Constructor accepts `base_url`, `model`, optional `openai_client`, `api_key="not-needed"`, `timeout_seconds`.
- If no injected client is given, instantiate `openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_seconds)`.
- `complete_text_from_image(image_path, system_prompt, user_prompt, max_tokens, temperature)` sends one `image_url` data URL plus user text.
- `complete_json(prompt, max_tokens, temperature)` sends text-only prompt and asks for JSON object.
- Add MIME helper for `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`, `.webp`.
- Strip `<think>...</think>` blocks before returning text or parsing JSON.
- Parse JSON with the existing robust logic from `copd_extraction.llm_client` or a shared helper; do not log full prompt, OCR text, image base64, or model output.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py -q
```

Expected: PASS; fake OpenAI calls contain local base URL behavior, image data URL, text JSON request, disabled thinking, and no cloud API key.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/qwen_vllm_client.py app/backend/tests/test_qwen_vllm_client.py
git commit -m "新增Qwen vLLM OpenAI客户端"
```

---

### Task 3: Replace the Default OCR Port With Qwen Vision vLLM

**Files:**
- Create: `app/backend/services/algorithm_ports/qwen_vision_vllm.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/services/algorithm_ports/CLAUDE.md`
- Modify: `app/backend/services/algorithm_ports/AGENTS.md`
- Test: `app/backend/tests/test_qwen_vision_vllm_port.py`
- Test: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_qwen_vision_vllm_port.py`:

```python
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


def test_qwen_vision_port_parses_pages_in_saved_order(tmp_path):
    img1 = tmp_path / "p1.jpg"
    img2 = tmp_path / "p2.jpg"
    img1.write_bytes(b"fake1")
    img2.write_bytes(b"fake2")
    client = FakeQwenClient(["第一页正文", "第二页正文"])
    port = QwenVisionVLLMDocumentPort(
        client=client,
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
    assert client.calls[0]["temperature"] == 0.0
    assert "签名" in client.calls[0]["system_prompt"] or "页眉" in client.calls[0]["system_prompt"]
```

Also cover:

- missing image raises `RuntimeError("OCR 输入图片不存在")`
- empty page output marks only that page failed
- all pages empty causes downstream failure through orchestrator
- events use `backend="qwen_vision_vllm"` and do not include base64 or OCR text

Update `app/backend/tests/test_backend_e2e.py::test_backend_configures_vlm_server_ocr_port` to expect `QwenVisionVLLMDocumentPort`, not `PaddleOCRVLMServerDocumentPort`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vision_vllm_port.py app/backend/tests/test_backend_e2e.py::test_backend_configures_vlm_server_ocr_port -q
```

Expected: FAIL because `QwenVisionVLLMDocumentPort` does not exist and app wiring still uses PaddleOCR.

- [ ] **Step 3: Implement minimal code**

Create `QwenVisionVLLMDocumentPort`:

- Uses injected `QwenVLLMClient`.
- Sorts pages by `page_no`.
- Sends each `processed_path` to `complete_text_from_image`.
- Prompt allows filtering page headers, footers, page numbers, print time, doctor signatures, and handwriting signatures.
- Prompt forbids correction, completion, summary, page reorder, title-specific replacement, and medical inference.
- Returns `pages`, `merged_text`, `source="qwen_vision_vllm"`, `blocks=[]`, `tables=[]`.
- Emits `ocr_vlm_started` and `ocr_vlm_finished` with safe diagnostics.

Modify `app/backend/__init__.py`:

- Import and instantiate `QwenVLLMClient`.
- Pass it to `QwenVisionVLLMDocumentPort`.
- Do not instantiate `PaddleOCRVLMServerDocumentPort` on the default path.

Update `app/backend/services/algorithm_ports/CLAUDE.md` and `AGENTS.md` to list `qwen_vision_vllm.py` as the active default OCR port.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vision_vllm_port.py app/backend/tests/test_backend_e2e.py::test_backend_configures_vlm_server_ocr_port -q
```

Expected: PASS; app configures Qwen OCR port and port returns safe `DocumentResult`.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/qwen_vision_vllm.py app/backend/__init__.py app/backend/services/algorithm_ports/CLAUDE.md app/backend/services/algorithm_ports/AGENTS.md app/backend/tests/test_qwen_vision_vllm_port.py app/backend/tests/test_backend_e2e.py
git commit -m "接入Qwen视觉OCR端口"
```

---

### Task 4: Switch Fixed-Field Extraction to the Same Qwen vLLM Service

**Files:**
- Modify: `app/backend/services/copd_extraction/llm_client.py`
- Modify: `app/backend/services/copd_extraction/port.py`
- Modify: `app/backend/services/copd_extraction/CLAUDE.md`
- Modify: `app/backend/services/copd_extraction/AGENTS.md`
- Test: `app/backend/tests/test_copd_llm_client.py`
- Test: `app/backend/tests/test_copd_field_port.py`
- Test: `app/backend/tests/test_admission_contract.py`

- [ ] **Step 1: Write the failing test**

Update `app/backend/tests/test_copd_llm_client.py` with OpenAI-compatible tests:

```python
class FakeQwenVLLMClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete_json(self, prompt, max_tokens, temperature):
        self.calls.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return self.result


def test_openai_compatible_json_client_uses_qwen_vllm_client():
    from app.backend.services.copd_extraction.llm_client import OpenAICompatibleJsonClient

    fake_qwen = FakeQwenVLLMClient({"schema_version": "admission_record_structured_fields.v1", "fields": []})
    client = OpenAICompatibleJsonClient(fake_qwen, max_tokens=8192, temperature=0.0)

    result = client.complete_json("prompt")

    assert result["schema_version"] == "admission_record_structured_fields.v1"
    assert fake_qwen.calls[-1]["max_tokens"] == 8192
    assert fake_qwen.calls[-1]["temperature"] == 0.0
```

Update `app/backend/tests/test_copd_field_port.py`:

- `test_default_copd_field_port_builds_qwen_vllm_json_client`
- assert `build_default_copd_field_port(config, ...)` no longer requires `llm_model_path`
- assert it uses `qwen_vllm_server_url`, `qwen_vllm_model_name`, `qwen_extraction_max_tokens`, `qwen_extraction_temperature`

Add a regression assertion that `build_default_copd_field_port` does not import or call `build_llama_cpp_client` when no test factory is supplied.

Keep `test_map_qwen_fields_returns_review_candidate_contract_shape`; if dirty, make sure `ocr_correction` default remains.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_llm_client.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_admission_contract.py::test_map_qwen_fields_returns_review_candidate_contract_shape -q
```

Expected: FAIL because default field port still builds llama.cpp and `OpenAICompatibleJsonClient` does not exist.

- [ ] **Step 3: Implement minimal code**

Modify `app/backend/services/copd_extraction/llm_client.py`:

- Keep the `LlmClient` interface and JSON parsing helpers.
- Add `OpenAICompatibleJsonClient(LlmClient)` that wraps `QwenVLLMClient.complete_json`.
- Remove llama.cpp from default builder, or rename it to an explicit non-default compatibility function.
- Remove hard-coded `DEFAULT_LLM_TIMEOUT = 360.0`; use `qwen_extraction_timeout_seconds` through config.

Modify `app/backend/services/copd_extraction/port.py`:

- `_LazyCOPDAdmissionQwenFieldPort` should build `OpenAICompatibleJsonClient` from shared Qwen config by default.
- Keep test injection via `llm_client_factory`.
- `COPDAdmissionQwenFieldPort` remains the fixed-field prompt/contract adapter.

Update `CLAUDE.md` and `AGENTS.md`:

- Default extraction now uses Qwen vLLM OpenAI-compatible client.
- OCR output may filter non-record headers/footers/signatures, but no correction or inference is allowed.
- Remove the stale “raw OCR must be complete” wording.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_copd_llm_client.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_admission_contract.py::test_map_qwen_fields_returns_review_candidate_contract_shape -q
```

Expected: PASS; fixed-field extraction uses Qwen vLLM client and candidate contract still validates.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/copd_extraction/llm_client.py app/backend/services/copd_extraction/port.py app/backend/services/copd_extraction/CLAUDE.md app/backend/services/copd_extraction/AGENTS.md app/backend/tests/test_copd_llm_client.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_admission_contract.py
git commit -m "切换固定字段抽取到Qwen vLLM"
```

---

### Task 5: Hold One GPU Queue Stage Across OCR And Extraction

**Files:**
- Modify: `app/backend/services/algorithm_ports/orchestrator.py`
- Test: `app/backend/tests/test_orchestrator.py`
- Test: `app/backend/tests/test_gpu_stage_queue.py`

- [ ] **Step 1: Write the failing test**

Add `app/backend/tests/test_orchestrator.py::test_orchestrator_holds_single_gpu_stage_across_ocr_and_field_extraction`:

```python
def test_orchestrator_holds_single_gpu_stage_across_ocr_and_field_extraction(tmp_path):
    events = []

    class RecordingContext:
        def __init__(self, events, stage):
            self.events = events
            self.stage = stage

        def __enter__(self):
            self.events.append(f"enter:{self.stage}")
            return self

        def __exit__(self, exc_type, exc, tb):
            self.events.append(f"exit:{self.stage}")
            return False

    class RecordingQueue:
        def stage(self, task_id, stage):
            return RecordingContext(events, stage)

    class ImagePort:
        def process(self, input):
            return {"processed_path": input["original_path"]}

    class DocPort:
        def parse(self, input):
            events.append("doc_inside_stage")
            return {"pages": [{"page_id": "p1", "page_no": 1, "status": "success", "text": "主诉：咳嗽"}], "merged_text": "主诉：咳嗽"}

    class FieldPort:
        def extract(self, input):
            events.append("field_inside_stage")
            return _build_full_qwen_candidates_with_statuses({"chief_complaint": "found"})

    class TaskService:
        def mark_processing_stage(self, task_id, stage, status, page_count=None):
            return {}

        def mark_ready(self, task_id):
            return {"task_id": task_id, "status": "review"}

        def mark_failed(self, *args, **kwargs):
            raise AssertionError("should not fail")

        def is_processing_cancelled(self, task_id):
            return False

    source = tmp_path / "page.jpg"
    source.write_text("image", encoding="utf-8")
    orchestrator = ProcessingOrchestrator(
        store=JsonStore(str(tmp_path)),
        image_port=ImagePort(),
        doc_port=DocPort(),
        field_port=FieldPort(),
        gpu_stage_queue=RecordingQueue(),
    )

    result = orchestrator.run(
        {
            "task_id": "task_001",
            "images": [{"page_id": "page_001", "page_no": 1, "original_image_path": str(source)}],
        },
        TaskService(),
        schema={"fields": [{"field_key": "chief_complaint"}]},
    )

    assert result["status"] == "review"
    assert events == [
        "enter:qwen_ocr_and_extraction",
        "doc_inside_stage",
        "field_inside_stage",
        "exit:qwen_ocr_and_extraction",
    ]
```

Add `test_orchestrator_with_cached_document_result_only_holds_field_stage`:

- Prewrite successful `document_result.json`.
- Assert OCR `DocPort.parse` is not called.
- Assert queue stage is `field_extraction` or `qwen_field_extraction_retry`, not full OCR+extraction.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py::test_orchestrator_holds_single_gpu_stage_across_ocr_and_field_extraction app/backend/tests/test_orchestrator.py::test_orchestrator_with_cached_document_result_only_holds_field_stage -q
```

Expected: FAIL because orchestrator currently releases the queue after document parsing and reacquires for field extraction.

- [ ] **Step 3: Implement minimal code**

Refactor `ProcessingOrchestrator.run()`:

- Keep image processing outside GPU queue.
- If no successful cached document result exists, acquire `self._gpu_stage(task_id, "qwen_ocr_and_extraction")` once.
- Inside that context:
  - run document parsing
  - validate and persist `document_result.json`
  - generate and persist `evidence_units`
  - run fixed-field extraction
  - persist field candidates
- Use `try/finally` through the existing queue context so errors release the lock.
- If a successful cached `document_result.json` exists, skip OCR and acquire only `field_extraction` for fixed-field extraction.

Do not change task failure semantics: OCR failures fail at `document_parsing`; extraction failures fail at `field_extraction`; mixed `not_found` fields enter review if at least one valid field is found.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py::test_orchestrator_holds_single_gpu_stage_across_ocr_and_field_extraction app/backend/tests/test_orchestrator.py::test_orchestrator_with_cached_document_result_only_holds_field_stage app/backend/tests/test_gpu_stage_queue.py -q
```

Expected: PASS; one task cannot be interrupted between OCR and extraction, while retry with cached OCR skips OCR.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/algorithm_ports/orchestrator.py app/backend/tests/test_orchestrator.py app/backend/tests/test_gpu_stage_queue.py
git commit -m "串行持有Qwen OCR与抽取队列"
```

---

### Task 6: Update Event Logging Privacy For Shared Qwen Runtime

**Files:**
- Modify: `app/backend/services/local_event_log.py`
- Modify: `app/backend/tests/test_local_event_log.py`
- Modify: `app/backend/tests/test_logging_integration.py`

- [ ] **Step 1: Write the failing test**

Add tests:

- `test_writes_qwen_vllm_ocr_events_without_text_or_base64`
- `test_writes_qwen_vllm_extraction_events_without_prompt_or_output`

Expected payload keys:

- OCR: `backend`, `server_url`, `model`, `page_count`, `timeout_seconds`, `temperature`, `max_tokens`, `top_p`, `input_files`, `failed_page_count`
- Extraction: `backend`, `server_url`, `model`, `schema_version`, `field_count`, `evidence_unit_count`, `timeout_seconds`, `temperature`, `max_tokens`, `elapsed_ms`, `exit_code`, `reason`

Assert disallowed keys are removed or absent: `ocr_text`, `merged_text`, `prompt`, `model_output`, `image_base64`, `patient_name`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_local_event_log.py::TestLocalEventLog::test_writes_qwen_vllm_ocr_events_without_text_or_base64 app/backend/tests/test_local_event_log.py::TestLocalEventLog::test_writes_qwen_vllm_extraction_events_without_prompt_or_output -q
```

Expected: FAIL because allowlist lacks shared Qwen extraction diagnostics.

- [ ] **Step 3: Implement minimal code**

Update `SAFE_EVENT_FIELDS` in `local_event_log.py`:

- Keep `ocr_vlm_started` / `ocr_vlm_finished`, allow `backend="qwen_vision_vllm"`.
- Add `llm_extraction_started` and `llm_extraction_finished` or update existing extraction event allowlists.
- Allow only diagnostic counts, durations, model name, schema version, and failure reason.
- Do not allow OCR text, prompt, evidence text, image base64, or model response content.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_local_event_log.py app/backend/tests/test_logging_integration.py -q
```

Expected: PASS; Qwen events are useful for diagnostics but do not leak patient text.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/local_event_log.py app/backend/tests/test_local_event_log.py app/backend/tests/test_logging_integration.py
git commit -m "完善Qwen运行日志隐私"
```

---

### Task 7: Replace Docker Compose And Dev Scripts

**Files:**
- Modify: `docker-compose.yml`
- Modify: `scripts/dev/run.sh`
- Modify: `scripts/dev/stop.sh`
- Modify: `app/backend/tests/test_windows_startup_scripts.py`
- Modify: `scripts/checks/offline_startup_check.py`

- [ ] **Step 1: Write the failing test**

Replace old PaddleOCR script assertions in `app/backend/tests/test_windows_startup_scripts.py`:

- `test_docker_compose_defines_qwen_vision_vllm_server`
  - expects service `qwen-vision-vllm-server`
  - expects image/tag variable for vLLM, not `paddleocr-genai-vllm-server`
  - expects command contains `--model /workspace/model/llm/Qwen3.5-4B-AWQ-4bit`
  - expects `--max-model-len ${QWEN_VLLM_MAX_MODEL_LEN:-16384}`
  - expects `--gpu-memory-utilization ${QWEN_VLLM_GPU_MEMORY_UTILIZATION:-0.85}`
  - expects `--max-num-seqs ${QWEN_VLLM_MAX_NUM_SEQS:-1}`
  - expects `--enable-chunked-prefill`, `--enable-prefix-caching`, `--dtype auto`, `--trust-remote-code`
  - expects port `127.0.0.1:8082:8000`
  - expects model mount `models/llm:/workspace/model/llm:ro`
  - expects healthcheck `curl -sf http://localhost:8000/v1/models`
- `test_wsl_run_script_starts_qwen_vllm_server`
- `test_wsl_stop_script_stops_qwen_vllm_server`
- Update or remove assertions that require `paddleocr-vlm-server`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py::test_docker_compose_defines_qwen_vision_vllm_server app/backend/tests/test_windows_startup_scripts.py::test_wsl_run_script_starts_qwen_vllm_server app/backend/tests/test_windows_startup_scripts.py::test_wsl_stop_script_stops_qwen_vllm_server -q
```

Expected: FAIL because compose and scripts still use `paddleocr-vlm-server`.

- [ ] **Step 3: Implement minimal code**

Update `docker-compose.yml`:

- Replace `paddleocr-vlm-server` service with `qwen-vision-vllm-server`.
- Use a fixed local tag variable such as `qwen-vllm-openai:verified`.
- Command uses vLLM OpenAI server args from the spec.
- Mount `./models/llm:/workspace/model/llm:ro`.
- Mount `./vllm_cache:/root/.cache/vllm` or a deploy-local cache path; ensure cache is ignored and not packaged as source.
- Keep `manzufei-ocr` depending on service health.

Update `scripts/dev/run.sh`:

- Use `QWEN_VLLM_MODEL_DIR="$ROOT_DIR/models/llm/Qwen3.5-4B-AWQ-4bit"`.
- Write local config with `qwen_vllm_server_url: "http://127.0.0.1:8082/v1"`.
- Start `docker compose up -d qwen-vision-vllm-server`.
- Wait on `http://127.0.0.1:8082/v1/models`.

Update `scripts/dev/stop.sh` to stop `qwen-vision-vllm-server`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py::test_docker_compose_defines_qwen_vision_vllm_server app/backend/tests/test_windows_startup_scripts.py::test_wsl_run_script_starts_qwen_vllm_server app/backend/tests/test_windows_startup_scripts.py::test_wsl_stop_script_stops_qwen_vllm_server -q
```

Expected: PASS; dev runtime uses Qwen vLLM service and no default PaddleOCR service.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml scripts/dev/run.sh scripts/dev/stop.sh scripts/checks/offline_startup_check.py app/backend/tests/test_windows_startup_scripts.py
git commit -m "替换开发运行的Qwen vLLM服务"
```

---

### Task 8: Update Offline Packaging And Windows Scripts

**Files:**
- Modify: `scripts/deploy/package_offline_docker_bundle.sh`
- Modify: `deploy/windows/00_import_image.bat`
- Modify: `deploy/windows/01_start.bat`
- Modify: `deploy/windows/02_stop.bat`
- Modify: `deploy/windows/03_logs.bat`
- Modify: `deploy/offline-images/README.md`
- Modify: `deploy/windows/README_DEPLOY.txt`
- Modify: `app/backend/tests/test_windows_startup_scripts.py`

- [ ] **Step 1: Write the failing test**

Add/replace tests:

- `test_offline_bundle_script_defines_qwen_vllm_image_and_tar`
  - expects `QWEN_VLLM_SERVER_IMAGE`
  - expects `QWEN_VLLM_SERVER_LOCAL_TAG`
  - expects `qwen-vllm-server.tar`
  - expects no default `paddleocr-vlm-server.tar`
- `test_windows_import_script_loads_qwen_vllm_server_tar`
- `test_windows_start_script_checks_qwen_vllm_models_endpoint`
- `test_windows_stop_script_stops_qwen_vllm_server`

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py::test_offline_bundle_script_defines_qwen_vllm_image_and_tar app/backend/tests/test_windows_startup_scripts.py::test_windows_import_script_loads_qwen_vllm_server_tar app/backend/tests/test_windows_startup_scripts.py::test_windows_start_script_checks_qwen_vllm_models_endpoint app/backend/tests/test_windows_startup_scripts.py::test_windows_stop_script_stops_qwen_vllm_server -q
```

Expected: FAIL because offline scripts still import and check PaddleOCR VLM.

- [ ] **Step 3: Implement minimal code**

Update packaging:

- Use Qwen vLLM image variables.
- Save/load `images/qwen-vllm-server.tar`.
- Do not package `models/llm/Qwen3.5-4B-AWQ-4bit/`, `vllm_cache/`, `data/`, `exports/`, or `logs/`.
- Preserve fixed image source policy; do not rely on floating `latest` for formal offline bundle.

Update Windows scripts:

- `00_import_image.bat` loads `qwen-vllm-server.tar`.
- `01_start.bat` checks Docker GPU and `http://127.0.0.1:8082/v1/models`.
- Remove llama.cpp CUDA wheel diagnostics from default startup checks unless kept as explicit legacy diagnostics.
- `02_stop.bat` stops `qwen-vision-vllm-server`.
- `03_logs.bat` includes Qwen service logs.

Update deploy READMEs to describe model placement under `models\llm\Qwen3.5-4B-AWQ-4bit\`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py -q
```

Expected: PASS; Windows/offline assertions now describe Qwen vLLM service.

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy/package_offline_docker_bundle.sh deploy/windows/00_import_image.bat deploy/windows/01_start.bat deploy/windows/02_stop.bat deploy/windows/03_logs.bat deploy/offline-images/README.md deploy/windows/README_DEPLOY.txt app/backend/tests/test_windows_startup_scripts.py
git commit -m "更新离线包Qwen vLLM脚本"
```

---

### Task 9: Clean Old Default Runtime Paths And Docs

**Files:**
- Modify: `Dockerfile`
- Modify: `requirements.docker.txt`
- Modify: `docs/部署/GPU-Docker部署.md`
- Modify: `docs/部署/离线验收记录.md`
- Modify: `docs/Backend/Backend_TDD/02-algorithm-ports.md`
- Modify: `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`
- Modify: `deploy/CLAUDE.md`
- Modify: `deploy/AGENTS.md`
- Modify: `app/backend/services/algorithm_ports/CLAUDE.md`
- Modify: `app/backend/services/algorithm_ports/AGENTS.md`
- Modify: `app/backend/services/copd_extraction/CLAUDE.md`
- Modify: `app/backend/services/copd_extraction/AGENTS.md`
- Test: `app/backend/tests/test_windows_startup_scripts.py`
- Test: `app/backend/tests/test_legacy_cleanup.py`

- [ ] **Step 1: Write the failing test**

Add or update these cleanup tests in `app/backend/tests/test_legacy_cleanup.py`:

```python
def test_default_runtime_docs_do_not_claim_paddleocr_or_llamacpp_are_required():
    paths = [
        Path("docs/部署/GPU-Docker部署.md"),
        Path("docs/Backend/Backend_TDD/02-algorithm-ports.md"),
        Path("deploy/CLAUDE.md"),
        Path("deploy/AGENTS.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "paddleocr-vlm-server.tar" not in combined
    assert "sha256:1cee5e7e26e666bcd80d2a9741c450438bf507268cbfb14e0e0d33b8d5259621" not in combined
    assert "必须把 `llama-cpp-python==0.3.22` 编译为 CUDA wheel" not in combined
```

Add:

```python
def test_dockerfile_does_not_compile_llama_cpp_for_default_runtime():
    content = Path("Dockerfile").read_text(encoding="utf-8")
    assert "llama-cpp-python==0.3.22" not in content
    assert "GGML_CUDA=on" not in content
```

Update `app/backend/tests/test_legacy_cleanup.py` so it asserts:

- no active default schema references old `copd_admission_record.v1.yaml`
- no active default code path imports `PaddleOCRVLMServerDocumentPort`
- no active default code path calls `build_llama_cpp_client`
- old free-key prompt names are absent from active prompt tests

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_legacy_cleanup.py::test_default_runtime_docs_do_not_claim_paddleocr_or_llamacpp_are_required app/backend/tests/test_legacy_cleanup.py::test_dockerfile_does_not_compile_llama_cpp_for_default_runtime -q
```

Expected: FAIL because docs and Dockerfile still describe PaddleOCR VLM and llama.cpp as default requirements.

- [ ] **Step 3: Implement minimal code**

Update docs:

- Qwen vLLM is default OCR + fixed-field extraction service.
- Model path: `models/llm/Qwen3.5-4B-AWQ-4bit/`.
- OCR may filter non-record headers/footers/signatures; no correction, inference, title replacement, or page reorder.
- Fixed-field evidence contract remains 2026-06-18.
- `not_found` remains normal.
- Offline acceptance checks `/v1/models` on `qwen-vision-vllm-server`.

Update `Dockerfile` and `requirements.docker.txt`:

- Remove default llama.cpp CUDA compile step if not used.
- Remove PaddleOCR/PaddleX dependencies if no default backend imports them.
- Keep only backend dependencies needed for Flask, YAML, OpenAI SDK, tests/build, and existing app.

If any legacy file remains for reference, document that it is not reachable from current `copd_admission_record` profile and not part of default runtime.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_legacy_cleanup.py app/backend/tests/test_windows_startup_scripts.py -q
```

Expected: PASS; default runtime docs and tests no longer require PaddleOCR or llama.cpp.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile requirements.docker.txt docs/部署/GPU-Docker部署.md docs/部署/离线验收记录.md docs/Backend/Backend_TDD/02-algorithm-ports.md docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md deploy/CLAUDE.md deploy/AGENTS.md app/backend/services/algorithm_ports/CLAUDE.md app/backend/services/algorithm_ports/AGENTS.md app/backend/services/copd_extraction/CLAUDE.md app/backend/services/copd_extraction/AGENTS.md app/backend/tests/test_legacy_cleanup.py app/backend/tests/test_windows_startup_scripts.py
git commit -m "清理旧默认模型运行契约"
```

---

### Task 10: Final Integration Verification

**Files:**
- Modify only if previous tasks reveal missing docs or broken test references.

- [ ] **Step 1: Run focused backend verification**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_qwen_vllm_client.py app/backend/tests/test_qwen_vision_vllm_port.py app/backend/tests/test_copd_llm_client.py app/backend/tests/test_copd_field_port.py app/backend/tests/test_orchestrator.py app/backend/tests/test_gpu_stage_queue.py app/backend/tests/test_config.py app/backend/tests/test_local_event_log.py app/backend/tests/test_windows_startup_scripts.py app/backend/tests/test_legacy_cleanup.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend test suite**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS. If unrelated pre-existing failures appear, record exact failing tests and do not mask them.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
npm --prefix app/frontend run test -- --run
npm --prefix app/frontend run typecheck
```

Expected: PASS. This migration should not require frontend behavior changes beyond what 2026-06-18 already implemented.

- [ ] **Step 4: Run repository hygiene checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. `git status --short` should show only intended tracked changes before the final commit, and no `data/`, `exports/`, `logs/`, model weights, vLLM cache, tar files, or local private config paths staged.

- [ ] **Step 5: Commit final verification docs if needed**

If Task 10 required doc or test-reference fixes, commit exactly the files changed by this verification step. For this plan, the expected allowed file set is limited to:

- `docs/部署/GPU-Docker部署.md`
- `docs/部署/离线验收记录.md`
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`
- `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`
- `app/backend/tests/test_legacy_cleanup.py`
- `app/backend/tests/test_windows_startup_scripts.py`

Run `git status --short`, confirm no `data/`, `exports/`, `logs/`, model, cache, Docker tar, local config, or secret files are present, then stage only the matching files that actually changed. Example when only docs changed:

```bash
git add docs/部署/GPU-Docker部署.md docs/部署/离线验收记录.md docs/Backend/Backend_TDD/02-algorithm-ports.md docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md
git commit -m "完善Qwen vLLM迁移验证"
```

Expected: no commit if Task 10 only ran verification and changed no files.

---

## Final Verification

Run from the execution worktree after all task commits:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
npm --prefix app/frontend run test -- --run
npm --prefix app/frontend run typecheck
git diff --check
git status --short
```

Expected:

- Backend tests pass.
- Frontend tests and typecheck pass.
- `git diff --check` has no output.
- `git status --short` shows a clean worktree after the final task commit.
- No `data/`, `exports/`, `logs/`, model weights, vLLM cache, Docker image tar files, local private paths, or secrets are staged or committed.

## Execution Handoff Prompt

```text
请在 `/home/kbzz1/manzufei_ocr` 中执行 Qwen Vision vLLM OCR + 固定字段抽取迁移。不要在 `master` 直接实现。

Spec: `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-vision-vllm-ocr/docs/superpowers/specs/2026-06-20-qwen-vision-vllm-ocr-extraction-design.md`
Plan: `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-vision-vllm-ocr/docs/superpowers/plans/2026-06-20-qwen-vision-vllm-ocr-extraction-implementation-plan.md`

要求：
- 先读取 `AGENTS.md` / `CLAUDE.md` / `docs/AGENTS.md` / `app/backend/CLAUDE.md`，进入 `app/backend/services/algorithm_ports/`、`app/backend/services/copd_extraction/`、`deploy/`、`scripts/` 时再读取对应 `CLAUDE.md` / `AGENTS.md`。
- 使用 Superpowers：`superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。
- 执行基线是 `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-structured-fields`，执行 worktree 使用 `/home/kbzz1/manzufei_ocr/.claude/worktrees/qwen-admission-vllm-runtime`，分支使用 `qwen-admission-vllm-runtime`。
- 开始 Task 1 前先执行 plan 的 `Execution Baseline`：检查 6-18 worktree dirty diff；保留 `admission_contract.py` 和 `test_admission_contract.py` 里的 `ocr_correction` 契约修正；不要把 `llm_client.py` 的临时 `DEFAULT_LLM_TIMEOUT = 360.0` 作为基线代码带入。
- 如果执行 worktree 已存在但不干净，先停止并报告 dirty 路径，不要覆盖或清理用户改动。
- 严格按 plan task-by-task 执行；每个任务先写失败测试，再运行确认失败，再做最小实现，再跑测试通过。
- 每个任务完成后单独 commit，commit message 使用中文。
- 不要修改与计划无关的文件；不要回滚、删除或清理当前工作区已有改动。
- 不要提交 `data/`、`exports/`、`logs/` 中的真实运行数据、模型权重、vLLM cache、Docker tar、日志、本机私有路径或密钥。
- 不要迁移桌面 qwen 的批处理归档、动态 schema、逗号级单 evidence_id、移动原图流程或真实输出样本。
- OCR 可过滤页眉、页脚、页码、打印时间、医生签名、手签等非正文干扰，但禁止纠正文书正文、补全、重排、标题字符串替换和医学推理。
- OCR 与固定字段抽取必须使用同一个本地 `qwen-vision-vllm-server`，后端通过 OpenAI SDK 调本地 `/v1`，不接云 API。
- 同一任务必须连续持有 GPU 队列完成 OCR 和固定字段抽取；已有合法 `document_result.json` 的重试只重跑固定字段抽取。
- 默认路径不能继续冷启动独立 llama.cpp/GGUF 模型，不能继续使用 PaddleOCR VLM 容器作为默认 OCR 服务。
- 最后运行 plan 的 Final Verification 命令，并报告通过项和无法运行项及原因。

开始执行前，先复述你将执行的 Execution Baseline、Task 1、涉及文件、验证命令和 expected result。
```
