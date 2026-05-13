# BE-08 导出服务设计

## 范围

对应 PRD `PR-BE-009`，覆盖 `docs/PRD任务清单.md` 中：

- BE-08-01 导出前完整性检查
- BE-08-02 JSON 导出
- BE-08-03 Excel 导出

本阶段承接 BE-07 人工审核结果。导出服务只以 `results/{task_id}/review_result.json` 中人工审核后的 `final_value` 为最终结果来源，不读取自动候选作为导出结果，不在导出阶段推断、补造或修正字段。

本阶段覆盖：

- 导出前完整性检查 API，返回未审核、存疑、空值、未接受空值、无来源字段统计和字段 key 列表。
- JSON 导出，保存到任务独立导出目录并返回下载响应。
- Excel 导出，按 schema 字段组组织 sheet，并返回下载响应。
- 导出成功后记录导出格式、导出时间、相对路径，并把任务推进到 `exported`。
- `confirmed` 和 `exported` 任务允许导出；未确认任务必须返回 `EXPORT_VALIDATION_FAILED`。
- 导出失败必须返回 `EXPORT_FAILED`，不得修改审核结果，且不得破坏已确认状态。

本阶段不覆盖：

- 前端下载按钮或导出页面。
- 电脑端审核 UI。
- OCR、LLM、图像处理、规则抽取或字段补造。
- 医院 HIS/EMR 写回。
- 批量导出多个任务。
- 导出文件长期保留策略和清理 UI（BE-09 已提供任务级清理边界）。

## 权威依据

- `docs/产品PRD.md`：PR-BE-009、PR-FE-007。
- `docs/Shared/state-enums.md`：`confirmed`、`exported` 任务状态，字段状态。
- `docs/Shared/error-codes.md`：`EXPORT_VALIDATION_FAILED`、`EXPORT_FAILED`、`TASK_NOT_FOUND`。
- `docs/Backend/Backend_BDD/export.md`。
- `docs/Backend/Backend_TDD/10-export-service.md`。
- `docs/Backend/Backend_TDD/09-review-results.md`。
- `docs/Backend/Backend_BDD/review-persistence.md`。
- `docs/superpowers/specs/2026-05-12-review-results-design.md`。

## 设计原则

- 人工审核结果是导出唯一权威来源。
- 导出前校验在后端执行，前端不能绕过。
- JSON 与 Excel 使用同一份导出数据模型，避免两个格式结果不一致。
- 文件路径只使用任务 ID 和固定文件名，拒绝用户输入参与路径。
- 导出失败不改变 `review_result.json`，不把任务从 `confirmed` 错误推进到 `exported`。
- 若 BE-09 本地事件日志存在，只记录导出摘要，不记录字段全文。
- 不新增运行时依赖；当前 `requirements.txt` 仅包含 Flask、PyYAML、pytest，Excel 生成必须使用标准库最小实现。

## 文件边界

```text
app/backend/
├── services/
│   └── export_service.py              # NEW 导出校验、导出数据模型、JSON/Excel 文件生成
├── routes/
│   └── export.py                      # NEW 导出检查和下载 API
├── tests/
│   ├── test_export_service.py         # NEW 服务层测试
│   └── test_export_routes.py          # NEW API 契约测试
├── __init__.py                        # MODIFIED 注册 ExportService 和 export_bp
├── routes/__init__.py                 # MODIFIED 增加 _get_export_service()
└── services/task_service.py           # MODIFIED 导出成功时记录 export_summary/状态
```

允许读取：

- `results/{task_id}/review_result.json`
- `tasks/{task_id}.json`
- 当前 schema 文件和 `SchemaService.get_current()`

不修改：

- `app/backend/services/review_service.py` 的 review_result 契约。
- `app/backend/services/algorithm_ports/`。
- `app/backend/services/local_event_log.py` 的事件白名单结构。
- `app/frontend/`。

## 数据契约

导出目录：

```text
exports/{task_id}/
├── {task_id}.review.json
└── {task_id}.review.xlsx
```

服务内部导出数据模型：

```json
{
  "task_id": "task_001",
  "exported_at": "2026-05-13T10:00:00+00:00",
  "schema_version": "1.0.0",
  "document_type": "general_medical_record",
  "fields": [
    {
      "field_key": "chief_complaint",
      "field_name": "主诉",
      "group_key": "admission_info",
      "group_label": "入院/病程信息",
      "final_value": "头痛3天",
      "status": "confirmed",
      "empty_accepted": false,
      "evidence": "第1页第2行",
      "page_no": 1,
      "reviewed_at": "2026-05-13T09:55:00+00:00"
    }
  ],
  "summary": {
    "total_count": 1,
    "unreviewed_count": 0,
    "suspicious_count": 0,
    "empty_count": 0,
    "empty_unaccepted_count": 0,
    "missing_evidence_count": 0
  }
}
```

排序规则：

- 字段优先按当前 `review_result.fields` 中的顺序导出。
- 如需补充组信息，按当前 schema 的字段 key 查找 `group_key`/`group_label`。
- 如果历史 review_result 的字段 key 不在当前 schema 中，不删除字段；组信息使用 `unknown`，并保持 review_result 原顺序。导出不得因此补造字段值。

## API 契约

### GET /api/tasks/{task_id}/export/check

成功：

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "status": "confirmed",
    "can_export": true,
    "summary": {
      "total_count": 2,
      "unreviewed_count": 0,
      "suspicious_count": 0,
      "empty_count": 1,
      "empty_unaccepted_count": 0,
      "missing_evidence_count": 1
    },
    "blocking_fields": {
      "unreviewed": [],
      "suspicious": [],
      "empty_unaccepted": []
    }
  }
}
```

失败：

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |
| 任务不是 `confirmed` 或 `exported` | 400 | `EXPORT_VALIDATION_FAILED` |
| review_result 缺失或无字段 | 400 | `EXPORT_VALIDATION_FAILED` |

### GET /api/tasks/{task_id}/export/json

成功：

- 写入 `exports/{task_id}/{task_id}.review.json`。
- 返回下载响应。
- `Content-Type: application/json`
- `Content-Disposition` 包含 `{task_id}.review.json`。
- 导出内容来自人工 `final_value`。

### GET /api/tasks/{task_id}/export/excel

成功：

- 写入 `exports/{task_id}/{task_id}.review.xlsx`。
- 返回下载响应。
- `Content-Type` 使用标准 xlsx MIME。
- `Content-Disposition` 包含 `{task_id}.review.xlsx`。
- 每个 schema 字段组一个 sheet；每行包含字段 key、字段名、final_value、状态、来源页、来源证据。

Excel 实现选择：

- 本任务不得新增第三方依赖，不得运行时联网安装 Excel 库。
- 使用项目内标准库最小 xlsx writer：通过 `zipfile` 写入 Office Open XML 必需文件，sheet 内容只覆盖本 spec 列出的表头和字段行。
- xlsx writer 作为 `ExportService` 内部私有实现或 `services/export_service.py` 中的私有 helper，不暴露为通用 Excel 框架。
- 测试不依赖 `openpyxl`；使用 `zipfile` 读取 `xl/workbook.xml`、`xl/worksheets/sheet*.xml`、`xl/sharedStrings.xml` 或 inlineStr 内容验证 sheet 名称、表头和 `final_value`。

## 状态流转

- `confirmed` 导出成功后可推进为 `exported`。
- `exported` 再次导出允许覆盖同格式文件，并更新 `export_summary`。
- `ready_for_review`、`processing`、`uploaded`、`failed` 均不得导出。
- 导出失败保持原任务状态不变。

`TaskService.mark_exported()` 需要保留或扩展：

```json
{
  "export_summary": {
    "last_exported_at": "2026-05-13T10:00:00+00:00",
    "formats": ["json", "excel"],
    "files": [
      {"format": "json", "relative_path": "task_001/task_001.review.json"}
    ]
  }
}
```

实现约束：

- 保留现有 `mark_exported(task_id)` 调用方式，新增参数必须有默认值。
- `formats` 按首次导出顺序追加，重复导出同一格式不重复追加。
- `files` 同一格式重复导出时更新对应 `relative_path` 和时间，不累积重复条目。
- `export_summary.files[].relative_path` 相对 `exports/`，形如 `task_001/task_001.review.json`，不得保存绝对路径。

## 错误处理

- 完整性失败：`EXPORT_VALIDATION_FAILED`，details 中列出阻断字段 key。
- 文件系统写入失败：`EXPORT_FAILED`，details 只包含 `format` 和简短原因，不包含字段全文。
- 路径错误：实现中不接受用户路径输入，测试用 monkeypatch 模拟写入失败。

## 与其他任务的边界

- 与 BE-03-08 并行：无共享实现文件。BE-03-08 只改上传/补偿；BE-08 只读审核结果并写 exports。
- 与 BE-10 并行：BE-10 只写当前 master 已有能力的 E2E/API 测试；如果 BE-10 发现导出 endpoint 不存在，应等 BE-08 合并后补导出测试，不在 BE-10 中实现导出。
- 与 BE-09：仅在事件名已存在时调用 `LOCAL_EVENT_LOG.safe_write("export_succeeded" / "export_failed", ...)`；不得改变日志白名单、日志脱敏规则或写入字段全文。
- 潜在共享文件：`app/backend/services/task_service.py`。本任务只扩展 `mark_exported()` 与 export_summary 归一化，不修改 processing/review/cleanup 逻辑。若合并时 BE-09 已修改 task processing 日志，保留 BE-09 的 `_safe_event` 调用。

## 测试重点

- confirmed 任务导出检查通过。
- ready_for_review 任务导出检查失败，返回 `EXPORT_VALIDATION_FAILED`。
- review_result 缺失、字段为空、存在 unreviewed/suspicious/empty_unaccepted 时阻断导出。
- JSON 导出结构完整，字段值来自 `final_value`，不是 `auto_value`。
- JSON 字段顺序稳定。
- Excel 按字段组生成 sheet，字段值来自 `final_value`。
- 导出文件保存到 `exports/{task_id}/`，不混入其他任务。
- 导出成功后任务状态变为 `exported`，记录 export_summary。
- 导出失败不修改 review_result，不破坏 confirmed/exported 状态。
- 后端全量测试保持通过。
