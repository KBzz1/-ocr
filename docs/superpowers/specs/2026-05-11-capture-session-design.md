# 采集会话管理设计

## 范围

本设计覆盖 PRD `PR-BE-002`：创建采集会话、查询会话、过期判定、页面清单编辑、完成采集锁定、finish 幂等、页序固化和最小 Task 桩。

本阶段覆盖：

- BE-SES-001：创建会话生成唯一 `session_id`
- BE-SES-002：创建会话记录 `created_at`、`expires_at`、`status: active`
- BE-SES-003：`POST /api/capture-sessions` 返回 201、会话信息和二维码 URL
- BE-SES-004：`GET /api/capture-sessions/{id}` 返回会话页数、状态和过期时间
- BE-SES-005：过期会话被判定为 `expired`
- BE-SES-006：过期会话写操作返回 409 和 `SESSION_EXPIRED`
- BE-SES-007：完成采集前允许新增、删除、排序、补拍页面清单
- BE-SES-008：`POST /api/mobile/{session_id}/finish` 后会话变为 `locked`
- BE-SES-009：`locked` 会话禁止新增、删除、排序页面，返回 `SESSION_LOCKED`
- BE-SES-010：完成采集后页面顺序固化，Task 桩记录固化页序
- BE-SES-011：没有已成功上传页面的会话不可完成采集，返回 `SESSION_EMPTY`

本阶段不覆盖：

- 真实图片上传、文件类型/MIME/大小校验、图片落盘
- `quad_points`、图片宽高、原图路径、处理后图片路径
- OCR、LLM、图像预处理、裁剪、透视矫正、规则抽取
- 任务从 `uploaded` 到 `processing` / `ready_for_review` / `failed` 的生命周期编排
- 手机端前端页面和二维码图片生成

## 技术选型

| 项 | 选择 |
|----|------|
| 路由层 | Flask Blueprint：`capture_session_bp`、`mobile_bp` |
| 业务层 | `SessionService`，无 Flask 请求对象依赖 |
| 持久化 | 复用 `storage/json_store.py` 的 `JsonStore` |
| ID 生成 | `uuid.uuid4()` |
| 时间 | `datetime.now(timezone.utc).isoformat()` |

## 数据模型

### Session（`data/sessions/{session_id}.json`）

```json
{
  "session_id": "uuid4",
  "status": "active",
  "created_at": "2026-05-12T10:00:00+00:00",
  "expires_at": "2026-05-12T10:30:00+00:00",
  "qr_code_url": "http://192.168.1.5:8081/mobile/uuid4",
  "page_count": 0,
  "pages": [],
  "locked_at": null,
  "task_id": null
}
```

页面清单项：

```json
{
  "page_id": "uuid4",
  "page_no": 1,
  "created_at": "2026-05-12T10:01:00+00:00",
  "upload_ref": null
}
```

`pages` 是唯一页序来源。PR-BE-003 图片上传阶段会把真实页面元数据路径写入 `upload_ref`，例如 `pages/{session_id}/{page_id}.json`。

### Task 桩（`data/tasks/{task_id}.json`）

```json
{
  "task_id": "uuid4",
  "session_id": "uuid4",
  "status": "uploaded",
  "created_at": "2026-05-12T10:05:00+00:00",
  "page_count": 2,
  "page_order": ["page-1", "page-2"],
  "source": "capture_session"
}
```

Task 桩只表达采集已完成并形成待处理任务，不实现 processing、算法调用、状态流转历史、失败重试、审核或导出。

## 配置

`app/config/default.yaml` 新增：

```yaml
sessions:
  capture_session_ttl_minutes: 30
```

`settings.py` 变更：

- `DEFAULT_CONFIG` 新增 `"capture_session_ttl_minutes": 30`
- `_flatten_config` 展平 `sessions.capture_session_ttl_minutes`
- `_validate_config` 校验 TTL 为正整数

## API 契约

### POST /api/capture-sessions

创建 active 采集会话，返回 201。

响应包含：

- `session_id`
- `status`
- `created_at`
- `expires_at`
- `qr_code_url`
- `page_count`

LAN 地址为空时，`qr_code_url` 为 null，不阻断创建。

### GET /api/capture-sessions/{session_id}

查询会话信息，返回完整 Session JSON。

读取时若 `status == active` 且当前时间超过 `expires_at`，自动转为 `expired` 并持久化。

不存在返回 `SESSION_NOT_FOUND`。

### POST /api/capture-sessions/{session_id}/pages

在 active 会话中新增页面清单项，返回更新后的会话。

本阶段不接收真实图片文件。真实上传由 PR-BE-003 的 `POST /api/mobile/{session_id}/pages` 接入，并复用同一会话服务。

### DELETE /api/capture-sessions/{session_id}/pages/{page_id}

在 active 会话中删除页面清单项，删除后重新编号 `page_no`。

页面不存在返回 `SESSION_NOT_FOUND`。

### PUT /api/capture-sessions/{session_id}/pages/order

在 active 会话中按 `page_ids` 重排页面顺序，重排后重新编号 `page_no`。

`page_ids` 必须与当前页面集合完全一致，否则返回 `SESSION_NOT_FOUND`。

### POST /api/mobile/{session_id}/finish

完成采集，锁定会话并创建最小 Task 桩。

行为：

- active 且所有当前页面均已成功上传并写回 `upload_ref`：写入 `locked_at`，状态变为 `locked`，创建 Task 桩，固化 `page_order`
- locked：幂等返回当前 locked 状态和已有 `task_id`
- expired：返回 `SESSION_EXPIRED`
- cancelled：返回 `SESSION_LOCKED`
- active 但没有页面，或存在尚未写回 `upload_ref` 的占位页面：返回 `SESSION_EMPTY`

## SessionService 契约

```python
class SessionService:
    def create(self) -> dict:
        """创建 active 会话。"""

    def get(self, session_id: str) -> dict:
        """读取会话，自动处理 active 过期。"""

    def add_page(self, session_id: str, upload_ref=None) -> dict:
        """在 active 会话中新增页面项。"""

    def attach_page_upload(self, session_id: str, page_id: str, upload_ref: str) -> dict:
        """把真实上传阶段产生的元数据路径写回页面项。"""

    def delete_page(self, session_id: str, page_id: str) -> dict:
        """删除页面项并重新编号。"""

    def reorder_pages(self, session_id: str, page_ids: list[str]) -> dict:
        """按指定 page_id 顺序重排页面项。"""

    def finish(self, session_id: str) -> dict:
        """锁定会话、固化页序并创建 Task 桩。"""
```

写操作 guard：

- `active`：允许写入
- `expired`：返回 `SESSION_EXPIRED`
- `locked` / `cancelled`：返回 `SESSION_LOCKED`

## 错误码

本阶段使用共享错误码：

| 错误码 | HTTP | 场景 |
|--------|------|------|
| `SESSION_NOT_FOUND` | 404 | 会话不存在，或页面项不存在 |
| `SESSION_EXPIRED` | 409 | 会话已过期 |
| `SESSION_LOCKED` | 409 | 会话已完成采集或已取消，禁止编辑 |
| `SESSION_EMPTY` | 400 | 会话没有已成功上传页面，不能完成采集 |

## 与 PR-BE-003 的衔接

PR-BE-003 图片上传阶段必须复用本阶段的 `SessionService`：

- 上传前调用会话写操作 guard
- 页面 `page_id` / `page_no` 由会话 `pages` 清单分配
- 图片和元数据保存成功后调用 `attach_page_upload(...)` 写回 `upload_ref`
- 文件模块不得扫描 `data/pages/{session_id}/` 自行推导页序
- finish 固化仍以会话 `pages` 顺序为准

## 测试策略

单元测试：

- 创建唯一会话
- active 状态、时间和空 pages 初始化
- get 自动过期并持久化
- add/delete/reorder 页面清单
- expired/locked 写操作 guard
- attach_page_upload 写回 upload_ref
- finish 锁定、Task 桩、page_order、幂等
- 无已上传页面或存在占位页面时 finish 返回 `SESSION_EMPTY`

API 测试：

- 创建会话返回 201 和二维码 URL
- 查询会话返回 pages
- 新增/删除/排序页面
- finish 锁定并返回 task_id
- locked 后禁止页面写入
- expired 后禁止页面写入和 finish
- 无已上传页面或存在占位页面时 finish 返回 400 和 `SESSION_EMPTY`

## 自审结论

- 不实现 OCR、LLM、图像预处理、裁剪、透视矫正或规则抽取。
- 不接入真实图片上传，避免和 PR-BE-003 职责重叠。
- 会话 `pages` 是唯一页序来源，避免后续上传分支割裂。
- Task 桩保持最小，不进入任务生命周期编排。
