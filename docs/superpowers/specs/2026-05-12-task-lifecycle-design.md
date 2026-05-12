# 任务生命周期管理设计（A-lite）

## 范围

对应 PRD `PR-BE-004`，承接后端 TDD 实施顺序第 6-7 步（`docs/Backend/Backend_TDD/06-task-lifecycle.md`、`07-algorithm-failure-contracts.md`）。

A-lite 阶段目标：任务状态机流转校验、任务列表/详情查询、触发处理骨架、失败重试、状态变更历史。不实现任何 OCR、LLM、图像处理或字段抽取算法，不编写算法模块适配器或 fixture。

本阶段覆盖：

- 任务状态机从 `uploaded` 起步（采集会话 finish 已创建 Task 桩，状态为 `uploaded`）
- 合法状态转换校验，非法转换返回 `INVALID_TASK_TRANSITION`
- `GET /api/tasks` 按 status 筛选
- `GET /api/tasks/{taskId}` 返回任务基本信息、页面摘要、状态历史
- `POST /api/tasks/{taskId}/process` 处理触发骨架（记录 `processing` 状态和 `processing_at`，不调算法；后续 BE-05 接入真实编排）
- `POST /api/tasks/{taskId}/retry` 从 `failed` 回到 `processing`
- 失败时保存 `error_code`、`error_message`、`failed_at`
- 状态变更写入历史记录

本阶段不覆盖：

- `created`、`uploading` 状态的流入路径（保留枚举值，但采集会话路径直达 `uploaded`）
- 算法模块调用、适配器、fixture（BE-05）
- OCR、LLM、图像处理、字段抽取实现（外部交付）
- 文档解析结果、结构化字段结果、审核结果、导出

## 设计原则

- 只实现状态机、查询、触发骨架和持久化；不实现任何算法行为。
- 使用 JSON 文件持久化任务数据，与现有 `data/tasks/{task_id}.json` 一致。
- 算法模块缺失时不自动降级；处理接口只做状态推进，不产生假数据。
- 所有错误响应使用 `docs/Shared/error-codes.md` 统一结构。

## 技术选型

| 项 | 选择 |
|----|------|
| 路由层 | 新建 `task_bp`，挂载 `/api/tasks` |
| 持久化 | 复用 `storage/json_store.py` 的 `JsonStore` |
| ID 生成 | 已有 Task 桩，不新增 ID 策略 |
| 时间 | `datetime.now(timezone.utc).isoformat()` |

## 目录结构（新增/变更）

```
app/backend/
├── routes/
│   └── task.py                    # NEW task_bp
├── services/
│   └── task_service.py            # NEW 任务状态机、查询、转换、历史
├── tests/
│   ├── test_task_service.py       # NEW 单元测试（状态机 + 查询 + 历史）
│   └── test_task_routes.py        # NEW API 集成测试
app/backend/
├── __init__.py                    # MODIFIED 注册 task_bp、TaskService
```

## 数据模型

### 任务（`data/tasks/{task_id}.json`）

在现有 Task 桩基础上扩展：

```json
{
  "task_id": "uuid4",
  "session_id": "uuid4",
  "status": "uploaded",
  "created_at": "2026-05-12T10:00:00+00:00",
  "page_count": 2,
  "page_order": ["page_id_1", "page_id_2"],
  "source": "capture_session",
  "error_code": null,
  "error_message": null,
  "failed_at": null,
  "processing_at": null,
  "ready_at": null,
  "status_history": [
    {
      "from_status": null,
      "to_status": "uploaded",
      "changed_at": "2026-05-12T10:00:00+00:00",
      "reason": "采集会话完成采集"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 已有，来自 finish |
| `session_id` | string | 已有 |
| `status` | string | `uploaded`/`processing`/`ready_for_review`/`confirmed`/`exported`/`failed` |
| `created_at` | string | 已有 |
| `page_count` | int | 已有 |
| `page_order` | list | 已有，固化后的 page_id 顺序 |
| `source` | string | 已有 |
| `error_code` | string/null | 失败时写入（如 `ALGORITHM_MODULE_NOT_CONFIGURED`），非失败态为 null |
| `error_message` | string/null | 失败时写入人类可读原因 |
| `failed_at` | string/null | 失败时写入 ISO 8601 UTC |
| `processing_at` | string/null | 进入 processing 时写入 |
| `ready_at` | string/null | 进入 ready_for_review 时写入 |
| `status_history` | list | 状态变更记录，每条含 `from_status`/`to_status`/`changed_at`/`reason` |

`status_history[0].from_status` 为 null 表示任务初始创建。

## 状态流转

```
finish 创建 Task 桩（uploaded）
    │
    ├── POST /api/tasks/{id}/process ──→ processing
    │                                       │
    │    ┌──────────────────────────────────┤
    │    │  (BE-05 算法成功)                │  (BE-05 算法失败)
    │    ↓                                  ↓
    │  ready_for_review                   failed
    │    │                                  │
    │    │  POST /api/tasks/{id}/retry ────→ processing
    │    │
    │    ↓
    │  confirmed → exported
    │
    └── (直接) → failed（手动标记，本阶段不实现此路径）
```

本阶段实现的状态转换：

| 当前状态 | 目标状态 | 触发方式 | 校验 |
|----------|----------|----------|------|
| `uploaded` | `processing` | `POST /.../process` | 合法 |
| `uploaded` | `failed` | 内部调用 | 合法（预留，本阶段不主动触发） |
| `processing` | `ready_for_review` | 内部调用 | 合法（BE-05 成功后调用） |
| `processing` | `failed` | 内部调用 | 合法（BE-05 失败后调用） |
| `failed` | `processing` | `POST /.../retry` | 合法 |
| `ready_for_review` | `processing` | 内部调用 | 合法（退回重处理） |
| `ready_for_review` | `failed` | 内部调用 | 合法 |
| `ready_for_review` | `confirmed` | 内部调用 | 合法（BE-07 审核确认后） |
| `confirmed` | `exported` | 内部调用 | 合法（BE-08 导出后） |
| 任意 → 任意（非法） | — | — | `INVALID_TASK_TRANSITION` |

`created`/`uploading` 在枚举中保留，合法转换表包含它们，但本阶段不实现流入路径的 API。

## API 契约

所有响应遵循 `docs/Shared/error-codes.md` 统一结构。

### GET /api/tasks

查询任务列表，支持按状态筛选。

**Query 参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 任务状态值，不传则返回全部 |

**Response 200：**

```json
{
  "success": true,
  "data": {
    "tasks": [
      {
        "task_id": "uuid4",
        "session_id": "uuid4",
        "status": "uploaded",
        "created_at": "2026-05-12T10:00:00+00:00",
        "page_count": 2
      }
    ]
  }
}
```

列表项只含摘要字段，不含完整 `page_order` 和 `status_history`。

筛选无效状态值时返回空列表而非报错。

### GET /api/tasks/{task_id}

返回任务详情。

**Response 200：**

```json
{
  "success": true,
  "data": {
    "task_id": "uuid4",
    "session_id": "uuid4",
    "status": "uploaded",
    "created_at": "2026-05-12T10:00:00+00:00",
    "page_count": 2,
    "page_order": ["page_id_1", "page_id_2"],
    "source": "capture_session",
    "error_code": null,
    "error_message": null,
    "failed_at": null,
    "processing_at": null,
    "ready_at": null,
    "status_history": [
      {
        "from_status": null,
        "to_status": "uploaded",
        "changed_at": "2026-05-12T10:00:00+00:00",
        "reason": "采集会话完成采集"
      }
    ]
  }
}
```

**错误响应：**

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |

### POST /api/tasks/{task_id}/process

触发任务处理。

**Request**：无请求体。

**Response 200：**

```json
{
  "success": true,
  "data": {
    "task_id": "uuid4",
    "status": "processing",
    "processing_at": "2026-05-12T10:05:00+00:00"
  }
}
```

**错误响应：**

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |
| 当前状态不允许 process | 400 | `INVALID_TASK_TRANSITION` |

实现要点：

- 仅允许 `uploaded` 或 `ready_for_review` 状态调用。
- 写入 `processing_at`，追加 `status_history` 记录。
- A-lite 阶段不调用任何算法模块。只做状态推进。
- 本阶段 process 停在 `processing`，不自动推进到 `ready_for_review`。

### POST /api/tasks/{task_id}/retry

失败任务重试。

**Request**：无请求体。

**Response 200：**

```json
{
  "success": true,
  "data": {
    "task_id": "uuid4",
    "status": "processing",
    "processing_at": "2026-05-12T10:05:00+00:00"
  }
}
```

**错误响应：**

| 条件 | HTTP | error.code |
|------|------|------------|
| 任务不存在 | 404 | `TASK_NOT_FOUND` |
| 当前状态不允许 retry | 400 | `INVALID_TASK_TRANSITION` |

实现要点：

- 仅允许 `failed` 状态调用。
- 清除 `error_code`、`error_message`、`failed_at`。
- 写入新的 `processing_at`，追加 `status_history`。
- 本阶段 retry 停在 `processing`，不重新执行算法。

## 模块职责

| 文件 | 职责 |
|------|------|
| `app/backend/services/task_service.py` | 状态机校验、合法转换表、任务读写、状态变更、历史追加、列表查询 |
| `app/backend/routes/task.py` | `task_bp`：列表、详情、process、retry 端点 |

### TaskService 接口契约

```python
class TaskService:
    def __init__(self, store: JsonStore):
        """通过 JsonStore 读写 data/tasks/{task_id}.json。"""

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """列出任务摘要。按 status 筛选时只返回匹配任务。"""

    def get_task(self, task_id: str) -> dict:
        """返回任务详情。不存在时 raise AppError(ErrorCode.TASK_NOT_FOUND)。"""

    def process(self, task_id: str) -> dict:
        """uploaded/ready_for_review → processing。
        非法状态 raise AppError(ErrorCode.INVALID_TASK_TRANSITION)。
        """

    def retry(self, task_id: str) -> dict:
        """failed → processing。
        非法状态 raise AppError(ErrorCode.INVALID_TASK_TRANSITION)。
        """

    def mark_ready(self, task_id: str) -> dict:
        """processing → ready_for_review（BE-05 成功后调用）。"""

    def mark_failed(self, task_id: str, error_code: str, error_message: str) -> dict:
        """任意非终态 → failed（BE-05 失败后调用）。
        写入 error_code/error_message/failed_at。
        """

    def mark_confirmed(self, task_id: str) -> dict:
        """ready_for_review → confirmed（BE-07 审核确认后调用）。"""

    def mark_exported(self, task_id: str) -> dict:
        """confirmed → exported（BE-08 导出后调用）。"""

    def _validate_transition(self, current: str, target: str) -> None:
        """校验状态转换合法性。非法 raise AppError(ErrorCode.INVALID_TASK_TRANSITION)。"""

    def _add_history(self, task: dict, target: str, reason: str) -> None:
        """追加状态历史记录到 task dict。"""
```

## 存储布局

```
data/tasks/
└── {task_id}.json    # 扩展后的任务 JSON（含 error_*、*_at、status_history）
```

与现有 Task 桩文件 `data/tasks/{task_id}.json` 格式兼容，finish 创建的文件被 process/retry/mark_* 原地更新。

## 与后续阶段的衔接

- BE-05 算法端口编排：`POST /api/tasks/{id}/process` 的真实实现接入图像处理→文档解析→字段抽取流水线，成功调用 `mark_ready()`，失败调用 `mark_failed()`。
- BE-07 人工审核：`mark_confirmed()` 在用户确认审核后调用。
- BE-08 导出：`mark_exported()` 在导出成功后调用。
- `created`/`uploading` 状态流入路径预留给非采集会话的任务创建方式（如后续支持手动创建任务）。

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 对应 TDD ID |
|----------|------|-------------|
| `test_task_service.py` | 单元 | BE-TASK-001, 002, 003, 006, 010 |
| `test_task_routes.py` | API 集成 | BE-TASK-004, 005, 007 |

### `test_task_service.py`

使用临时目录 `JsonStore`，不依赖 Flask app。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_task_initial_status_is_uploaded` | BE-TASK-001 | 现有 Task 桩状态不是 uploaded |
| `test_valid_transition_uploaded_to_processing` | BE-TASK-002 | 合法转换被拒绝 |
| `test_valid_transition_processing_to_ready` | BE-TASK-002 | ready_for_review 转换被拒绝 |
| `test_valid_transition_processing_to_failed` | BE-TASK-002 | failed 转换被拒绝 |
| `test_valid_transition_failed_to_processing` | BE-TASK-002 | retry 被拒绝 |
| `test_invalid_transition_uploaded_to_confirmed` | BE-TASK-003 | 非法转换被接受 |
| `test_invalid_transition_processing_to_uploaded` | BE-TASK-003 | 回退到 uploaded 被接受 |
| `test_invalid_transition_failed_to_confirmed` | BE-TASK-003 | 失败任务直接确认被接受 |
| `test_all_valid_transitions_match_state_enums` | BE-TASK-002 | 合法转换表与 Shared 定义不一致 |
| `test_process_sets_processing_at` | BE-TASK-002 | processing_at 未写入 |
| `test_mark_failed_saves_error_info` | BE-TASK-006 | error_code/message/failed_at 未保存 |
| `test_mark_failed_clears_error_on_retry` | BE-TASK-006 | retry 后错误信息未清除 |
| `test_status_history_appended` | BE-TASK-010 | 状态变更后历史未更新 |
| `test_status_history_has_correct_fields` | BE-TASK-010 | 历史记录缺少 from/to/changed_at/reason |
| `test_list_tasks_filters_by_status` | BE-TASK-004 | 筛选无效 |
| `test_list_tasks_returns_all_when_no_filter` | BE-TASK-004 | 空筛选返回空 |
| `test_get_task_returns_full_detail` | BE-TASK-005 | 详情缺字段 |
| `test_get_nonexistent_task_raises_not_found` | BE-TASK-005 | 不存在时未抛异常 |

### `test_task_routes.py`

使用 Flask test client + 临时 config 目录。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_list_tasks_returns_200` | BE-TASK-004 | 端点缺失 |
| `test_list_tasks_filter_by_status` | BE-TASK-004 | 筛选不生效 |
| `test_get_task_returns_200` | BE-TASK-005 | 详情端点缺失 |
| `test_get_nonexistent_task_returns_404` | BE-TASK-005 | 未返回 TASK_NOT_FOUND |
| `test_process_task_returns_200` | BE-TASK-002 | process 端点缺失 |
| `test_process_task_invalid_state_returns_400` | BE-TASK-003 | 非法转换未拒绝 |
| `test_retry_task_returns_200` | BE-TASK-007 | retry 端点缺失 |
| `test_retry_task_invalid_state_returns_400` | BE-TASK-003 | 非 failed 状态 retry 未拒绝 |

### 自审结论

- 无 OCR、LLM、图像处理、字段抽取实现要求。
- 算法模块调用全部留空；process/retry 只做状态推进。
- `created`/`uploading` 保留枚举值但本阶段不实现流入 API。
- Task 数据模型扩展字段（error_code/error_message/failed_at/processing_at/ready_at/status_history）均与现有 Task 桩兼容。
- 状态转换表覆盖所有 Shared/state-enums.md 定义的合法路径。
