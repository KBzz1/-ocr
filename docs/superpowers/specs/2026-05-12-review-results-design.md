# 人工审核结果设计（BE-07）

## 范围

对应 PRD `PR-BE-008`，覆盖 `docs/PRD任务清单.md` 中：

- BE-07-01 审核结果读取
- BE-07-02 字段编辑保存
- BE-07-03 任务确认校验

本阶段承接 BE-05 外部算法端口和 BE-06 schema 管理。任务只有在 `ready_for_review` 状态且已有外部字段候选结果时，才允许进入审核结果读取、字段保存和任务确认流程。

本阶段覆盖：

- 首次读取审核结果时，基于 `results/{task_id}/field_candidates.json` 初始化人工审核记录。
- 人工审核结果与自动候选结果分开保存，不覆盖字段候选文件。
- 支持字段确认、修改、清空、标记存疑。
- 保存字段最终值、审核状态、审核时间和修改痕迹。
- 确认任务前统计未审核、存疑、空值和无来源字段。
- 满足确认条件后把任务从 `ready_for_review` 推进到 `confirmed`。
- `failed`、`uploaded`、`processing` 等非审核态任务不得读取正常审核流、保存审核或确认。

本阶段不覆盖：

- JSON/Excel 导出（BE-08）。
- 前端审核页面交互。
- OCR、LLM、图像处理、规则抽取或字段补造。
- 根据 schema 或 OCR 文本生成缺失字段。
- 真实日志落盘策略（BE-09），但必须避免在错误 details 中放入敏感全文。

## 权威依据

- `docs/产品PRD.md`：PR-BE-008、PR-FE-004、PR-FE-005、PR-FE-006。
- `docs/Shared/state-enums.md`：任务状态和字段状态。
- `docs/Shared/error-codes.md`：`REVIEW_VALIDATION_FAILED`、`TASK_NOT_FOUND`、`INVALID_TASK_TRANSITION`。
- `docs/Backend/Backend_BDD/review-persistence.md`。
- `docs/Backend/Backend_TDD/09-review-results.md`。
- `docs/superpowers/specs/2026-05-12-algorithm-ports-design.md`。
- `docs/superpowers/specs/2026-05-12-schema-loader-design.md`。

## 设计原则

- 自动候选结果是外部算法输出，只读保存；人工审核结果单独落盘。
- 初始化审核记录只复制候选字段，不新增 schema 中缺失但外部未返回的字段。
- 后端只做审核状态、最终值、修改痕迹和确认校验，不推断字段值。
- `failed` 任务不能通过审核流程绕过算法失败。
- 确认任务是后端权威状态流转，前端不能绕过未审核、存疑或未确认空值。

## 文件边界

```text
app/backend/
├── services/
│   ├── review_service.py              # NEW 审核结果初始化、读取、保存、确认校验
│   └── algorithm_ports/results.py     # READ 读取 field_candidates，不改自动结果契约
├── routes/
│   └── review.py                      # NEW 审核结果 API
├── tests/
│   ├── test_review_service.py         # NEW 服务层单元/集成测试
│   └── test_review_routes.py          # NEW API 契约测试
└── __init__.py                        # MODIFIED 注册 ReviewService 和 review_bp
```

不修改：

- `app/backend/services/algorithm_ports/orchestrator.py`：BE-07 不改变算法编排。
- `app/backend/services/schema_validator.py`：BE-07 只读取 schema 顺序和字段显示信息，不改变 BE-06 校验规则。
- `exports/`：BE-08 再写导出。

## 数据模型

审核结果写入：

```text
results/{task_id}/review_result.json
```

结构：

```json
{
  "task_id": "task_001",
  "schema_version": "medical_record.v1",
  "document_type": "medical_record",
  "initialized_at": "2026-05-12T10:00:00+00:00",
  "updated_at": "2026-05-12T10:05:00+00:00",
  "fields": [
    {
      "field_key": "chief_complaint",
      "field_name": "主诉",
      "auto_value": "头痛3天",
      "final_value": "头痛3天",
      "evidence": "第1页第2行",
      "page_no": 1,
      "confidence": 0.95,
      "status": "unreviewed",
      "empty_accepted": false,
      "review_note": null,
      "reviewed_at": null,
      "updated_at": null,
      "history": []
    }
  ],
  "summary": {
    "total_count": 1,
    "unreviewed_count": 1,
    "confirmed_count": 0,
    "modified_count": 0,
    "suspicious_count": 0,
    "empty_count": 0,
    "empty_unaccepted_count": 0,
    "missing_evidence_count": 0
  }
}
```

字段初始化规则：

- `auto_value` 来自候选字段 `original_value`。
- `final_value` 初始等于 `auto_value`。
- `status` 初始为 `unreviewed`。
- `field_name` 优先来自当前 schema；schema 没有显示名时使用候选字段自带 `field_name`；仍缺失时使用 `field_key`。
- 字段顺序按 schema 字段顺序排列；schema 中没有但候选里存在的字段不应出现，因为 BE-06 已在处理阶段阻断。
- `evidence` 可以为空；无来源字段不阻断保存，但确认前需统计提示。

字段状态规则：

| 操作 | final_value | status | empty_accepted |
|------|-------------|--------|----------------|
| confirm | 请求值或当前值 | `confirmed` | false |
| modify | 请求值 | `modified` | false |
| mark_suspicious | 当前值 | `suspicious` | false |
| clear | `""` | `empty` | false |
| accept_empty | `""` | `empty` | true |

确认任务阻断规则：

- 存在 `unreviewed` 字段：阻断，返回 `REVIEW_VALIDATION_FAILED`。
- 存在 `suspicious` 字段：阻断，返回 `REVIEW_VALIDATION_FAILED`。
- 存在 `empty` 且 `empty_accepted != true` 字段：阻断，返回 `REVIEW_VALIDATION_FAILED`。
- 字段数量为 0：阻断，返回 `REVIEW_VALIDATION_FAILED`。
- 无来源字段只计入 summary，不阻断确认；前端应提示人工核验。

## API 契约

### GET /api/tasks/{task_id}/review

首次调用时初始化审核结果；后续调用返回已保存结果。

成功响应：

```json
{
  "success": true,
  "data": {
    "task_id": "task_001",
    "status": "ready_for_review",
    "review_result": {}
  }
}
```

错误：

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |
| 任务不是 `ready_for_review` 或 `confirmed` | 400 | `INVALID_TASK_TRANSITION` |
| 字段候选文件缺失或为空 | 400 | `REVIEW_VALIDATION_FAILED` |

### PATCH /api/tasks/{task_id}/review/fields/{field_key}

请求：

```json
{
  "action": "modify",
  "final_value": "头痛3天，加重1天",
  "review_note": "按原文修正"
}
```

`action` 允许：`confirm`、`modify`、`clear`、`accept_empty`、`mark_suspicious`。

成功后返回完整 review_result，便于前端刷新统计。

校验：

- 任务必须是 `ready_for_review`。
- `field_key` 必须存在于 review_result。
- `modify` 和 `confirm` 的 `final_value` 必须是字符串；`clear` 和 `accept_empty` 将最终值置为空字符串。
- `review_note` 可选，必须是字符串或 null。

### POST /api/tasks/{task_id}/review/confirm

确认任务。

成功：

- 任务状态从 `ready_for_review` 变更为 `confirmed`。
- response 返回任务详情和 review summary。

失败：

```json
{
  "error": {
    "code": "REVIEW_VALIDATION_FAILED",
    "message": "审核确认校验失败",
    "details": {
      "unreviewed": ["chief_complaint"],
      "suspicious": [],
      "empty_unaccepted": [],
      "missing_evidence_count": 0
    }
  }
}
```

## 并行与合并边界

- 可与 BE-09 并行。BE-09 如果需要记录审核事件，应只调用 ReviewService 暴露的事件点或路由层结果，不改变审核数据结构。
- 可与 BE-01 并行。BE-01 不应修改审核服务、结果路径或任务确认规则。
- BE-08 必须等待本 spec 合并后再实现导出，以 `review_result.json` 为最终值来源。
- FE-04 可基于本 API 契约做页面，但不得在前端自行补造字段或绕过确认校验。

## 测试重点

- 首次读取基于字段候选初始化 review_result。
- 再次读取不覆盖已有人工修改。
- 自动候选文件未被修改。
- confirm、modify、clear、accept_empty、mark_suspicious 分别更新状态和 history。
- failed 任务、processing 任务不能进入审核流。
- 确认任务阻断未审核、存疑、未接受空值。
- 确认成功后任务进入 `confirmed`。
- 后端全量测试保持通过。
