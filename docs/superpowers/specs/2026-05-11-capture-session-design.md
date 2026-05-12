# 采集会话管理设计（A-lite）

## 范围

采集会话核心容器：创建、查询、过期判定、锁定、finish 幂等、最小 Task 桩。对应 PRD `PR-BE-002`，承接后端 TDD 实施顺序第 3 步（`docs/Backend/Backend_TDD/04-capture-sessions.md`）。

本阶段覆盖：

- BE-SES-001：创建会话生成唯一 `session_id`
- BE-SES-002：创建会话记录 `created_at`、`expires_at`、`status: active`
- BE-SES-003：`POST /api/capture-sessions` 返回 201、会话信息和二维码 URL
- BE-SES-004：`GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间
- BE-SES-005：过期会话被判定为 `expired`
- BE-SES-008：`POST /api/mobile/{session_id}/finish` 后会话变为 `locked`，并创建最小 Task 桩

本阶段只为 BE-SES-006/009/010 保留可衔接的服务层能力，不实现页面上传、页面编辑或页序固化端点：

- BE-SES-006 的“过期会话上传返回 409”在图片上传阶段实现；本阶段先实现通用过期判定和 finish 过期拒绝。
- BE-SES-009 的“locked 会话禁止新增、删除、排序页面”在页面管理阶段实现；本阶段先保证 `locked` 状态持久化。
- BE-SES-010 的“页面顺序固化”在页面模型明确后实现；本阶段不提前设计 `pages` schema。

本阶段不覆盖：

- 图片上传、文件类型校验、图片尺寸和四边形坐标保存（PRD `PR-BE-003` / `PR-BE-011`）
- 会话内页面列表模型、删除、排序、补拍、页序固化
- 任务生命周期编排、算法端口调用、解析结果、字段结果、审核结果、导出
- 手机端前端页面和二维码图片生成

## 设计原则

- 只实现本地后端状态与持久化，不实现 OCR、LLM、图像处理、裁剪、透视矫正或规则抽取。
- 使用 JSON 文件持久化，保证断网、重启后会话状态不丢失。
- Task 桩只表达“采集已完成并形成待后续处理的任务”，不提前设计页面、算法、审核和导出字段。
- 所有错误响应使用 `docs/Shared/error-codes.md` 中的统一结构，不返回堆栈。

## 技术选型

| 项 | 选择 |
|----|------|
| 路由层 | Flask Blueprint（新增 `capture_session_bp`、`mobile_bp`） |
| 持久化 | 复用 `storage/json_store.py` 的 `JsonStore` |
| ID 生成 | `uuid.uuid4()` |
| 时间 | `datetime.now(timezone.utc).isoformat()` |

## 目录结构（新增/变更）

```
app/backend/
├── routes/
│   ├── capture_session.py       # NEW capture_session_bp
│   └── mobile.py                # NEW mobile_bp（finish 端点）
├── services/
│   ├── __init__.py              # NEW
│   └── session_service.py       # NEW 会话业务逻辑（无 Flask 请求对象依赖）
├── tests/
│   ├── test_session_service.py  # NEW 单元测试
│   └── test_capture_session.py  # NEW API 集成测试
app/config/
└── default.yaml                 # MODIFIED 新增 sessions 段
app/backend/config.py            # MODIFIED 展平 capture_session_ttl_minutes
app/backend/__init__.py          # MODIFIED 注册服务与 Blueprint
```

## 数据模型

### Session（`data/sessions/{session_id}.json`）

```json
{
  "session_id": "uuid4",
  "status": "active",
  "created_at": "2026-05-11T10:00:00+00:00",
  "expires_at": "2026-05-11T10:30:00+00:00",
  "qr_code_url": "http://192.168.1.5:8081/mobile/uuid4",
  "page_count": 0,
  "locked_at": null,
  "task_id": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | UUID4，创建时生成 |
| `status` | string | `active` / `expired` / `locked` / `cancelled` |
| `created_at` | string | ISO 8601 UTC |
| `expires_at` | string | ISO 8601 UTC，= `created_at` + `capture_session_ttl_minutes` |
| `qr_code_url` | string 或 null | 第一个可用 LAN 地址拼 `/mobile/{session_id}`；无 LAN 地址时为 null |
| `page_count` | int | 创建时 0，后续上传端点更新 |
| `locked_at` | string 或 null | finish 时写入，锁定前为 null |
| `task_id` | string 或 null | finish 时写入 Task 桩 ID，锁定前为 null |

### Task 桩（`data/tasks/{task_id}.json`）

```json
{
  "task_id": "uuid4",
  "session_id": "uuid4",
  "status": "uploaded",
  "created_at": "2026-05-11T10:05:00+00:00",
  "page_count": 0,
  "source": "capture_session"
}
```

Task 桩严格保持以上 6 个字段。后续 `docs/Backend/Backend_TDD/06-task-lifecycle.md`、`07-algorithm-failure-contracts.md`、`09-review-results.md` 再扩展页面、解析结果、字段、审核结果和错误信息。

Task 桩初始状态使用 `"uploaded"`：

- PRD 中 finish 表示采集完成，后端应根据当前页面列表创建或更新任务，并进入 uploaded 或 processing 状态。
- 本阶段不启动算法处理，所以停在 `uploaded`。
- 后续上传阶段会补齐从 `created` / `uploading` 到 `uploaded` 的过程状态。

## 配置

`app/config/default.yaml` 新增：

```yaml
sessions:
  capture_session_ttl_minutes: 30
```

`config.py` 变更：

- `DEFAULT_CONFIG` 新增 `"capture_session_ttl_minutes": 30`
- `_flatten_config` 新增对 `sessions.capture_session_ttl_minutes` 的展平
- `_validate_config` 校验该值为正整数
- 配置键名使用 `capture_session_ttl_minutes`，不用泛化的 `session_timeout`，避免后续与审核登录超时、任务锁等概念混淆

## API 契约

所有响应遵循 `docs/Shared/error-codes.md` 的统一结构。

### POST /api/capture-sessions

创建采集会话。

**Request**: 无请求体。

**Response 201**:

```json
{
  "success": true,
  "data": {
    "session_id": "uuid4",
    "status": "active",
    "created_at": "2026-05-11T10:00:00+00:00",
    "expires_at": "2026-05-11T10:30:00+00:00",
    "qr_code_url": "http://192.168.1.5:8081/mobile/uuid4",
    "page_count": 0
  }
}
```

实现要点：

- `session_id` 用 `uuid4()`，确保离线环境唯一。
- `qr_code_url` 取 `current_app.config["LAN_ADDRESSES"]` 第一个地址，拼接 `/mobile/{session_id}`。
- `LAN_ADDRESSES` 为空时，`qr_code_url` 为 null，不阻断创建。电脑端后续可显示手动复制地址或重新生成二维码。
- 调用 `SessionService` 创建并持久化。

### GET /api/capture-sessions/{session_id}

查询会话信息。

**Response 200**:

```json
{
  "success": true,
  "data": {
    "session_id": "uuid4",
    "status": "active",
    "created_at": "2026-05-11T10:00:00+00:00",
    "expires_at": "2026-05-11T10:30:00+00:00",
    "qr_code_url": "http://192.168.1.5:8081/mobile/uuid4",
    "page_count": 0,
    "locked_at": null,
    "task_id": null
  }
}
```

实现要点：

- 读取 JSON 时检查 `expires_at`：若当前时间 > `expires_at` 且状态仍为 `active`，自动将状态更新为 `expired` 并回写持久化。
- 会话不存在返回 `SESSION_NOT_FOUND`（404）。
- 返回完整会话对象，包含 `locked_at` 和 `task_id`。

### POST /api/mobile/{session_id}/finish

完成采集，锁定会话。

**Request**: 无请求体。

**Response 200**（正常锁定或重复 finish）:

```json
{
  "success": true,
  "data": {
    "session_id": "uuid4",
    "status": "locked",
    "locked_at": "2026-05-11T10:05:00+00:00",
    "task_id": "uuid4"
  }
}
```

已锁定会话重复调用时返回现有锁定状态，不重复创建 Task。

错误响应：

| 条件 | HTTP | error.code |
|------|------|------------|
| 会话不存在 | 404 | `SESSION_NOT_FOUND` |
| 会话已过期 | 409 | `SESSION_EXPIRED` |
| 会话已取消 | 409 | `SESSION_LOCKED` |

实现要点：

- `active` + 未过期：状态设为 `locked`，写入 `locked_at`，创建 Task 桩，回写 `task_id` 到会话 JSON。
- `locked`：幂等返回现有状态，不重复创建 Task。
- `expired`：返回 `SESSION_EXPIRED`。
- `cancelled`：返回 `SESSION_LOCKED`，表达该会话已不可编辑/不可完成；不伪装为过期。

## 模块接口契约

### `services/session_service.py`

```python
class SessionService:
    """采集会话业务逻辑，通过构造函数注入 JsonStore、LAN 地址和 TTL。

    不直接依赖 Flask request/current_app，便于单元测试。
    """

    def __init__(self, store: JsonStore, lan_addresses: list[str], ttl_minutes: int):
        ...

    def create(self) -> dict:
        """创建 active 会话，写入 sessions/{id}.json，返回完整 dict。"""

    def get(self, session_id: str) -> dict:
        """读取会话，自动处理 active 过期。

        不存在时 raise AppError(ErrorCode.SESSION_NOT_FOUND)。
        """

    def finish(self, session_id: str) -> dict:
        """锁定会话并创建 Task 桩。

        locked 会话幂等返回；expired 会话拒绝；active 会话锁定并创建 Task 桩。
        """
```

### `routes/capture_session.py`

```python
capture_session_bp = Blueprint("capture_session", __name__)

@capture_session_bp.route("/api/capture-sessions", methods=["POST"])
def create_session():
    """创建采集会话。返回 201。"""

@capture_session_bp.route("/api/capture-sessions/<session_id>", methods=["GET"])
def get_session(session_id: str):
    """查询会话信息。返回 200。"""
```

### `routes/mobile.py`

```python
mobile_bp = Blueprint("mobile", __name__)

@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id: str):
    """完成采集并锁定会话。返回 200。"""
```

### `__init__.py` 变更

`create_backend_app(config_dir=None)` 中新增：

- 用 `config["storage_dir"]` 初始化 `JsonStore`
- 用 `LAN_ADDRESSES` 和 `capture_session_ttl_minutes` 初始化 `SessionService`
- 将服务对象挂到 `app.config["SESSION_SERVICE"]`
- 注册 `capture_session_bp` 和 `mobile_bp`

## 状态流转

```
active ──[超时]──→ expired（get 时自动判定，持久化）
active ──[finish]──→ locked + 创建 Task 桩
expired ──[finish]──→ SESSION_EXPIRED
cancelled ──[finish]──→ SESSION_LOCKED
locked ──[finish]──→ 幂等返回（不重复创建 Task）
expired ──[后续写操作]──→ SESSION_EXPIRED
locked ──[后续页面编辑写操作]──→ SESSION_LOCKED（页面管理阶段实现）
```

## 存储布局

```
data/
├── sessions/
│   └── {session_id}.json
└── tasks/
    └── {task_id}.json
```

JsonStore 实例化：

- 单一 `JsonStore(base_dir=config["storage_dir"])`
- 会话读写路径：`sessions/{session_id}.json`
- Task 桩读写路径：`tasks/{task_id}.json`

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 对应 TDD ID |
|----------|------|-------------|
| `test_session_service.py` | 单元 | BE-SES-001, 002, 005, 008 |
| `test_capture_session.py` | API 集成 | BE-SES-003, 004, 008 |

### `test_session_service.py`

不依赖 Flask app，直接实例化 `SessionService` + 临时目录 `JsonStore`。

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
| `test_finish_idempotent_on_locked` | BE-SES-008 | 重复 finish 抛异常或重复创建 Task |
| `test_finish_on_expired_raises_session_expired` | BE-SES-005 | 未拒绝过期会话 finish |
| `test_finish_on_nonexistent_raises_not_found` | BE-SES-004 | 未拒绝不存在会话 finish |
| `test_qr_code_url_uses_first_lan_address` | BE-SES-003 | URL 格式不对 |
| `test_qr_code_url_null_when_no_lan` | BE-SES-003 | 无 LAN 时崩溃 |
| `test_ttl_minutes_must_be_positive` | 配置契约 | 非正数 TTL 未被拒绝 |

### `test_capture_session.py`

使用 Flask test client + 临时 config 目录 + 临时存储。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_create_session_returns_201` | BE-SES-003 | 路由缺失或状态码不对 |
| `test_create_session_response_has_qr_url` | BE-SES-003 | 响应结构缺失 qr_code_url |
| `test_get_session_returns_200` | BE-SES-004 | 查询接口缺失 |
| `test_get_nonexistent_session_returns_404` | BE-SES-004 | 不存在时未返回 404 |
| `test_get_expired_session_returns_expired_status` | BE-SES-005 | 查询过期会话未转为 expired |
| `test_finish_locks_session_returns_200` | BE-SES-008 | finish 接口缺失 |
| `test_finish_idempotent_returns_same_task_id` | BE-SES-008 | 重复 finish 创建了不同 task_id |
| `test_finish_expired_session_returns_409` | BE-SES-005 | 过期会话 finish 未拒绝 |

## 与后续阶段的衔接

- PR-BE-003 图片上传阶段负责更新 `page_count`，并定义页面图像、四边形坐标、文件路径等数据。
- 页面管理阶段负责删除、排序、补拍和页序固化，不复用本阶段的 Task 桩作为最终页面顺序来源。
- 任务生命周期阶段读取 Task 桩，将 `uploaded` 任务推进到 `processing`，并按算法端口契约处理成功或失败。
- 算法模块缺失、异常、空结构化字段或契约非法时，后续任务必须进入 `failed`，本阶段不做任何降级或规则兜底。

## 自审结论

- 无 OCR、LLM、图像预处理、裁剪、透视矫正或规则抽取实现要求。
- 没有提前定义 `pages` schema，避免和上传/页面管理阶段冲突。
- 错误码只使用共享错误码；`cancelled` 不再伪装为 `SESSION_EXPIRED`。
- Task 桩限制为 6 个字段，避免提前侵入任务生命周期、审核和导出模型。
