# 外部算法端口编排设计（A-lite）

## 范围

对应 PRD `PR-BE-004`、`PR-BE-005`、`PR-BE-006`，承接后端 TDD 实施顺序第 6-7 步（`docs/Backend/Backend_TDD/02-algorithm-ports.md`、`07-algorithm-failure-contracts.md`）。

A-lite 阶段目标：定义图像处理、文档解析、字段抽取三个外部本地算法端口接口，实现处理编排器串联流水线，提供测试用 fixture 适配器，替换 `TaskService.process/retry` 中硬编码的未配置失败路径。不实现任何 OCR、LLM、图像处理、裁剪、透视矫正或规则抽取算法。

边界隔离：Agent B 并行开发 BE-06（Schema 管理）。BE-05 只能接收并透传 schema dict 给字段抽取端口，不定义 schema 文件结构，不读取固定 schema 路径，不校验 `field_key` 是否属于 schema。BE-05 只校验字段候选的端口结构合法性（`field_key` 非空、`original_value` 是字符串等）。schema 外字段检测由 BE-06 或未来可选 validator 提供；如果该 validator 被注入并返回非法，编排器只负责把错误映射为 `ALGORITHM_CONTRACT_INVALID`。

本阶段覆盖：

- 三个端口接口：`ImageProcessingPort`（原图路径+quad→processed 图像路径）、`DocumentParsingPort`（processed 图像路径列表→文本+结构）、`FieldExtractionPort`（解析结果+schema dict→候选字段列表）
- `ProcessingOrchestrator`：按 image→document→field 顺序串联，任一步失败即停止并调用 `TaskService.mark_failed`
- 失败映射：未配置→`ALGORITHM_MODULE_NOT_CONFIGURED`，异常→`ALGORITHM_MODULE_FAILED`，结构非法→`ALGORITHM_CONTRACT_INVALID`，空结果→failed
- 失败时记录阶段和简短 details（`stage: image_processing/document_parsing/field_extraction`），不得记录完整病历原文、图片 base64 或模型输出全文
- 每步结果持久化到 `data/results/{task_id}/`
- 字段候选结构校验（不校验 schema 白名单）
- Fixture 适配器：只返回预置结构或抛预置异常，用于覆盖成功/异常/空/部分失败/结构非法；不得在 fixture 中实现识别、抽取、裁剪或规则兜底
- `TaskService.process/retry` 委托 `ProcessingOrchestrator.run()`
- 多页图像处理：从任务 `session_id` + `page_order` 回查采集会话页面清单，按 `upload_ref` 读取每页元数据，逐页调用图像处理端口

本阶段不覆盖：

- OCR、LLM、图像处理算法实现（外部交付）
- Schema 定义、schema 外字段校验（BE-06）
- 后端基于 schema、OCR 文本或页面内容补造字段
- 真实外部模块配置文件或动态加载
- 审核、导出

## 设计原则

- 只定义端口、编排器、失败处理和 fixture；不实现任何算法行为或规则兜底。
- 端口签名对齐 `docs/Backend/Backend_TDD/02-algorithm-ports.md`，使用 input dict 便于后续扩展。
- 任务本体仍是 `data/tasks/{task_id}.json`，只保存状态、时间、失败摘要和页面顺序等任务元数据；处理中间结果和候选字段写入 `data/results/{task_id}/`，不得写回任务本体。
- 算法模块缺失时不降级；编排器确保失败路径完整覆盖所有失败契约。
- 所有错误响应使用 `docs/Shared/error-codes.md` 统一结构。

## 技术选型

| 项 | 选择 |
|----|------|
| 端口定义 | Python ABC 或 duck-typing 接口类 |
| 编排器注入 | 构造函数注入 `ProcessingOrchestrator(image_port=None, doc_port=None, field_port=None, schema_validator=None)`；`schema_validator` 可选且由 BE-06/后续阶段提供 |
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
            "task_id": str,
            "page_id": str,             # 页面标识
            "page_no": int,             # 冻结后的页序，从 task.page_order 推导
            "original_path": str,       # 页面元数据中的原图路径
            "quad_points": list | None, # 四边形角点坐标
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
            "task_id": str,
            "image_paths": [str],  # processed 图像路径列表（按页序）
            "pages": [
                {"page_id": str, "page_no": int, "processed_path": str}
            ],
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
            "task_id": str,
            "document_result": dict,  # DocumentParsingPort.parse() 的返回值
            "schema": dict,           # schema dict；结构由 BE-06 定义，本端口只透传
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
def validate_field_candidates(candidates: list) -> None:
    """校验字段候选结构合法性。不通过时 raise AppError(ErrorCode.ALGORITHM_CONTRACT_INVALID)。

    校验规则：
    - candidates 必须是 list
    - 每项必须是 dict
    - field_key 必须是非空字符串
    - original_value 必须是字符串
    - confidence 如存在必须是 int 或 float
    - evidence 如存在必须是 str 或 None

    不接收 schema，不校验 field_key 是否在 schema 内（由 BE-06 或未来可选 validator 负责）。
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
        schema_validator=None,
    ):
        self._store = store
        self._image_port = image_port
        self._doc_port = doc_port
        self._field_port = field_port
        self._schema_validator = schema_validator

    def run(self, task: dict, task_service, schema: dict | None = None) -> dict:
        """串联 image → document → field 流水线。任一步失败即 mark_failed。
        返回最终的 task dict（ready_for_review 或 failed）。
        """
```

### 多页图像处理逻辑

编排器不扫描 `data/pages/` 推导页序。唯一页序来源是 BE-04 任务本体中的 `page_order`。处理步骤：

1. 从任务读取 `task_id`、`session_id`、`page_order`。
2. 读取 `data/sessions/{session_id}.json`，用会话 `pages` 建立 `page_id → upload_ref` 映射。
3. 按 `page_order` 顺序逐页读取 `upload_ref` 指向的页面元数据（如 `pages/{session_id}/{page_id}.json`）。
4. 从页面元数据读取 `original_image_path`、`quad_points`、`image_width`、`image_height`。
5. 逐页调用 `ImageProcessingPort.process(input)`，收集 `processed_path`，并把页序信息原样传给后续文档解析端口。

如果 `session_id` 缺失、`page_order` 为空、会话缺失、页面不在会话清单内、某页 `upload_ref` 缺失、页面元数据文件缺失，或页面元数据缺少 `original_image_path`/尺寸字段，均视为任务输入契约不完整：

```
mark_failed(
    task_id,
    "ALGORITHM_CONTRACT_INVALID",
    "页面元数据缺失",
    stage="image_processing",
    details={"stage": "image_processing", "reason": "page_metadata_missing"}
)
```

`quad_points` 可以为 `null`，不得在 BE-05 内自行生成默认框选或执行裁剪/透视矫正。

### schema 输入边界

`ProcessingOrchestrator.run()` 可以接收调用方传入的 `schema: dict | None`，并把该 dict 原样放入 `FieldExtractionPort.extract()` 的 input。BE-05 不负责加载 schema 文件，也不定义 schema 字段结构。

如果 BE-06 已提供 schema loader，TaskService 或上层装配代码可以在调用 orchestrator 前取得 schema dict。`FieldExtractionPort.extract()` 的 `schema` 输入必须是调用方传入的 dict；缺失或非 dict 视为 `field_extraction` 阶段输入契约不完整并进入 `failed`，不得自行构造默认 schema。

如果后续注入 `schema_validator`，其职责只在字段候选返回后检查 schema 外字段等 schema 语义问题；编排器只捕获其失败并映射为 `ALGORITHM_CONTRACT_INVALID`，不在 BE-05 内实现 schema 规则。

### 失败映射

```
启动处理
  ├─ image_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "图像处理模块未配置",
  │                  stage="image_processing",
  │                  details={"stage": "image_processing", "reason": "module_not_configured"})
  │
  ├─ 页面输入元数据缺失或非法
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "页面元数据缺失",
  │                  stage="image_processing",
  │                  details={"stage": "image_processing", "reason": "page_metadata_missing"})
  │
  ├─ image_port.process() raise Exception
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "图像处理模块异常",
  │                  stage="image_processing",
  │                  details={"stage": "image_processing", "reason": "module_exception"})
  │
  ├─ image_port.process() 返回缺少 processed_path
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "图像处理结果结构非法",
  │                  stage="image_processing",
  │                  details={"stage": "image_processing", "reason": "invalid_processed_path"})
  │
  ├─ doc_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "文档解析模块未配置",
  │                  stage="document_parsing",
  │                  details={"stage": "document_parsing", "reason": "module_not_configured"})
  │
  ├─ doc_port.parse() raise Exception
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "文档解析模块异常",
  │                  stage="document_parsing",
  │                  details={"stage": "document_parsing", "reason": "module_exception"})
  │
  ├─ doc_port.parse() 返回空 pages
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "文档解析结果为空",
  │                  stage="document_parsing",
  │                  details={"stage": "document_parsing", "reason": "empty_pages"})
  │
  ├─ doc_port.parse() 部分页 status=failed
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "部分页面解析失败",
  │                  stage="document_parsing",
  │                  details={"stage": "document_parsing", "reason": "partial_page_failed", "failed_page_ids": [...]})
  │   保留成功页结果在 document_result.json
  │
  ├─ field_port is None
  │   → mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED,
  │                  "字段抽取模块未配置",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "module_not_configured"})
  │
  ├─ schema 缺失或不是 dict
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段 schema 缺失或非法",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "schema_missing_or_invalid"})
  │
  ├─ field_port.extract() raise Exception
  │   → mark_failed(ALGORITHM_MODULE_FAILED,
  │                  "字段抽取模块异常",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "module_exception"})
  │
  ├─ field_port.extract() 返回空列表
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段候选结果为空",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "empty_candidates"})
  │
  ├─ validate_field_candidates() 失败
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段候选结构非法: ...",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "invalid_candidate_contract"})
  │
  ├─ schema_validator 检测到 schema 外字段（仅当 BE-06/后续阶段注入）
  │   → mark_failed(ALGORITHM_CONTRACT_INVALID,
  │                  "字段候选不符合 schema",
  │                  stage="field_extraction",
  │                  details={"stage": "field_extraction", "reason": "schema_validation_failed"})
  │
  └─ 全部成功
      → mark_ready()
```

每步成功后先持久化结果到 `data/results/{task_id}/`。失败 details 只记录阶段、原因码、失败页 ID 等排查摘要，不记录完整 OCR 文本、结构化字段全文、患者身份信息、图片 base64 或调用堆栈。

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

任务本体文件路径仍为 `data/tasks/{task_id}.json`，只保存任务状态和失败摘要；处理结果独立存储在 `data/results/{task_id}/`。

### 结果文件格式

`image_result.json`：
```json
{
  "task_id": "uuid4",
  "stage": "image_processing",
  "status": "success",
  "pages": [
    {
      "page_id": "uuid4",
      "page_no": 1,
      "original_path": "data/pages/{session_id}/{page_id}.jpg",
      "quad_points": null,
      "processed_path": "data/results/{task_id}/processed/{page_id}.jpg"
    }
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

`TaskService` 继续负责任务读取、合法状态流转、失败/成功状态落盘；`ProcessingOrchestrator` 只负责算法端口编排、结果持久化和把阶段失败委托回 `TaskService.mark_failed()`。二者关系：

- `TaskService.process()`：校验当前任务可进入 `processing`，清理旧失败字段，写入 `processing_at`，然后调用 `orchestrator.run(task, self, schema=schema_dict)`。
- `TaskService.retry()`：只允许 `failed → processing`，清理旧失败字段和 details，随后调用同一个 orchestrator。
- `schema_dict` 来自上层注入的 SchemaService 或测试 fixture。BE-05 不加载 schema 文件；如果 BE-06 尚未接入，成功主流程测试必须显式传入最小 schema dict。
- `ProcessingOrchestrator`：不得直接改写任务状态文件；成功时调用 `task_service.mark_ready(task_id)`，失败时调用 `task_service.mark_failed(...)`。
- 应用装配必须创建 orchestrator。A-lite 阶段端口可以全为 `None`，因此首个未配置阶段会明确失败在 `image_processing`，不再由 TaskService 写一个笼统的 `processing` 失败。

`task_service.py` 中 `process()` 和 `retry()` 移除硬编码的 `mark_failed(ALGORITHM_MODULE_NOT_CONFIGURED)` 主路径，改为委托 `ProcessingOrchestrator.run()`。

```python
class TaskService:
    def __init__(self, store: JsonStore, orchestrator):
        self._store = store
        self._orchestrator = orchestrator

    def process(self, task_id: str, schema: dict | None = None) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.PROCESSING.value, "触发任务处理")
        task["processing_at"] = self._now()
        task["error_code"] = None
        task["error_message"] = None
        task["failed_at"] = None
        task["details"] = {}
        if schema is not None:
            task["schema_version"] = schema.get("version")
            task["document_type"] = schema.get("document_type")
        self._write_task(task)
        return self._orchestrator.run(task, self, schema=schema)

    def retry(self, task_id: str, schema: dict | None = None) -> dict:
        task = self._read_task(task_id)
        if task["status"] != TaskStatus.FAILED.value:
            raise AppError(ErrorCode.INVALID_TASK_TRANSITION, ...)
        task = self._transition(task, ...)
        ...
        task["details"] = {}
        if schema is not None:
            task["schema_version"] = schema.get("version")
            task["document_type"] = schema.get("document_type")
        return self._orchestrator.run(task, self, schema=schema)
```

`schema_version` 和 `document_type` 的权威来源由 BE-06 定义。BE-05 只在调用方传入 schema dict 时记录这两个字段；不得自行构造默认版本或默认文书类型。

`mark_failed` 签名扩展，增加 `stage` 和 `details` 参数。`details` 写入任务本体只作为失败摘要，不包含敏感全文：

```python
def mark_failed(self, task_id: str, error_code: str, message: str,
                stage: str = "processing", details: dict | None = None) -> dict:
    task = self._read_task(task_id)
    task = self._transition(task, TaskStatus.FAILED.value, message)
    task["error_code"] = error_code
    task["error_message"] = message
    task["failed_at"] = self._now()
    task["details"] = {"stage": stage, **(details or {})}
    self._write_task(task)
    return task
```

## 注册

`app/backend/__init__.py` 中必须创建 orchestrator 并注入 `TaskService`。A-lite 阶段所有端口为 `None`，触发处理后由 orchestrator 在 `image_processing` 阶段返回 `ALGORITHM_MODULE_NOT_CONFIGURED`：

```python
from .services.algorithm_ports.orchestrator import ProcessingOrchestrator

orchestrator = ProcessingOrchestrator(store=store)
app.config["TASK_SERVICE"] = TaskService(store=store, orchestrator=orchestrator)
```

## Fixture 适配器

仅用于测试，放在 `services/algorithm_ports/fixtures.py`。Fixture 只透传测试预置值或抛出测试预置异常，不根据图像内容、OCR 文本、schema 或规则生成字段：

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
        # 返回构造函数注入的预置 pages；partial_fail_page_id 只把预置页状态改为 failed
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
| `test_field_extraction_port.py` | 契约 | BE-FLD-001, 002, 003, 004, 007 |
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
| `test_schema_outside_field_is_not_checked_without_validator` | — | BE-05 偷做 schema 白名单校验 |

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
| `test_failed_stage_recorded_in_task_details` | details.stage 未记录 |
| `test_schema_validator_failure_maps_contract_invalid_when_injected` | 可选 validator 失败未映射为 BE-FLD-006 |
| `test_full_success_fixture_flow` | 多页 success fixture 完整主流程中断 |
| `test_success_flow_requires_explicit_schema_dict` | 未接入 BE-06 时 BE-05 自行构造了默认 schema |

## 与后续阶段的衔接

- BE-06（Agent B）：schema 外字段校验通过可选的 `SchemaValidator` 注入 `ProcessingOrchestrator`；BE-05 的 `validate_field_candidates` 不接收 schema。
- 真实外部模块交付后：将 `ImageProcessingPort` 等子类化，实现真实的子进程调用或本地库调用，替换构造函数中的 None。
- `data/results/{task_id}/` 中的结果文件供 BE-07 审核和 BE-08 导出读取。
- `mark_failed` 的 `stage` 信息和 `details` 供前端展示失败阶段。

## 自审结论

- 无 OCR、LLM、图像处理算法实现。
- 存储布局 `data/results/` 与 `data/tasks/` 不冲突。
- 字段校验不涉及 schema 白名单，BE-FLD-006 仅在 BE-06/未来 validator 注入后由编排器映射。
- 端口签名使用 input dict 对齐 TDD 文档，可扩展。
- 多页处理从 `task.session_id`、`task.page_order`、会话 `pages[].upload_ref` 读取元数据，数据来源明确。
- 编排器构造函数注入，失败映射区分阶段并写入 details 摘要。
- Fixture 适配器覆盖成功/异常/空/部分失败/结构非法。
- `mark_failed` 新增 `stage` 参数，不破坏现有调用方。
