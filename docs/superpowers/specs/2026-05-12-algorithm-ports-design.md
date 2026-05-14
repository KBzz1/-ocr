# 外部算法端口与编排设计（BE-05）

## 范围

对应 PRD `PR-BE-005`、`PR-BE-006`，覆盖 `docs/PRD任务清单.md` 中：

- BE-05-01 图像处理端口契约
- BE-05-02 文档解析端口契约
- BE-05-03 字段抽取端口契约
- BE-05-04 算法失败映射

本阶段承接 BE-04 任务生命周期：`POST /api/tasks/{taskId}/process` 和 `retry` 触发任务处理编排。BE-05 的目标是让后端具备调用外部本地算法模块的端口边界、fixture 成功路径、失败映射和结果持久化能力。

本阶段覆盖：

- 定义图像处理、文档解析、字段抽取三个本地端口的输入输出契约。
- 提供默认未配置端口，触发处理时任务进入 `failed` 并保存 `ALGORITHM_MODULE_NOT_CONFIGURED`。
- 提供测试用 fixture 端口，用于验证外部结果被原样保存，不验证识别准确率。
- 编排流程：图像处理 → 文档解析 → 字段抽取。
- 成功时保存处理后图像路径、文档解析结果、字段候选结果，并将任务推进到 `ready_for_review`。
- 失败时保存 `error_code`、`error_message`、`failed_at`，任务进入 `failed`。
- 部分页面解析失败时保留成功页外部结果，但整体任务进入 `failed`。

本阶段不覆盖：

- OCR、LLM、图像预处理、裁剪、透视矫正、自动边界识别或规则字段抽取实现。
- 真实外部算法包的加载细节、模型路径探测或部署检查。
- Schema 管理完整实现（BE-06）。本阶段仅允许使用测试 fixture schema 验证字段候选契约。
- 审核结果编辑、确认校验、导出。
- 前端审核页和结果展示。

## 设计原则

- 本仓库只定义端口、调用编排、契约校验、结果持久化和失败映射。
- 任何端口未配置、抛异常、返回空结果或契约非法，都不得进入 `ready_for_review`。
- 不允许用 schema、OCR 文本、页面内容或规则生成替代结构化字段。
- fixture 只代表“外部模块返回的数据”，不得被解释为本项目具备识别或抽取能力。
- 外部模块返回的文档解析结果和字段候选结果应原样保存；后端只补充本系统需要的状态、时间和任务引用字段。
- 日志和错误响应不得包含完整病历原文、身份证号、图片 base64 或模型输出全文。

## 技术选型

| 项 | 选择 |
|----|------|
| 端口定义 | Python `Protocol` + dataclass/dict 契约 |
| 编排层 | 新建 `AlgorithmOrchestrator` |
| 默认端口 | 未配置端口，调用即抛 `AlgorithmPortNotConfigured` |
| 测试端口 | fixture adapter，仅在测试中注入 |
| 持久化 | 复用 `JsonStore` |
| 状态更新 | 复用 `TaskService.mark_ready()` / `mark_failed()` |

## 目录结构（新增/变更）

```text
app/backend/
├── algorithm/
│   ├── __init__.py                     # NEW 算法端口包
│   ├── ports.py                        # NEW 端口 Protocol、错误类型、契约辅助类型
│   ├── defaults.py                     # NEW 默认未配置端口
│   ├── fixtures.py                     # NEW 测试 fixture 端口实现
│   └── orchestrator.py                 # NEW 算法处理编排
├── services/
│   └── task_service.py                 # MODIFIED process/retry 接入 orchestrator
├── routes/
│   └── task_results.py                 # NEW 文档解析结果和字段候选读取 API
├── tests/
│   ├── test_algorithm_ports.py         # NEW 端口契约单元测试
│   ├── test_algorithm_orchestrator.py  # NEW 编排集成测试
│   └── test_task_results_routes.py     # NEW 结果读取 API 测试
└── __init__.py                         # MODIFIED 注册默认端口、orchestrator、结果路由
```

## 端口契约

### 错误类型

算法端口抛出的内部异常不直接暴露为 HTTP 响应，而是由编排层映射为任务失败信息。

```python
class AlgorithmPortNotConfigured(Exception):
    """端口未配置。映射为 ALGORITHM_MODULE_NOT_CONFIGURED。"""


class AlgorithmPortFailed(Exception):
    """端口调用异常。映射为 ALGORITHM_MODULE_FAILED。"""


class AlgorithmContractInvalid(Exception):
    """端口返回结构非法。映射为 ALGORITHM_CONTRACT_INVALID。"""
```

### 图像处理端口

输入：

```json
{
  "task_id": "uuid4",
  "page_id": "page_id_1",
  "page_no": 1,
  "original_path": "pages/{session_id}/{page_id}.jpg",
  "quad_points": [[0, 0], [100, 0], [100, 100], [0, 100]],
  "image_width": 1200,
  "image_height": 1600
}
```

输出：

```json
{
  "page_id": "page_id_1",
  "page_no": 1,
  "processed_image_path": "results/{task_id}/processed/page_id_1.png",
  "status": "success"
}
```

契约要求：

- `processed_image_path` 必须是非空相对路径。
- 输出 `page_id` 必须等于输入 `page_id`。
- 输出 `status` 必须为 `success`，失败应抛异常而不是返回空成功。
- 后端不校验图像内容，不做裁剪或透视矫正。

### 文档解析端口

输入：

```json
{
  "task_id": "uuid4",
  "image_paths": ["results/{task_id}/processed/page_id_1.png"],
  "pages": [
    {
      "page_id": "page_id_1",
      "page_no": 1,
      "source_image_path": "pages/{session_id}/{page_id}.jpg",
      "processed_image_path": "results/{task_id}/processed/page_id_1.png"
    }
  ]
}
```

输出：

```json
{
  "task_id": "uuid4",
  "pages": [
    {
      "page_id": "page_id_1",
      "page_no": 1,
      "status": "success",
      "plain_text": "fixture text from external parser",
      "blocks": [],
      "tables": []
    }
  ],
  "merged_text": "fixture text from external parser"
}
```

契约要求：

- `pages` 必须是非空列表。
- 每页必须包含 `page_id`、`page_no`、`status`。
- `status` 允许 `success` 或 `failed`。
- 只要任一页 `status == "failed"`，整体任务进入 `failed`，但文档解析结果仍保存供排查。
- 空 `pages`、缺字段、非法 `status` 映射为 `ALGORITHM_CONTRACT_INVALID`。
- 后端不修改 `plain_text`、`blocks`、`tables`、`merged_text`。
- 文档解析默认使用图像处理端口返回的 `processed_image_path` 作为 `image_paths`；`source_image_path` 仅用于保留原图追踪信息。

### 字段抽取端口

输入：

```json
{
  "task_id": "uuid4",
  "document_result": {
    "task_id": "uuid4",
    "pages": [],
    "merged_text": "fixture text from external parser"
  },
  "schema": {
    "version": "fixture",
    "fields": ["chief_complaint"]
  }
}
```

输出：

```json
[
  {
    "field_key": "chief_complaint",
    "field_name": "主诉",
    "original_value": "fixture value from external extractor",
    "evidence": "fixture evidence",
    "page_no": 1,
    "confidence": "medium"
  }
]
```

持久化时后端允许补充：

```json
{
  "status": "unreviewed",
  "reviewed_value": null,
  "reviewed_at": null,
  "review_note": null
}
```

契约要求：

- 字段候选必须是非空列表。
- 每个字段必须包含 `field_key`、`original_value`。
- `field_key` 必须来自当前 schema。
- `confidence` 如存在，必须原样保存；本阶段不基于置信度改变字段。
- 字段状态初始为 `unreviewed`。
- 空候选、schema 外字段、缺少关键字段均映射为 `ALGORITHM_CONTRACT_INVALID`。
- 后端不得基于 schema 生成空字段候选或默认字段值。

## 持久化布局

```text
data/
├── pages/
│   └── {session_id}/
│       └── {page_id}.json               # 已有上传元数据，含 original_image_path/quad_points
├── tasks/
│   └── {task_id}.json                   # 任务状态、错误信息、历史
└── results/
    └── {task_id}/
        ├── image-processing.json        # 图像处理端口返回摘要
        ├── document-result.json         # 文档解析端口原始返回
        └── structured-fields.json       # 字段抽取候选 + 本系统字段状态
```

### 页面元数据回写

图像处理成功后，需要把每页的 `processed_image_path` 写回页面元数据 JSON。页面元数据仍以 PR-BE-003 的 upload metadata 为准，不新增独立页序来源。

## 编排流程

```text
TaskService.process(task_id)
    ↓
AlgorithmOrchestrator.process(task_id)
    ↓
读取 task.page_order
    ↓
读取每页 upload metadata
    ↓
ImageProcessingPort.process(each page)
    ↓
保存 image-processing.json，回写 processed_image_path
    ↓
DocumentParsingPort.parse(processed images with original image metadata)
    ↓
保存 document-result.json
    ↓
若任一解析页 failed → TaskService.mark_failed(...)
    ↓
FieldExtractionPort.extract(document_result, schema)
    ↓
校验字段候选
    ↓
保存 structured-fields.json
    ↓
TaskService.mark_ready(task_id)
```

`retry` 与 `process` 使用同一编排逻辑；区别只在任务状态从 `failed` 重新进入 `processing` 的状态历史由 BE-04 负责记录。

## 成功路径

给定测试 fixture 端口：

- 图像处理 fixture 返回每页 `processed_image_path`。
- 文档解析 fixture 返回 `pages`、`blocks`、`tables`、`merged_text`。
- 字段抽取 fixture 返回非空字段候选。

系统必须：

- 保存三类结果文件。
- 回写页面元数据中的 `processed_image_path`。
- 保存字段候选并将每个字段标记为 `unreviewed`。
- 任务状态进入 `ready_for_review`。
- 不改写外部返回的 OCR 文本、块、表格、字段值、证据和置信度。

## 失败映射

| 场景 | 任务状态 | error_code | 额外要求 |
|------|----------|------------|----------|
| 任一端口未配置 | `failed` | `ALGORITHM_MODULE_NOT_CONFIGURED` | 不产生空成功结果 |
| 任一端口抛 `AlgorithmPortFailed` 或未知异常 | `failed` | `ALGORITHM_MODULE_FAILED` | 不向 API 冒泡 500 |
| 图像处理返回空 processed path | `failed` | `ALGORITHM_CONTRACT_INVALID` | 保留原图和 quad |
| 文档解析返回空 pages | `failed` | `ALGORITHM_CONTRACT_INVALID` | 不暴露为空成功文档 |
| 文档解析部分页面 failed | `failed` | `ALGORITHM_MODULE_FAILED` | 保存成功页和失败页状态 |
| 字段抽取返回空候选 | `failed` | `ALGORITHM_CONTRACT_INVALID` | 不生成空字段 |
| 字段抽取返回 schema 外字段 | `failed` | `ALGORITHM_CONTRACT_INVALID` | 非法候选不保存为审核结果 |
| 字段抽取缺少 `field_key` 或 `original_value` | `failed` | `ALGORITHM_CONTRACT_INVALID` | 非法候选不保存为审核结果 |

## API 契约

### GET /api/tasks/{task_id}/document-result

返回文档解析结果。

成功任务响应：

```json
{
  "success": true,
  "data": {
    "task_id": "uuid4",
    "pages": [],
    "merged_text": "fixture text from external parser"
  }
}
```

错误响应：

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |
| 任务未进入 `ready_for_review`/`confirmed`/`exported` | 400 | `INVALID_TASK_TRANSITION` |
| 结果文件不存在 | 404 | `TASK_NOT_FOUND` |

失败任务不得返回 `success: true` 和空结果。

### GET /api/tasks/{task_id}/structured-fields

返回字段候选结果。

成功任务响应：

```json
{
  "success": true,
  "data": {
    "task_id": "uuid4",
    "fields": [
      {
        "field_key": "chief_complaint",
        "field_name": "主诉",
        "original_value": "fixture value from external extractor",
        "evidence": "fixture evidence",
        "page_no": 1,
        "confidence": "medium",
        "status": "unreviewed",
        "reviewed_value": null,
        "reviewed_at": null,
        "review_note": null
      }
    ]
  }
}
```

错误响应同文档结果 API。失败任务不得返回空数组成功响应。

## 与 BE-04 的衔接

BE-04 A-lite 中 `process/retry` 在未配置算法时固定进入 `failed`。BE-05 接入后应改为：

- `TaskService.process()`：合法状态进入 `processing` 后调用 `AlgorithmOrchestrator.process(task_id)`。
- `TaskService.retry()`：`failed -> processing` 后调用同一编排。
- 默认端口未配置时，编排层仍返回 `ALGORITHM_MODULE_NOT_CONFIGURED`，保持 BE-04 的失败契约。
- fixture 端口注入时，成功路径进入 `ready_for_review`。

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 覆盖 |
|----------|------|------|
| `test_algorithm_ports.py` | 契约单元 | 默认未配置端口、fixture 端口、契约非法 |
| `test_algorithm_orchestrator.py` | 集成 | 成功编排、失败映射、结果持久化 |
| `test_task_results_routes.py` | API | 文档结果和字段结果读取，不伪装空成功 |

### `test_algorithm_ports.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_default_image_processing_port_not_configured` | BE-IMG-001 | 未配置端口被当成成功 |
| `test_default_document_parsing_port_not_configured` | BE-DOC-001 | 未配置解析端口返回空成功 |
| `test_default_field_extraction_port_not_configured` | BE-FLD-001 | 未配置抽取端口返回空成功 |
| `test_fixture_image_processing_returns_processed_paths` | BE-IMG-003 | fixture 路径未返回 |
| `test_fixture_document_parser_returns_pages_unchanged` | BE-DOC-003 | 解析 fixture 被改写 |
| `test_fixture_field_extractor_returns_fields_unchanged` | BE-FLD-003 | 字段 fixture 被改写 |

### `test_algorithm_orchestrator.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_process_with_fixture_ports_marks_ready` | BE-05 成功编排 | 成功 fixture 未进入 ready_for_review |
| `test_process_persists_image_processing_results` | BE-IMG-003 | processed path 未持久化 |
| `test_process_persists_document_result_unchanged` | BE-DOC-003 | 文档解析结果被改写 |
| `test_process_persists_structured_fields_unreviewed` | BE-FLD-003 | 字段状态不是 unreviewed |
| `test_missing_image_port_marks_failed` | BE-IMG-001 | 未配置未失败 |
| `test_image_port_exception_maps_failed` | BE-IMG-004 | 异常冒泡或 500 |
| `test_empty_document_pages_marks_contract_invalid` | BE-DOC-002 | 空解析结果被放行 |
| `test_partial_document_failure_marks_task_failed_and_keeps_result` | BE-DOC-004 | 部分失败被放行或结果丢失 |
| `test_empty_fields_marks_contract_invalid` | BE-FLD-002 | 空字段进入审核 |
| `test_schema_extra_field_marks_contract_invalid` | BE-FLD-006 | schema 外字段被保存 |
| `test_missing_required_field_key_marks_contract_invalid` | BE-FLD-007 | 非法字段结构被保存 |

### `test_task_results_routes.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_get_document_result_returns_saved_result` | BE-DOC-005 | 结果端点缺失 |
| `test_get_document_result_for_failed_task_returns_error` | BE-DOC-005 | 失败任务返回空成功 |
| `test_get_structured_fields_returns_saved_fields` | BE-FLD-005 | 字段端点缺失 |
| `test_get_structured_fields_for_failed_task_returns_error` | BE-FLD-005 | 失败任务返回空数组成功 |

## 自审结论

- 本 spec 不要求实现 OCR、LLM、图像处理、裁剪、透视矫正或规则抽取。
- 成功路径只通过 fixture 端口模拟外部模块返回，用于验证编排和持久化。
- 失败契约覆盖 `ALGORITHM_MODULE_NOT_CONFIGURED`、`ALGORITHM_MODULE_FAILED`、`ALGORITHM_CONTRACT_INVALID`。
- 字段候选必须来自外部端口，后端只补充审核状态，不补造字段值。
- BE-05 可作为 BE-06 schema 管理、BE-07 审核、BE-10 E2E 的前置基础。
