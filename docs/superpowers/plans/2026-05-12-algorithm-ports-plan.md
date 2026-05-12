# 外部算法端口编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 定义并接入图像处理、文档解析、字段抽取三个外部本地算法端口，让任务处理成功时进入 `ready_for_review`，任一端口缺失、异常、空结构化字段或契约非法时进入 `failed` 并保存明确失败摘要。

**Architecture:** 新增 `app/backend/services/algorithm_ports/` 包，端口类只声明调用契约，`ProcessingOrchestrator` 负责按 `image_processing -> document_parsing -> field_extraction` 编排、校验最小返回结构、持久化外部返回结果并委托 `TaskService.mark_failed()` / `mark_ready()` 更新状态。`TaskService.process()` 和 `retry()` 只负责合法状态流转、清理旧失败信息、记录 schema 元信息并委托编排器，不再硬编码算法未配置失败。Fixture 适配器只返回测试预置结构或抛测试预置异常，不读取图片、不解析 OCR 文本、不根据 schema 或规则生成字段。

**Tech Stack:** Python 3, Flask app factory, pytest, `JsonStore`, 现有 `TaskStatus` / `AppError` / `ErrorCode`。

---

## 权威依据

- `docs/产品PRD.md`: PR-BE-004、PR-BE-005、PR-BE-006、PR-BE-011；算法能力由外部本地模块提供，失败必须进入 `failed`。
- `docs/PRD任务清单.md`: BE-05 外部算法端口；BE-06 schema 管理并行，BE-05 不实现 schema 白名单规则。
- `docs/Shared/state-enums.md`: `processing -> ready_for_review | failed`，`failed -> processing`。
- `docs/Shared/error-codes.md`: `ALGORITHM_MODULE_NOT_CONFIGURED`、`ALGORITHM_MODULE_FAILED`、`ALGORITHM_CONTRACT_INVALID` 是任务失败错误码，不是常规 HTTP 错误响应码。
- `docs/Shared/terminology.md`: 算法模块是外部交付的图像处理 + OCR + LLM 模块。
- `app/README.md`、`app/backend/README.md`: 后端只做 API、状态、持久化和外部算法端口编排。
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`、`07-algorithm-failure-contracts.md`: 端口契约和失败契约。
- `docs/Backend/Backend_BDD/algorithm-integration.md`: 用户可观察失败行为和成功结果持久化行为。
- `docs/superpowers/specs/2026-05-12-algorithm-ports-design.md`: 本计划的直接设计来源。

## 并行执行与合并边界

BE-05 可以与 BE-06 Schema Loader 并行执行，但必须按以下边界保持无缝合并：

- BE-05 拥有 `app/backend/services/algorithm_ports/`、`TaskService.process()` / `retry()` 委托、算法失败映射和 `results/{task_id}/` 持久化。
- BE-05 不创建 `app/config/schemas/medical_record.v1.yaml`，不实现 `SchemaService`，不读取 schema 文件，不构造默认 schema。
- BE-05 字段候选结构校验只检查 `field_key`、`original_value`、`confidence`、`evidence` 的基础契约；schema 外字段、重复字段等白名单语义由 BE-06 的 `SchemaValidator` 处理。
- 两个分支都会修改 `app/backend/__init__.py`。合并时保留两块装配：BE-05 的 `ProcessingOrchestrator`/`TASK_SERVICE`，BE-06 的 `SCHEMA_SERVICE`/schema route。不要用一方整文件覆盖另一方。
- 推荐合并顺序：先合并 BE-06，再合并 BE-05。BE-05 合并时把 `SchemaService.get_current()` 返回的 dict 传入处理入口，把 `SchemaService.build_validator()` 注入 orchestrator。
- 如果必须先合并 BE-05，BE-05 使用测试显式传入的 schema dict 保持通过；BE-06 合并后只做 app factory 或 route 层装配补丁接入 `SchemaService`，不能把 schema loader 复制进 BE-05。
- 并行执行期间统一使用 conda 环境 `manzufei_ocr` 运行测试命令。

## 非目标和硬边界

本计划只允许实现：

- 外部算法端口接口。
- 端口调用编排。
- 端口返回结构的最小契约校验。
- 失败映射、任务状态、失败摘要和状态历史。
- 外部模块成功返回结果的原样持久化。
- 测试 fixture 适配器。

本计划禁止实现：

- OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正、去摩尔纹、去反光、自动边界识别。
- 基于 OCR 文本、schema、字段名、正则、模板或页面内容生成字段候选。
- 算法失败后的人工补录降级路径、空成功结果、可审核的空字段集合。
- 运行时联网下载模型、调用云 API、上传遥测。
- 在日志、失败 details 或测试 fixture 中保存完整病历原文、身份证号、图片 base64、模型输出全文或调用堆栈。

## 文件结构

- Create: `app/backend/services/algorithm_ports/__init__.py`
  - 导出端口接口、编排器、字段候选结构校验。
- Create: `app/backend/services/algorithm_ports/image_processing.py`
  - `ImageProcessingPort.process(input: dict) -> dict`，只定义接口。
- Create: `app/backend/services/algorithm_ports/document_parsing.py`
  - `DocumentParsingPort.parse(input: dict) -> dict`，只定义接口。
- Create: `app/backend/services/algorithm_ports/field_extraction.py`
  - `FieldExtractionPort.extract(input: dict) -> list[dict]` 和 `validate_field_candidates()`。
- Create: `app/backend/services/algorithm_ports/orchestrator.py`
  - `ProcessingOrchestrator` 编排三阶段、写 `results/{task_id}/`、映射失败。
- Create: `app/backend/services/algorithm_ports/fixtures.py`
  - 测试用 fixture，只返回构造函数传入的预置值或抛异常。
- Modify: `app/backend/errors.py`
  - 将三个算法错误码补入 `ErrorCode`，保留 `AlgorithmErrorCode` 兼容既有测试。
- Modify: `app/backend/services/task_service.py`
  - 注入 orchestrator；`process()` / `retry()` 委托；`mark_failed()` 增加 `stage` 和 `details`。
- Modify: `app/backend/__init__.py`
  - app factory 创建 `ProcessingOrchestrator(store=store)` 并注入 `TaskService`。
- Test: `app/backend/tests/test_field_extraction_port.py`
- Test: `app/backend/tests/test_orchestrator.py`
- Test: `app/backend/tests/test_image_processing_port.py`
- Test: `app/backend/tests/test_document_parsing_port.py`
- Modify Test: `app/backend/tests/test_task_service.py`
- Modify Test: `app/backend/tests/test_task_routes.py`

## 数据和状态契约

任务本体仍在 `tasks/{task_id}.json`，只保存任务状态、时间、失败摘要和页面顺序。算法中间结果写入 `results/{task_id}/`：

- `image_result.json`: 外部图像处理端口成功返回的 `processed_path`，附带原图路径、页号、`quad_points`。
- `document_result.json`: 外部文档解析端口返回的 `pages`、`blocks`、`tables`、`merged_text`，原样持久化。
- `field_candidates.json`: 外部字段抽取端口返回的候选字段，原样持久化。

`ready_for_review` 只能在三个阶段全部成功、字段候选非空且契约合法后进入。以下情况必须进入 `failed`：

| 场景 | 状态 | error_code | details.stage | details.reason |
|------|------|------------|---------------|----------------|
| 图像处理端口未配置 | `failed` | `ALGORITHM_MODULE_NOT_CONFIGURED` | `image_processing` | `module_not_configured` |
| 页面元数据缺失或非法 | `failed` | `ALGORITHM_CONTRACT_INVALID` | `image_processing` | `page_metadata_missing` |
| 图像处理端口异常 | `failed` | `ALGORITHM_MODULE_FAILED` | `image_processing` | `module_exception` |
| 图像处理返回缺少非空 `processed_path` | `failed` | `ALGORITHM_CONTRACT_INVALID` | `image_processing` | `invalid_processed_path` |
| 文档解析端口未配置 | `failed` | `ALGORITHM_MODULE_NOT_CONFIGURED` | `document_parsing` | `module_not_configured` |
| 文档解析端口异常 | `failed` | `ALGORITHM_MODULE_FAILED` | `document_parsing` | `module_exception` |
| 文档解析返回非 dict 或缺少 list `pages` | `failed` | `ALGORITHM_CONTRACT_INVALID` | `document_parsing` | `invalid_document_result` |
| 文档解析返回空 `pages` | `failed` | `ALGORITHM_CONTRACT_INVALID` | `document_parsing` | `empty_pages` |
| 任一解析页 `status == "failed"` | `failed` | `ALGORITHM_MODULE_FAILED` | `document_parsing` | `partial_page_failed` |
| 字段抽取端口未配置 | `failed` | `ALGORITHM_MODULE_NOT_CONFIGURED` | `field_extraction` | `module_not_configured` |
| schema 缺失或不是 dict | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `schema_missing_or_invalid` |
| 字段抽取端口异常 | `failed` | `ALGORITHM_MODULE_FAILED` | `field_extraction` | `module_exception` |
| 字段候选不是 list | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `invalid_candidate_contract` |
| 字段候选为空 list | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `empty_candidates` |
| 候选缺少非空字符串 `field_key` | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `invalid_candidate_contract` |
| 候选缺少字符串 `original_value` | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `invalid_candidate_contract` |
| 候选 `confidence` 存在但不是数字 | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `invalid_candidate_contract` |
| 候选 `evidence` 存在但不是字符串或 null | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `invalid_candidate_contract` |
| 注入的 schema validator 拒绝候选 | `failed` | `ALGORITHM_CONTRACT_INVALID` | `field_extraction` | `schema_validation_failed` |

BE-05 不校验 `field_key` 是否属于 schema；该校验属于 BE-06 或注入的 `schema_validator`。如果没有注入 validator，schema 外字段不会在 BE-05 被拒绝，但仍必须满足字段候选结构契约。

## Task 0: 确认 BE-04 基线

**Files:**
- Read: `app/backend/services/task_service.py`
- Read: `app/backend/tests/test_task_service.py`
- Read: `app/backend/tests/test_task_routes.py`

- [ ] **Step 1: 运行任务生命周期基线测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS。若失败，先停止执行本计划并把失败用例交给主 agent 协调，因为 BE-05 依赖 BE-04 的 `process`、`retry`、`mark_failed`、`mark_ready`。

## Task 1: 端口接口和字段候选结构校验

**Files:**
- Modify: `app/backend/errors.py`
- Create: `app/backend/services/algorithm_ports/__init__.py`
- Create: `app/backend/services/algorithm_ports/image_processing.py`
- Create: `app/backend/services/algorithm_ports/document_parsing.py`
- Create: `app/backend/services/algorithm_ports/field_extraction.py`
- Test: `app/backend/tests/test_field_extraction_port.py`

- [ ] **Step 1: 写字段候选结构校验测试**

`app/backend/tests/test_field_extraction_port.py` 必须覆盖以下断言：

```python
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.algorithm_ports.field_extraction import validate_field_candidates


def test_valid_candidates_pass():
    validate_field_candidates([
        {"field_key": "chief_complaint", "original_value": "头痛3天", "confidence": 0.95},
        {"field_key": "name", "original_value": "张三", "evidence": None},
    ])


@pytest.mark.parametrize("payload", [
    {"field_key": "chief_complaint"},
    ["not-a-dict"],
    [{"original_value": "x"}],
    [{"field_key": "", "original_value": "x"}],
    [{"field_key": 123, "original_value": "x"}],
    [{"field_key": "k"}],
    [{"field_key": "k", "original_value": 123}],
    [{"field_key": "k", "original_value": "x", "confidence": "high"}],
    [{"field_key": "k", "original_value": "x", "evidence": 42}],
])
def test_invalid_candidates_raise_contract_invalid(payload):
    with pytest.raises(AppError) as exc_info:
        validate_field_candidates(payload)
    assert exc_info.value.code == ErrorCode.ALGORITHM_CONTRACT_INVALID.code


def test_extra_fields_are_allowed():
    validate_field_candidates([
        {"field_key": "k", "original_value": "x", "unknown_external_attr": {"raw": True}},
    ])
```

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py -q
```

Expected: FAIL，导入 `app.backend.services.algorithm_ports` 或 `validate_field_candidates` 失败。

- [ ] **Step 3: 对齐算法错误码**

在 `app/backend/errors.py` 的 `ErrorCode` 中增加：

```python
ALGORITHM_MODULE_NOT_CONFIGURED = ("ALGORITHM_MODULE_NOT_CONFIGURED", 500, "算法模块未配置")
ALGORITHM_MODULE_FAILED = ("ALGORITHM_MODULE_FAILED", 500, "外部算法模块异常")
ALGORITHM_CONTRACT_INVALID = ("ALGORITHM_CONTRACT_INVALID", 500, "外部算法模块返回结构不符合契约")
```

保留现有 `AlgorithmErrorCode`，避免破坏已完成 BE-04 测试。正常 BE-05 流程由编排器捕获算法错误并写入任务本体；这些 `ErrorCode` 只用于结构校验异常或意外冒泡时保持统一错误对象。

- [ ] **Step 4: 实现三个端口接口和字段候选校验**

接口类只抛 `NotImplementedError`。`validate_field_candidates()` 只能校验 list/dict/字段类型，不读取 schema，不检查字段是否属于 schema。

- [ ] **Step 5: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_field_extraction_port.py app/backend/tests/test_errors.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add app/backend/errors.py app/backend/services/algorithm_ports/__init__.py app/backend/services/algorithm_ports/image_processing.py app/backend/services/algorithm_ports/document_parsing.py app/backend/services/algorithm_ports/field_extraction.py app/backend/tests/test_field_extraction_port.py
git commit -m "feat: 定义算法端口接口与字段候选契约"
```

## Task 2: ProcessingOrchestrator 和 TaskService 委托

**Files:**
- Create: `app/backend/services/algorithm_ports/orchestrator.py`
- Modify: `app/backend/services/task_service.py`
- Modify: `app/backend/__init__.py`
- Modify Test: `app/backend/tests/test_task_service.py`
- Modify Test: `app/backend/tests/test_task_routes.py`
- Test: `app/backend/tests/test_orchestrator.py`

- [ ] **Step 1: 写编排器失败路径和成功路径测试**

`app/backend/tests/test_orchestrator.py` 必须用 stub port 覆盖：

```python
def test_no_ports_configured_marks_failed(...):
    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
    assert result["details"]["stage"] == "image_processing"
    assert result["details"]["reason"] == "module_not_configured"


def test_all_ports_configured_flow_to_ready(...):
    assert result["status"] == "ready_for_review"
    assert store.exists("results/task-001/image_result.json")
    assert store.exists("results/task-001/document_result.json")
    assert store.exists("results/task-001/field_candidates.json")


def test_image_exception_skips_later_ports(...):
    assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
    assert result["details"]["stage"] == "image_processing"
    assert doc.calls == []
    assert field.calls == []


def test_document_empty_pages_marks_contract_invalid(...):
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
    assert result["details"]["reason"] == "empty_pages"


def test_document_partial_page_failure_preserves_document_result_and_fails_task(...):
    assert result["status"] == "failed"
    assert result["error_code"] == "ALGORITHM_MODULE_FAILED"
    assert result["details"]["reason"] == "partial_page_failed"
    assert store.exists("results/task-001/document_result.json")


def test_field_empty_candidates_marks_contract_invalid(...):
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
    assert result["details"]["stage"] == "field_extraction"
    assert result["details"]["reason"] == "empty_candidates"


def test_missing_schema_skips_field_port_and_fails(...):
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
    assert result["details"]["reason"] == "schema_missing_or_invalid"
    assert field.calls == []


def test_schema_validator_failure_maps_contract_invalid_when_injected(...):
    assert result["error_code"] == "ALGORITHM_CONTRACT_INVALID"
    assert result["details"]["reason"] == "schema_validation_failed"
```

测试 fixture 写入任务时必须包含 `status: "processing"`、`session_id`、`page_order`，会话文件必须包含 `pages[].upload_ref`，页面元数据必须包含 `original_image_path`、`image_width`、`image_height`、`quad_points`。不要让测试从图片内容、OCR 文本或 schema 推导字段。

- [ ] **Step 2: 运行编排器测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q
```

Expected: FAIL，`ProcessingOrchestrator` 未定义或 `TaskService` 尚不接受 orchestrator。

- [ ] **Step 3: 实现 ProcessingOrchestrator**

实现要求：

- `__init__(store, image_port=None, doc_port=None, field_port=None, schema_validator=None)`。
- `run(task, task_service, schema=None)` 返回最终 task dict。
- 按任务 `session_id` 和 `page_order` 读取 `sessions/{session_id}.json`，再按 `pages[].upload_ref` 读取页面元数据。
- `quad_points` 可为 `None`，不得生成默认框选，不得裁剪图片。
- 任一阶段失败立即停止，不调用后续端口。
- 成功阶段结果写入 `results/{task_id}/`。
- 成功时只调用 `task_service.mark_ready(task_id)`。
- 失败时只调用 `task_service.mark_failed(task_id, error_code, message, stage=..., details=...)`。
- 捕获端口异常时 details 不写异常堆栈和完整模型输出。

- [ ] **Step 4: 改造 TaskService**

`TaskService.__init__` 改为接收 `orchestrator`。`process(task_id, schema=None)` 和 `retry(task_id, schema=None)` 必须：

- 按 `docs/Shared/state-enums.md` 做合法流转。
- 进入 `processing` 后清空 `error_code`、`error_message`、`failed_at`、`details`。
- 调用方传入 schema dict 时记录 `schema_version = schema.get("version")` 和 `document_type = schema.get("document_type")`。
- 不自行读取 schema 文件，不构造默认 schema。
- 不再硬编码 `ALGORITHM_MODULE_NOT_CONFIGURED` 主路径。

`mark_failed()` 扩展为：

```python
def mark_failed(self, task_id: str, error_code: str, message: str,
                stage: str = "processing", details: dict | None = None) -> dict:
    ...
    task["details"] = {"stage": stage, **(details or {})}
```

- [ ] **Step 5: 更新 app factory**

`app/backend/__init__.py` 创建默认未配置编排器：

```python
from .services.algorithm_ports.orchestrator import ProcessingOrchestrator

orchestrator = ProcessingOrchestrator(store=store)
app.config["TASK_SERVICE"] = TaskService(store=store, orchestrator=orchestrator)
```

默认端口为 `None`，因此 API 触发处理时应在 `image_processing` 阶段进入 `failed`，错误码为 `ALGORITHM_MODULE_NOT_CONFIGURED`。

- [ ] **Step 6: 更新既有 TaskService 和 route 测试**

既有 `process_without_algorithm`、`retry_without_algorithm` 断言更新为：

```python
assert result["status"] == "failed"
assert result["error_code"] == "ALGORITHM_MODULE_NOT_CONFIGURED"
assert result["error_message"] == "图像处理模块未配置"
assert result["details"]["stage"] == "image_processing"
assert result["details"]["reason"] == "module_not_configured"
```

`mark_failed` 单元测试增加：

```python
assert result["details"]["stage"] == "processing"
```

- [ ] **Step 7: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add app/backend/services/algorithm_ports/orchestrator.py app/backend/services/task_service.py app/backend/__init__.py app/backend/tests/test_orchestrator.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py
git commit -m "feat: 接入外部算法端口编排器"
```

## Task 3: Fixture 适配器契约测试

**Files:**
- Create: `app/backend/services/algorithm_ports/fixtures.py`
- Test: `app/backend/tests/test_image_processing_port.py`
- Test: `app/backend/tests/test_document_parsing_port.py`
- Modify Test: `app/backend/tests/test_field_extraction_port.py`

- [ ] **Step 1: 写 fixture 端口测试**

测试必须证明 fixture 只返回预置值或抛异常：

```python
def test_fixture_image_port_returns_processed_path_from_page_id():
    result = FixtureImagePort(processed_dir="/tmp/processed").process({
        "task_id": "t1", "page_id": "p1", "page_no": 1,
        "original_path": "/tmp/original.jpg", "quad_points": None,
        "image_width": 1920, "image_height": 1080,
    })
    assert result == {"processed_path": "/tmp/processed/p1_processed.jpg"}


def test_fixture_doc_port_preserves_preset_pages():
    pages = [{"page_id": "p1", "page_no": 1, "status": "success", "text": "preset", "blocks": [], "tables": []}]
    result = FixtureDocPort(pages=pages, merged_text="preset merged").parse({"task_id": "t1", "image_paths": [], "pages": []})
    assert result["pages"] is pages
    assert result["merged_text"] == "preset merged"


def test_fixture_field_port_preserves_preset_candidates():
    candidates = [{"field_key": "chief_complaint", "original_value": "预置值", "evidence": None, "confidence": 0.9}]
    result = FixtureFieldPort(candidates=candidates).extract({"task_id": "t1", "document_result": {}, "schema": {"version": "v1"}})
    assert result == candidates
```

异常测试必须断言 `RuntimeError`，由 orchestrator 映射为 `ALGORITHM_MODULE_FAILED`，fixture 自身不写任务状态。

- [ ] **Step 2: 运行测试确认 RED**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_image_processing_port.py app/backend/tests/test_document_parsing_port.py app/backend/tests/test_field_extraction_port.py -q
```

Expected: FAIL，`fixtures.py` 未定义。

- [ ] **Step 3: 实现 Fixture 适配器**

实现 `FixtureImagePort`、`FixtureDocPort`、`FixtureFieldPort`：

- `FixtureImagePort` 只根据 `processed_dir` 和 `input["page_id"]` 拼接测试路径，不打开图片。
- `FixtureDocPort` 优先返回构造函数传入的 `pages`；未传入时只根据 input pages 生成固定测试结构，不读取图像内容，不判断 OCR 正确性。
- `FixtureFieldPort` 只返回构造函数传入的 `candidates`；默认候选只能作为固定测试数据，不能解析 `document_result` 或 schema。
- `return_empty=True` 返回空集合，用于触发失败契约。
- `should_fail=True` 抛 `RuntimeError`，用于触发异常映射。

- [ ] **Step 4: 运行测试确认 GREEN**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_image_processing_port.py app/backend/tests/test_document_parsing_port.py app/backend/tests/test_field_extraction_port.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/backend/services/algorithm_ports/fixtures.py app/backend/tests/test_image_processing_port.py app/backend/tests/test_document_parsing_port.py app/backend/tests/test_field_extraction_port.py
git commit -m "test: 新增算法端口 fixture 契约测试"
```

## Task 4: 回归、泄漏检查和完成记录

**Files:**
- Verify only: `app/backend/`
- Verify only: `docs/`

- [ ] **Step 1: 运行后端全量测试**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -q
```

Expected: PASS。

- [ ] **Step 2: 检查算法实现泄漏**

Run:

```bash
rg -n "pytesseract|easyocr|paddleocr|cv2|PIL|Image\\.open|openai|requests|httpx|正则抽取|规则抽取|模板抽取|裁剪|透视矫正|base64" app/backend/services/algorithm_ports app/backend/services/task_service.py app/backend/__init__.py
```

Expected: 没有命中算法实现、联网调用或 base64 处理。允许命中文档字符串中的边界说明；如果命中可执行代码中的算法库导入、联网库调用、图片读取或规则抽取逻辑，必须删除该实现并补测试防回归。

- [ ] **Step 3: 检查失败契约覆盖**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_orchestrator.py -q
```

Expected: PASS，且测试名覆盖未配置、异常、空 pages、部分页面失败、空 candidates、非法 candidates、缺 schema、validator 失败、成功进入 `ready_for_review`。

- [ ] **Step 4: 完成提交**

```bash
git status --short
git add app/backend/services/algorithm_ports app/backend/services/task_service.py app/backend/__init__.py app/backend/errors.py app/backend/tests
git commit -m "feat: 完成外部算法端口编排失败契约"
```

Expected: commit message 使用中文，且不包含 `data/`、`exports/`、`logs/` 真实运行数据。

## 自审清单

- Goal 覆盖 BE-05：三个端口、编排器、失败映射、结果持久化、TaskService 委托、fixture。
- Architecture 边界清晰：本仓库只做端口、契约校验、状态、持久化、导出后续衔接和日志摘要；不实现算法。
- 状态枚举对齐：成功只走 `processing -> ready_for_review`；失败只走 `processing -> failed`；重试只走 `failed -> processing`。
- 错误码对齐：只使用 `ALGORITHM_MODULE_NOT_CONFIGURED`、`ALGORITHM_MODULE_FAILED`、`ALGORITHM_CONTRACT_INVALID` 表达算法端口失败。
- 空结构化字段处理明确：`FieldExtractionPort.extract()` 返回空 list 必须 `failed`，不得生成空字段进入审核。
- 契约非法处理明确：非 list、缺字段、类型错误、validator 拒绝都必须 `failed`。
- schema 边界明确：BE-05 只接收调用方传入的 dict 并透传；schema 文件加载、字段白名单和版本权威由 BE-06 提供。
- 隐私边界明确：失败 details 和日志只保存阶段、原因码、任务 ID、失败页 ID，不保存完整 OCR 文本、病历原文、身份证号、图片 base64 或模型输出全文。
- Fixture 边界明确：fixture 是端口替身，只返回预置结构或异常，不从图像、文本、schema 或规则推导字段。
- 执行完成后建议提交信息：`feat: 完成外部算法端口编排失败契约`。

## 需主 agent 协调的风险

- BE-06 schema 管理并行开发：BE-05 的 `schema_validator` 只能作为可选注入点；字段白名单、schema 文件路径、默认 schema 由 BE-06 决定。
- API 层后续结果读取接口尚未在本计划实现；失败任务禁止返回空成功结果需在 BE-07/BE-10 或对应 API 契约中继续补齐。
- 日志服务尚未接入；本计划只约束失败 details 不含敏感全文，真正日志落盘格式需 BE-09 统一。
- 真实外部模块动态加载和配置目录映射不在本计划范围；接入真实模块前需新增配置契约测试，仍不得在仓库内实现算法。
