# 采集会话管理设计（A-lite）

## 范围

采集会话核心容器：创建、查询、过期判定、锁定、finish 幂等、最小 Task 桩。对应 TDD 实施顺序第 3 步（`04-capture-sessions.md`），覆盖 BE-SES-001 ~ BE-SES-008。

本阶段覆盖：
- BE-SES-001：创建会话生成唯一 `session_id`
- BE-SES-002：创建会话记录 `created_at`、`expires_at`、`status: active`
- BE-SES-003：`POST /api/capture-sessions` 返回 201、会话信息和二维码 URL
- BE-SES-004：`GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间
- BE-SES-005：过期会话被判定为 `expired`
- BE-SES-006：过期会话上传返回 409 和 `SESSION_EXPIRED`（本阶段实现过期拒绝基
  础逻辑，上传端点本身在后续步骤实现）
- BE-SES-007：页面编辑相关端点骨架留到步骤 5，本阶段仅实现 `page_count` 字段占位
- BE-SES-008：`POST /api/mobile/{sessionId}/finish` 后会话变为 `locked`，创建
  最小 Task 桩

本阶段不覆盖：
- BE-SES-009：锁定后禁止编辑的页面级端点（步骤 5）
- BE-SES-010：页序固化集成测试（步骤 5）
- 图片上传、文件校验、文件存储（步骤 4）
- 任务生命周期编排（步骤 7）

## 技术选型

| 项 | 选择 |
|----|------|
| 路由层 | Flask Blueprint（新增 `capture_session_bp`） |
| 持久化 | 复用 `storage/json_store.py` 的 `JsonStore` |
| ID 生成 | `uuid.uuid4()` |
| 时间 | `datetime.now(timezone.utc).isoformat()` |

## 目录结构（新增/变更）

```
app/backend/
├── routes/
│   ├── capture_session.py   # NEW capture_session_bp
│   └── mobile.py            # NEW mobile_bp（finish 端点）
├── services/
│   └── session_service.py   # NEW 会话业务逻辑（无框架依赖）
├── tests/
│   ├── test_session_service.py  # NEW 单元测试
│   └── test_capture_session.py  # NEW API 集成测试
app/config/
└── default.yaml             # MODIFIED 新增 sessions 段
app/backend/config.py        # MODIFIED 展平 capture_session_ttl_minutes
```

## 数据模型

### Session（`data/sessions/{session_id}.json`）

```json
{
  "session_id": "uuid4",
  "status": "active",
  "created_at": "2026-05-11T10:00:00+00:00",
  "expires_at": "2026-05-11T10:30:00+00:00",
  "qr_code_url": "http://192.168.1.5:8081/mobile/a1b2c3d4",
  "page_count": 0,
  "locked_at": null,
  "task_id": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | UUID4，创建时生成 |
| `status` | string | `active` / `expired` / `locked` |
| `created_at` | string | ISO 8601 UTC |
| `expires_at` | string | ISO 8601 UTC，= `created_at` + `capture_session_ttl_minutes` |
| `qr_code_url` | string | 第一个可用 LAN 地址拼 `/mobile/{session_id}` |
| `page_count` | int | 创建时 0，后续上传端点更新 |
| `locked_at` | string\|null | finish 时写入，锁定前为 null |
| `task_id` | string\|null | finish 时写入 Task 桩 ID，锁定前为 null |

### Task 桩（`data/tasks/{task_id}.json`）

```json
{
  "task_id": "uuid4",
  "session_id": "a1b2c3d4",
  "status": "uploaded",
  "created_at": "2026-05-11T10:05:00+00:00",
  "page_count": 5,
  "source": "capture_session"
}
```

Task 桩严格保持 6 个字段。后续 `06-task-lifecycle.md` 步骤再扩展
`pages`/`document_result`/`fields`/`review_result`/`error_info` 等。

Task 桩初始状态 `"uploaded"`，而非 `"created"`：
- 会话 finish 意味着所有页面已上传完成，直接进入 `uploaded`
- 跳过 `created` → `uploading` → `uploaded` 的流转，因为采集阶段已隐含完成上传
- 若后续处理编排需要不同的起始状态，可在此处调整

## 配置

`app/config/default.yaml` 新增：

```yaml
sessions:
  capture_session_ttl_minutes: 30
```

`config.py` 变更：

- `DEFAULT_CONFIG` 新增 `"capture_session_ttl_minutes": 30`
- `_flatten_config` 新增对 `sessions.capture_session_ttl_minutes` 的展平
- 配置键名使用 `capture_session_ttl_minutes`，不用泛化的 `session_timeout`，
  避免后续与审核登录超时、任务锁等概念混淆

## API 契约

所有 API 路径前缀由 `create_backend_app` 注册 Blueprint 时统一管理。
响应格式遵循 `docs/Shared/error-codes.md` 的统一结构。

### POST /api/capture-sessions

创建采集会话。

**Request**: 无请求体。

**Response 201**:
```json
{
  "success": true,
  "data": {
    "session_id": "a1b2c3d4-...",
    "status": "active",
    "created_at": "2026-05-11T10:00:00+00:00",
    "expires_at": "2026-05-11T10:30:00+00:00",
    "qr_code_url": "http://192.168.1.5:8081/mobile/a1b2c3d4-...",
    "page_count": 0
  }
}
```

**实现要点**：
- `session_id` 用 `uuid4()`，确保离线环境唯一
- `qr_code_url` 取 `current_app.config["LAN_ADDRESSES"]` 第一个 + `/mobile/{session_id}`
- LAN_ADDRESSES 为空时，`qr_code_url` 为 null
- 调用 `SessionService` 创建并持久化

### GET /api/capture-sessions/{session_id}

查询会话信息。

**Response 200**:
```json
{
  "success": true,
  "data": {
    "session_id": "a1b2c3d4-...",
    "status": "active",
    "created_at": "2026-05-11T10:00:00+00:00",
    "expires_at": "2026-05-11T10:30:00+00:00",
    "qr_code_url": "http://192.168.1.5:8081/mobile/a1b2c3d4-...",
    "page_count": 0,
    "locked_at": null,
    "task_id": null
  }
}
```

**实现要点**：
- 读取 JSON 时检查 `expires_at`：若当前时间 > `expires_at` 且状态仍为 `active`，
  自动将状态更新为 `expired` 并回写持久化
- 会话不存在返回 `SESSION_NOT_FOUND`（404）
- 返回完整会话对象，包含 `locked_at` 和 `task_id`（active 时均为 null）

### POST /api/mobile/{session_id}/finish

完成采集，锁定会话。

**Request**: 无请求体。

**Response 200**（正常锁定）:
```json
{
  "success": true,
  "data": {
    "session_id": "a1b2c3d4-...",
    "status": "locked",
    "locked_at": "2026-05-11T10:05:00+00:00",
    "task_id": "e5f6g7h8-..."
  }
}
```

**Response 200**（幂等重复 finish）:
```json
{
  "success": true,
  "data": {
    "session_id": "a1b2c3d4-...",
    "status": "locked",
    "locked_at": "2026-05-11T10:05:00+00:00",
    "task_id": "e5f6g7h8-..."
  }
}
```
已锁定会话重复调用，返回已有锁定状态，不重复创建 Task。

**错误响应**:

| 条件 | HTTP | error.code |
|------|------|------------|
| 会话不存在 | 404 | `SESSION_NOT_FOUND` |
| 会话已过期 | 409 | `SESSION_EXPIRED` |

**实现要点**：
- `active` + 未过期 → 锁定：状态设为 `locked`，写入 `locked_at`，创建 Task 桩，
  回写 `task_id` 到会话 JSON
- `locked` → 幂等返回现有状态，不重复创建 Task
- `expired` → 拒绝，返回 `SESSION_EXPIRED`
- `cancelled` → 拒绝，返回 `SESSION_EXPIRED`（已取消等同于已过期，不可恢复）

## 模块接口契约

### services/session_service.py

```python
class SessionService:
    """采集会话业务逻辑，无 Flask 依赖，通过构造函数注入 JsonStore。
    
    职责：
    - 创建会话（生成 UUID、计算 expires_at、持久化）
    - 查询会话（读取 JSON、自动过期检测与回写）
    - 锁定会话（校验状态、创建 Task 桩、幂等返回）
    """

    def __init__(self, store: JsonStore, lan_addresses: list[str],
                 ttl_minutes: int):
        ...

    def create(self) -> dict:
        """创建 active 会话，写入 sessions/{id}.json，返回完整 dict。
        
        - session_id: uuid4
        - expires_at: created_at + ttl_minutes
        - qr_code_url: lan_addresses[0] + /mobile/{session_id}，无地址时为 null
        - page_count: 0
        """

    def get(self, session_id: str) -> dict:
        """读取会话，自动处理过期。
        
        - 不存在 → raise AppError(SESSION_NOT_FOUND)
        - active + 已过期 → 更新 status=expired 并回写，返回更新后的 dict
        - 其他状态直接返回
        """

    def finish(self, session_id: str) -> dict:
        """锁定会话并创建 Task 桩。
        
        - 调用 get() 获取当前状态
        - locked → 幂等返回已有状态
        - expired/cancelled → raise AppError(SESSION_EXPIRED)
        - active → 更新状态为 locked，写入 locked_at，创建 Task 桩，
          回写 task_id，返回 dict
        """
```

### routes/capture_session.py

```python
capture_session_bp = Blueprint("capture_session", __name__)

@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    """创建采集会话。返回 201。"""

@capture_session_bp.route("/api/capture-sessions/<session_id>")
def get_session(session_id: str):
    """查询会话信息。返回 200。"""
```

### routes/mobile.py

```python
mobile_bp = Blueprint("mobile", __name__)

@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id: str):
    """完成采集并锁定会话。返回 200。"""
```

### __init__.py 变更

```python
def create_backend_app(config_dir=None) -> Flask:
    ...
    # 新增：初始化 JsonStore 和 SessionService
    # 新增：注册 capture_session_bp 和 mobile_bp
```

## 状态流转

```
active ──[超时]──→ expired（get 时自动判定，持久化）
active ──[finish]──→ locked + 创建 Task 桩
expired ──[finish]──→ SESSION_EXPIRED 拒绝
cancelled ──[finish]──→ SESSION_EXPIRED 拒绝
locked ──[finish]──→ 幂等返回（不重复创建 Task）
expired ──[任何写操作]──→ 拒绝
locked ──[任何写操作]──→ 拒绝（步骤 5 实现具体拒绝端点）
```

## 存储布局

```
data/
├── sessions/
│   └── {session_id}.json    # 单个会话
└── tasks/
    └── {task_id}.json       # Task 桩（本阶段最小化）
```

JsonStore 实例化：
- 会话用 `JsonStore(base_dir=config["storage_dir"])`，读写路径 `sessions/{id}.json`
- Task 桩用同一 store，读写路径 `tasks/{id}.json`

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 对应 TDD ID |
|----------|------|-------------|
| `test_session_service.py` | 单元 | BE-SES-001, 002, 005 |
| `test_capture_session.py` | API 集成 | BE-SES-003, 004, 006, 007, 008 |

### test_session_service.py（单元测试）

不依赖 Flask app，直接实例化 SessionService + 临时目录 JsonStore。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_create_returns_dict_with_session_id` | BE-SES-001 | ID 为空 |
| `test_create_sets_active_status_and_timestamps` | BE-SES-002 | status 不是 active |
| `test_create_persists_to_json` | BE-SES-001 | 文件不存在 |
| `test_create_session_id_is_unique` | BE-SES-001 | 两次创建 ID 相同 |
| `test_get_returns_session` | BE-SES-004 | 查询返回 None |
| `test_get_nonexistent_raises_not_found` | BE-SES-004 | 不抛异常 |
| `test_get_auto_expires_when_past_expires_at` | BE-SES-005 | active 会话过期后仍返回 active |
| `test_get_auto_expire_persists_status_change` | BE-SES-005 | 文件仍为 active |
| `test_finish_locks_active_session` | BE-SES-008 | 状态未变为 locked |
| `test_finish_creates_task_stub` | BE-SES-008 | task_id 为 null |
| `test_finish_sets_locked_at` | BE-SES-008 | locked_at 为 null |
| `test_finish_idempotent_on_locked` | — | 重复 finish 抛异常或重复创建 Task |
| `test_finish_on_expired_raises_session_expired` | — | 未拒绝过期会话 finish |
| `test_finish_on_nonexistent_raises_not_found` | — | 未拒绝不存在会话 finish |
| `test_qr_code_url_uses_first_lan_address` | BE-SES-003 | URL 格式不对 |
| `test_qr_code_url_null_when_no_lan` | BE-SES-003 | 无 LAN 时崩溃 |

### test_capture_session.py（API 集成测试）

使用 Flask test client + 临时 config 目录 + 临时存储。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_create_session_returns_201` | BE-SES-003 | 路由缺失或状态码不对 |
| `test_create_session_response_has_qr_url` | BE-SES-003 | 响应结构缺失 qr_code_url |
| `test_get_session_returns_200` | BE-SES-004 | 查询接口缺失 |
| `test_get_nonexistent_session_returns_404` | BE-SES-004 | 不存在时未返回 404 |
| `test_finish_locks_session_returns_200` | BE-SES-008 | finish 接口缺失 |
| `test_finish_idempotent_returns_same_task_id` | — | 重复 finish 创建了不同 task_id |
| `test_finish_expired_session_returns_409` | BE-SES-006 | 过期会话 finish 未拒绝 |

## 不在此阶段实现

- 手机端页面采集、图片上传、文件校验（PR-BE-003）
- 会话内页面列表模型（pages schema）
- 页面删除、排序、补拍端点（步骤 5）
- 锁定后拒绝编辑的页面级端点（BE-SES-009）
- 页序固化集成测试（BE-SES-010）
- 任务生命周期编排（processing → ready_for_review 等）
- 文档解析、字段抽取、审核、导出
- 手机端前端页面
