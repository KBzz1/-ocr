# 外部算法端口编排设计（A-lite）

## 范围

对应 PRD `PR-BE-005`、`PR-BE-006`，承接后端 TDD 实施顺序第 6-7 步（`docs/Backend/Backend_TDD/02-algorithm-ports.md`、`07-algorithm-failure-contracts.md`）。

A-lite 阶段目标：定义图像处理、文档解析、字段抽取三个外部算法端口接口，实现处理编排器串联流水线，提供测试用 fixture 适配器，替换 `TaskService.process/retry` 中硬编码的失败路径。不实现任何 OCR、LLM、图像处理算法。

边界隔离：Agent B 并行开发 BE-06（Schema 管理）。BE-05 只校验字段结构合法性（`field_key` 非空、`original_value` 是字符串等），不做 schema 内字段白名单校验。schema 外字段检测由 BE-06 通过可选的 `SchemaValidator` 注入实现。

本阶段覆盖：

- 三个端口接口：`ImageProcessingPort`（原图+quad→processed图像）、`DocumentParsingPort`（processed图像列表→文本+结构）、`FieldExtractionPort`（解析结果+schema→候选字段列表）
- `ProcessingOrchestrator`：按 image→document→field 顺序串联，任一步失败即停止并调用 `mark_failed`
- 失败映射：未配置→`ALGORITHM_MODULE_NOT_CONFIGURED`，异常→`ALGORITHM_MODULE_FAILED`，结构非法→`ALGORITHM_CONTRACT_INVALID`，空结果→failed
- 失败时区分阶段（`stage: image_processing/document_parsing/field_extraction`）
- 每步结果持久化到 `data/results/{task_id}/`
- 字段候选结构校验（不校验 schema 白名单）
- Fixture 适配器：成功/异常/空/部分失败/结构非法，覆盖完整主流程
- `TaskService.process/retry` 委托 `ProcessingOrchestrator.run()`
- 多页图像处理：从 `page_order` + `upload_ref` 读取每页元数据，逐页调用图像处理端口

本阶段不覆盖：

- OCR、LLM、图像处理算法实现（外部交付）
- Schema 定义、schema 外字段校验（BE-06）
- 真实外部模块配置文件或动态加载
- 审核、导出

## 设计原则

- 只定义端口、编排器、失败处理和 fixture；不实现任何算法行为。
- 端口签名对齐 `docs/Backend/Backend_TDD/02-algorithm-ports.md`，使用 input dict 便于后续扩展。
- 处理结果写入 `data/results/{task_id}/`，与 `data/tasks/{task_id}.json` 分离，不冲突。
- 算法模块缺失时不降级；编排器确保失败路径完整覆盖所有失败契约。
- 所有错误响应使用 `docs/Shared/error-codes.md` 统一结构。

## 技术选型

| 项 | 选择 |
|----|------|
| 端口定义 | Python ABC 或 duck-typing 接口类 |
| 编排器注入 | 构造函数注入 `ProcessingOrchestrator(image_port=None, doc_port=None, field_port=None)` |
| 持久化 | 复用 `JsonStore`，结果写入 `data/results/{task_id}/` |
| 测试 | Fixture 适配器，不调真实算法 |

## 目录结构（新增/变更）

```
app/backend/
├── services/
│   └── algorithm_ports/
│       ├── __init__.py
│       ├── image_processing.py      # ImageProcessingPort 接口
│       ├── document_parsing.py      # DocumentParsingPort 接口
│       ├── field_extraction.py      # FieldExtractionPort 接口 + 结构校验
│       ├── orchestrator.py          # ProcessingOrchestrator 流水线编排
│       └── fixtures.py              # Fixture 适配器（仅测试用）
├── services/
│   └── task_service.py              # MODIFIED: process/retry 委托 orchestrator
├── __init__.py                      # MODIFIED: 创建 orchestrator 并注入 TaskService
├── tests/
│   ├── test_image_processing_port.py
│   ├── test_document_parsing_port.py
│   ├── test_field_extraction_port.py
│   └── test_orchestrator.py
```

## 端口接口

### ImageProcessingPort

```python
class ImageProcessingPort:
    """图像处理端口：逐页接收原图路径和 quad，返回 processed 图像路径。"""

    def process(self, input: dict) -> dict:
        """
        input: {
            "original_path": str,       # 原图绝对路径
            "quad_points": list | None, # 四边形角点坐标
            "page_id": str,             # 页面标识
            "image_width": int,
            "image_height": int,
        }
        returns: {"processed_path": str}
        raises: NotImplementedError（未实现时）
        """
        raise NotImplementedError
```

### DocumentParsingPort

```python
class DocumentParsingPort:
    """文档解析端口：接收 processed 图像路径列表，返回逐页解析结果。"""

    def parse(self, input: dict) -> dict:
        """
        input: {
            "image_paths": [str],  # processed 图像路径列表（按页序）
            "task_id": str,
        }
        returns: {
            "pages": [
                {
                    "page_id": str,
                    "page_no": int,
                    "status": "success" | "failed",
                    "text": str,
                    "blocks": [...],
                    "tables": [...],
                }
            ],
            "merged_text": str,
        }
        raises: NotImplementedError
        """
        raise NotImplementedError
```

### FieldExtractionPort

```python
class FieldExtractionPort:
    """字段抽取端口：接收解析结果和 schema，返回候选字段列表。"""

    def extract(self, input: dict) -> list[dict]:
        """
        input: {
            "document_result": dict,  # DocumentParsingPort.parse() 的返回值
            "schema": dict,           # 字段 schema（BE-06 定义结构，本端口只透传）
            "task_id": str,
        }
        returns: [
            {
                "field_key": str,
                "original_value": str,
                "evidence": str | None,
                "confidence": float,
            }
        ]
        raises: NotImplementedError
        """
        raise NotImplementedError
```

### 字段结构校验（独立函数，不依赖 schema 内容）

```python
def validate_field_candidates(candidates: list, schema: dict | None = None) -> None:
    """校验字段候选结构合法性。不通过时 raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID)。

    校验规则：
    - candidates 必须是 list
    - 每项必须是 dict
    - field_key 必须是非空字符串
    - original_value 必须是字符串
    - confidence 如存在必须是 int 或 float
    - evidence 如存在必须是 str 或 None

    不校验 field_key 是否在 schema 内（由 BE-06 的 SchemaValidator 负责）。
    """
```

## 编排器

### ProcessingOrchestrator

```python
class ProcessingOrchestrator:
    def __init__(
        self,
        store: JsonStore,
        image_port: ImageProcessingPort | None = None,
        doc_port: DocumentParsingPort | None = None,
        field_port: FieldExtractionPort | None = None,
    ):
        self._store = store
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port

    def run(self, task: dict, task_service) -> dict:
        """串联 image → document → field 流水线。任一步失败即 mark_failed。
        返回最终的 task dict（ready_for_review 或 failed）。
        """
```

### 多页图像处理逻辑

编排器从任务的 `page_order` 读取页面 ID 列表，通过每个页面的 `upload_ref`（指向 `data/pages/{session_id}/{page_id}.json`）读取页面元数据，提取 `original_image_path` 和 `quad_points`。逐页调用 `ImageProcessingPort.process()`，收集所有 `processed_path`。

如果 `page_order` 为空或某页 `upload_ref` 为 null，视为数据不完整 → `mark_failed(ALGORITHM_CONTRACT_INVALID, message="页面元数据缺失")`。

### 失败映射

```
启动处理
  ├─ image_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "图像处理模块未配置",
  │                  stage="image_processing")
  │
  ├─ image_port.process() raise Exception
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "图像处理模块异常",
  │                  stage="image_processing")
  │
  ├─ doc_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "文档解析模块未配置",
  │                  stage="document_parsing")
  │
  ├─ doc_port.parse() 返回空 pages
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "文档解析结果为空",
  │                  stage="document_parsing")
  │
  ├─ doc_port.parse() 部分页 status=failed
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "部分页面解析失败",
  │                  stage="document_parsing")
  │   保留成功页结果在 document_result.json
  │
  ├─ field_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "字段抽取模块未配置",
  │                  stage="field_extraction")
  │
  ├─ field_port.extract() 返回空列表
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段候选结果为空",
  │                  stage="field_extraction")
  │
  ├─ validate_field_candidates() 失败
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段候选结构非法: ...",
  │                  stage="field_extraction")
  │
  └─ 全部成功
      → mark_ready()
```

每步成功后先持久化结果到 `data/results/{task_id}/`。

## 存储布局

```
data/
├── tasks/
│   └── {task_id}.json              # 任务本体（BE-04 已有）
├── pages/
│   └── {session_id}/
│       ├── {page_id}.jpg           # 原图（BE-03 已有）
│       └── {page_id}.json          # 页面元数据（BE-03 已有）
└── results/
    └── {task_id}/
        ├── image_result.json       # 图像处理结果
        ├── document_result.json    # 文档解析结果
        └── field_candidates.json   # 字段候选结果
```

任务本体 `data/tasks/{task_id}.json` 不变，处理结果独立存储在 `data/results/{task_id}/`。

### 结果文件格式

`image_result.json`：
```json
{
  "task_id": "uuid4",
  "stage": "image_processing",
  "status": "success",
  "pages": [
    {"page_id": "uuid4", "original_path": "...", "processed_path": "..."}
  ]
}
```

`document_result.json`：
```json
{
  "task_id": "uuid4",
  "stage": "document_parsing",
  "status": "success",
  "pages": [
    {"page_id": "uuid4", "page_no": 1, "status": "success", "text": "...", "blocks": [...], "tables": [...]}
  ],
  "merged_text": "..."
}
```

`field_candidates.json`：
```json
{
  "task_id": "uuid4",
  "stage": "field_extraction",
  "status": "success",
  "candidates": [
    {"field_key": "chief_complaint", "original_value": "头痛3天", "evidence": "...", "confidence": 0.95}
  ]
}
```

## TaskService 变更

`task_service.py` 中 `process()` 和 `retry()` 移除硬编码的 `mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED)`，改为委托 `ProcessingOrchestrator.run()`。

```python
class TaskService:
    def __init__(self, store: JsonStore, orchestrator=None):
        self._store = store
        self._orchestrator = orchestrator

    def process(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "触发任务处理")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        self._write_task(task)
        if self._orchestrator:
            return self._orchestrator.run(task, self)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED",
                                message="算法模块未配置",
                                stage="processing")

    def retry(self, task_id: str) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.FAILED.value:
            raise AppError(ErrorCode.INVALID_TASK_TRANSITION, ...)
        task = self._transition(task, ...)
        ...
        if self._orchestrator:
            return self._orchestrator.run(task, self)
        return self.mark_failed(task_id, "ALGORITHM_MODULE_NOT_CONFIGURED",
                                message="算法模块未配置",
                                stage="processing")
```

`mark_failed` 签名扩展，增加 `stage` 参数写入 details：

```python
def mark_failed(self, task_id: str, error_code: str, message: str,
                stage: str = "processing") -> dict:
    task = self._read_task(task_id)
    task = self._transition(task, TaskStatus.FAILED.value, message)
    task["error_code"] = error_code
    task["error_message"] = message
    task["failed_at"] = self._now()
    task.setdefault("details", {})
    task["details"]["failed_stage"] = stage
    self._write_task(task)
    return task
```

## 注册

`app/backend/__init__.py` 中创建 orchestrator（A-lite 阶段所有端口为 None）：

```python
from .services.algorithm_ports.orchestrator import ProcessingOrchestrator

orchestrator = ProcessingOrchestrator(store=store)
app.config["TASK_SERVICE"] = TaskService(store=store, orchestrator=orchestrator)
```

## Fixture 适配器

仅用于测试，放在 `services/algorithm_ports/fixtures.py`：

```python
class FixtureImagePort(ImageProcessingPort):
    def __init__(self, processed_dir: str | None = None, should_fail: bool = False):
        self._processed_dir = processed_dir
        self._should_fail = should_fail

    def process(self, input: dict) -> dict:
        if self._should_fail:
            raise RuntimeError("fixture image processing failure")
        return {"processed_path": f"{self._processed_dir}/{input['page_id']}_processed.jpg"}


class FixtureDocPort(DocumentParsingPort):
    def __init__(self, pages: list | None = None, merged_text: str = "",
                 partial_fail_page_id: str | None = None, should_fail: bool = False,
                 return_empty: bool = False):
        ...

    def parse(self, input: dict) -> dict:
        if self._should_fail: raise RuntimeError(...)
        if self._return_empty: return {"pages": [], "merged_text": ""}
        # 构建 pages，part_fail_page_id 对应页 status="failed"
        ...


class FixtureFieldPort(FieldExtractionPort):
    def __init__(self, candidates: list | None = None, should_fail: bool = False,
                 return_empty: bool = False):
        ...

    def extract(self, input: dict) -> list[dict]:
        if self._should_fail: raise RuntimeError(...)
        if self._return_empty: return []
        return self._candidates
```

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 对应 TDD ID |
|----------|------|-------------|
| `test_image_processing_port.py` | 契约 | BE-IMG-001, 002, 004 |
| `test_document_parsing_port.py` | 契约 | BE-DOC-001, 002, 004, 005 |
| `test_field_extraction_port.py` | 契约 | BE-FLD-001, 002, 003, 004, 006, 007 |
| `test_orchestrator.py` | 集成 | 流水线编排 + 失败传播 + 完整主流程 |

### `test_image_processing_port.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_port_not_configured_task_failed` | BE-IMG-001 | orchestrator 无 image_port 时未进入 failed |
| `test_port_raises_exception_task_failed` | BE-IMG-004 | 端口抛异常后任务未进入 failed |
| `test_fixture_port_returns_processed_path` | BE-IMG-003 | fixture 成功路径未返回 processed_path |
| `test_failed_preserves_original_image_and_quad` | BE-IMG-002 | 失败后元数据丢失 |

### `test_document_parsing_port.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_port_not_configured_task_failed` | BE-DOC-001 | orchestrator 无 doc_port 时未进入 failed |
| `test_empty_pages_marks_failed` | BE-DOC-002 | 空 pages 被当成成功 |
| `test_fixture_result_preserved_as_is` | BE-DOC-003 | 系统改写了解析结果 |
| `test_partial_page_failure_marks_task_failed` | BE-DOC-004 | 部分失败被放行 |
| `test_partial_failure_preserves_success_pages` | BE-DOC-004 | 成功页结果被丢弃 |

### `test_field_extraction_port.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_port_not_configured_task_failed` | BE-FLD-001 | orchestrator 无 field_port 时未进入 failed |
| `test_empty_candidates_marks_failed` | BE-FLD-002 | 空候选被当成成功 |
| `test_fixture_candidates_preserved_as_is` | BE-FLD-003 | 系统修改了候选值 |
| `test_port_exception_marks_failed` | BE-FLD-004 | 异常后未进入 failed |
| `test_missing_field_key_marks_contract_invalid` | BE-FLD-007 | 缺 field_key 被接受 |
| `test_missing_original_value_marks_contract_invalid` | BE-FLD-007 | 缺 original_value 被接受 |
| `test_non_string_field_key_marks_contract_invalid` | BE-FLD-007 | 非字符串 field_key 被接受 |
| `test_extra_fields_in_candidate_are_ok` | — | BE-05 不拒绝携带额外字段的合法候选 |

### `test_orchestrator.py`

| 测试 | RED 失败点 |
|------|------------|
| `test_all_ports_configured_flow_to_ready` | 完整成功主流程未走到 ready_for_review |
| `test_image_fails_skips_doc_and_field` | image 失败后继续调了 doc/field |
| `test_doc_fails_skips_field` | doc 失败后继续调了 field |
| `test_image_result_persisted_to_results_dir` | image_result.json 未落盘 |
| `test_document_result_persisted_to_results_dir` | document_result.json 未落盘 |
| `test_field_candidates_persisted_to_results_dir` | field_candidates.json 未落盘 |
| `test_multi_page_reads_metadata_from_upload_ref` | 未从页面元数据读取 original_path 和 quad |
| `test_page_order_empty_marks_failed` | 空 page_order 未进入 failed |
| `test_failed_stage_recorded_in_task_details` | details.failed_stage 未记录 |
| `test_full_success_fixture_flow` | 多页 success fixture 完整主流程中断 |

## 与后续阶段的衔接

- BE-06（Agent B）：schema 外字段校验通过可选的 `SchemaValidator` 注入 `ProcessingOrchestrator` 或 `validate_field_candidates`。
- 真实外部模块交付后：将 `ImageProcessingPort` 等子类化，实现真实的子进程调用或本地库调用，替换构造函数中的 None。
- `data/results/{task_id}/` 中的结果文件供 BE-07 审核和 BE-08 导出读取。
- `mark_failed` 的 `stage` 信息和 `details` 供前端展示失败阶段。

## 自审结论

- 无 OCR、LLM、图像处理算法实现。
- 存储布局 `data/results/` 与 `data/tasks/` 不冲突。
- 字段校验不涉及 schema 白名单，边界清晰留给 BE-06。
- 端口签名使用 input dict 对齐 TDD 文档，可扩展。
- 多页处理从 page_order/upload_ref 读取元数据，数据来源明确。
- 编排器构造函数注入，失败映射区分阶段。
- Fixture 适配器覆盖成功/异常/空/部分失败/结构非法。
- `mark_failed` 新增 `stage` 参数，不破坏现有调用方。
