# BE-10 后端 E2E 契约测试设计

## 范围

对应 `docs/PRD任务清单.md` 中：

- BE-10-01 API 全量契约测试
- BE-10-02 成功 fixture 主流程
- BE-10-03 失败 fixture 主流程

本阶段目标是为当前后端主流程建立 E2E 和 API 契约回归网。此任务原则上只新增测试和 fixtures，不新增业务功能。若测试发现当前实现存在真实 bug，只允许做最小修复，并单独提交说明。

本阶段覆盖当前 master 已有能力：

- 系统状态和维护接口基本契约。
- 采集会话创建、查询、上传页面、finish 幂等。
- 上传图片和 quad 元数据的 API 契约。
- 任务处理成功 fixture 主流程：多页上传 → finish → process → `ready_for_review`。
- 算法未配置/失败/空字段/非法契约失败主流程：进入 `failed`，不得进入审核。
- 审核读取、字段修改、确认主流程。
- 本地日志和离线检查的基本契约。

本阶段暂不覆盖：

- BE-08 导出服务的真实 endpoint，除非 BE-08 已先合并到当前分支。
- 前端 E2E。
- Windows `.bat` 手动验收。
- OCR、LLM、图像处理质量或语义正确性。

## 权威依据

- `docs/产品PRD.md`：业务主流程、后端 PRD。
- `docs/Shared/state-enums.md`。
- `docs/Shared/error-codes.md`。
- `docs/Backend/Backend_TDD/12-api-contracts.md`。
- `docs/Backend/Backend_TDD/14-fixtures.md`。
- `docs/Backend/Backend_TDD/02-algorithm-ports.md`。
- `docs/Backend/Backend_TDD/07-algorithm-failure-contracts.md`。
- `docs/Backend/Backend_TDD/09-review-results.md`。
- `docs/Backend/Backend_TDD/11-logging-privacy.md`。
- `docs/Backend/Backend_BDD/capture-session.md`。
- `docs/Backend/Backend_BDD/task-lifecycle.md`。
- `docs/Backend/Backend_BDD/review-persistence.md`。
- `docs/Backend/Backend_BDD/logging-privacy.md`。

## 设计原则

- 测试使用本地 fixtures，不调用真实算法，不访问外网。
- E2E 测试只验证本系统契约，不验证 OCR/LLM 质量。
- 成功 fixture 的字段候选必须来自 fixture 算法端口，不在测试中根据 OCR/schema 推断。
- 失败主流程必须断言 `failed` 状态和标准错误码，且不得进入审核态。
- 下载/导出相关测试只在对应功能存在后补充，不能在 BE-10 中伪造业务实现。

## 文件边界

```text
app/backend/tests/
├── test_backend_e2e.py                 # NEW 后端主流程 E2E
├── test_api_contracts.py               # NEW 成功/错误响应契约
├── fixtures/
│   ├── __init__.py                     # NEW fixture package
│   ├── images.py                       # NEW 最小图片 bytes helpers
│   └── algorithm.py                    # NEW 成功/失败算法 fixture helpers
└── conftest.py                         # OPTIONAL 仅当能减少重复且不破坏现有测试
```

原则上不修改业务文件。允许的最小 bugfix 示例：

- 某 endpoint 返回错误码与 `docs/Shared/error-codes.md` 明显不一致。
- 某失败路径泄露堆栈或返回 500。
- E2E 揭示已有 API 不能按文档完成主流程。

不允许修改：

- `app/backend/services/algorithm_ports/` 的真实端口契约以迎合测试。
- `app/backend/services/review_service.py` 的数据结构。
- `run.bat` / `stop.bat`。
- `app/frontend/`。

## Fixtures

### 图片 fixture

使用内存 bytes，不提交真实病历图片：

```python
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 128
PNG_BYTES = b"\x89PNG" + b"\x00" * 128
PDF_BYTES = b"%PDF-1.4 not image"
```

### 成功算法 fixture

E2E 中可以直接注入当前 app 的 `TASK_SERVICE` 所依赖 orchestrator，或使用现有 `ProcessingOrchestrator` + fixture ports。成功 fixture 必须返回：

- image processing：每页 processed path。
- document parsing：pages、blocks、tables、merged_text。
- field extraction：schema 中存在的字段候选，至少包含 `chief_complaint` 或当前 schema 中一个稳定字段。

字段值示例：

```json
{
  "field_key": "chief_complaint",
  "field_name": "主诉",
  "original_value": "fixture value from external extractor",
  "evidence": "fixture evidence",
  "page_no": 1,
  "confidence": "medium"
}
```

说明：字段值只代表外部模块返回，不代表本项目抽取能力。

### 失败算法 fixture

覆盖：

- 算法未配置：`ALGORITHM_MODULE_NOT_CONFIGURED`。
- 算法异常：`ALGORITHM_MODULE_FAILED`。
- 空结构化字段：`ALGORITHM_CONTRACT_INVALID` 或当前 BE-05 定义的标准失败码。
- 非法字段 key：任务进入 `failed`。

具体错误码以当前 `docs/Shared/error-codes.md` 和现有 BE-05 测试为准，不在 BE-10 中新增错误码。

## E2E 流程

### 成功主流程

```text
GET /api/system/status
  ↓
POST /api/capture-sessions
  ↓
POST /api/mobile/{session_id}/pages  上传第 1 页
  ↓
POST /api/mobile/{session_id}/pages  上传第 2 页
  ↓
POST /api/mobile/{session_id}/finish
  ↓
POST /api/tasks/{task_id}/process  使用成功 fixture 算法
  ↓
GET /api/tasks/{task_id}
  ↓
GET /api/tasks/{task_id}/review
  ↓
PATCH /api/tasks/{task_id}/review/fields/{field_key}
  ↓
POST /api/tasks/{task_id}/review/confirm
```

断言：

- session 从 `active` 到 `locked`。
- task 从 `uploaded` 到 `processing` 到 `ready_for_review` 到 `confirmed`。
- review_result 来自 fixture 字段候选。
- `final_value` 修改后持久化。
- 自动候选文件没有被覆盖。

### 失败主流程

```text
POST /api/capture-sessions
  ↓
POST /api/mobile/{session_id}/pages
  ↓
POST /api/mobile/{session_id}/finish
  ↓
POST /api/tasks/{task_id}/process  使用失败 fixture 或未配置算法
  ↓
GET /api/tasks/{task_id}
  ↓
GET /api/tasks/{task_id}/review
```

断言：

- task 最终为 `failed`。
- task 记录 `error_code`、`error_message`、`failed_at`。
- 审核入口返回 `INVALID_TASK_TRANSITION`，不得初始化 review_result。

## API 契约测试

覆盖：

- 所有成功 JSON API 返回 `{success: true, data: ...}`。
- 所有失败 API 返回 `{error: {code, message, details}}`，不包含堆栈。
- 404 session/task 返回对应错误码。
- 上传缺少 image 返回 `INVALID_REQUEST_PARAMS`。
- 非图片上传返回 `UNSUPPORTED_FILE_TYPE`。
- 重复 finish 同一 session 幂等返回同一 task_id。
- 排序未知 page_id 整体拒绝，不局部应用。
- `/api/maintenance/offline-check` 只返回本地检查结构。

下载响应（BE-08 合并后补充）：

- JSON/Excel 导出 endpoint 返回明确 `Content-Disposition` 和内容类型。
- BE-08 未合并前，BE-10 不新增导出 endpoint 测试。

## 日志和隐私契约

E2E 只验证日志摘要：

- 产生 `system_started`、`session_created`、`page_uploaded`、`session_finished`、处理失败/成功相关事件。
- 日志中不出现图片 bytes、base64、身份证号、完整 OCR/病历文本。
- 不断言日志顺序过细，避免和实现细节耦合。

## 与其他任务的边界

- 与 BE-03-08 并行：如果 BE-03-08 尚未合并，BE-10 不强制新增上传失败补偿 E2E；可在 spec/plan 中列为合并后扩展。
- 与 BE-08 并行：BE-10 不实现导出，不要求导出 endpoint 存在；BE-08 合并后再补导出 E2E。
- 与前端任务无交集。

## 测试重点

- 成功主流程使用本地算法 fixture，最终可进入 confirmed。
- 失败主流程不会进入审核。
- API 成功/失败响应结构稳定。
- 错误响应不泄露堆栈。
- 日志不泄露敏感内容。
- E2E 过程中不访问外部网络。
- 后端全量测试保持通过。
