# 图片上传与文件管理设计

## 范围

对应 PRD `PR-BE-003`、`PR-BE-011`，承接后端 TDD 实施顺序第 4 步（`docs/Backend/Backend_TDD/05-file-upload.md`）。

本阶段必须衔接已合并到主分支的 PR-BE-002 采集会话管理。PR-BE-002 的会话 JSON 维护 `pages` 清单，并负责 active/expired/locked 写操作 guard、页面顺序、page_count、finish 页序固化和最小 Task 桩。本阶段只把真实图片文件和采集元数据接入该页面清单，不另建独立页序模型。

本阶段覆盖：

- 图片文件类型校验：jpg/jpeg/png/bmp
- 基于 magic bytes 的真实类型检测，不信任用户文件名和 Content-Type
- 文件大小限制配置
- 文件名净化和路径安全校验
- `quad_points` 校验：4 点、数字、范围内、不自相交、面积过小
- 上传原图保存 + 页面元数据 JSON 持久化
- 上传成功后写回会话页面项 `upload_ref`
- 上传阶段不调用 OCR，不执行后端图像处理、裁剪或透视矫正

本阶段不覆盖：

- 页面删除、排序、补拍 API（由 PR-BE-002 会话管理提供）
- finish 时页序固化（由 PR-BE-002 会话管理提供）
- processed image 生成或记录（BE-FILE-011 延后到算法端口/任务处理阶段）
- 删除任务时清理任务目录（BE-FILE-012 延后到任务删除能力）
- 任务生命周期推进、算法模块调用、审核和导出

## 与 PR-BE-002 的衔接

PR-BE-002 计划中的会话页面项为：

```json
{
  "page_id": "uuid4",
  "page_no": 1,
  "created_at": "2026-05-12T10:01:00+00:00",
  "upload_ref": null
}
```

PR-BE-003 上传成功后，必须把 `upload_ref` 更新为页面元数据 JSON 的相对路径：

```json
{
  "page_id": "uuid4",
  "page_no": 1,
  "created_at": "2026-05-12T10:01:00+00:00",
  "upload_ref": "pages/{session_id}/{page_id}.json"
}
```

衔接规则：

- `SessionService` / 会话 JSON 的 `pages` 清单是唯一页序来源。
- 上传模块不得扫描 `data/pages/{session_id}/` 来计算 `page_no`。
- 上传模块不得绕过会话服务直接修改会话状态。
- `POST /api/mobile/{session_id}/pages` 语义是“上传真实图片并创建/更新会话页面项”。
- finish 固化仍由 PR-BE-002 的 `SessionService.finish()` 负责，读取会话 `pages` 顺序生成 Task 桩 `page_order`。

主分支已提供以下会话服务方法。PR-BE-003 必须复用这些方法，不绕过 `SessionService` 直接修改会话 JSON：

```python
class SessionService:
    def add_page(self, session_id: str, upload_ref=None) -> dict:
        """在 active 会话中创建页面项。

        missing -> SESSION_NOT_FOUND
        expired -> SESSION_EXPIRED
        locked/cancelled -> SESSION_LOCKED
        """

    def attach_page_upload(self, session_id: str, page_id: str, upload_ref: str) -> dict:
        """把页面元数据引用写回指定页面项。"""
```

## 设计原则

- 只实现文件校验、quad 校验、文件存储和元数据持久化。
- 不实现 OCR、LLM、图像处理、裁剪、透视矫正或规则抽取。
- 使用 JSON 文件持久化页面元数据，保证断网、重启后数据不丢失。
- 不创建 Task；finish 和 Task 桩仍由 PR-BE-002 会话服务负责。
- 所有错误响应使用 `docs/Shared/error-codes.md` 的统一结构，不返回堆栈。

## 技术选型

| 项 | 选择 |
|----|------|
| 路由层 | 追加到已有 `mobile_bp`，新增 `POST /api/mobile/<session_id>/pages` |
| 文件保存 | 写入 `data/pages/{session_id}/`，路径由 `PageService` 生成并做安全校验 |
| ID 生成 | `SessionService.add_page()` 分配 `page_id` |
| 时间 | `datetime.now(timezone.utc).isoformat()` |
| 文件类型检测 | magic bytes 头检测 |

## 目录结构

```
app/backend/
├── routes/
│   └── mobile.py                # MODIFIED 新增 upload_page 端点
├── services/
│   ├── file_validator.py        # NEW magic bytes、类型白名单、大小校验、路径安全
│   ├── quad_validator.py        # NEW 点数量、数字性、范围、自相交、面积校验
│   └── page_service.py          # NEW 调用 SessionService，保存图片和元数据
├── tests/
│   ├── test_file_validator.py   # NEW 单元测试
│   ├── test_quad_validator.py   # NEW 单元测试
│   ├── test_page_service.py     # NEW 单元测试
│   └── test_mobile_pages.py     # NEW API 集成测试
app/config/
└── default.yaml                 # MODIFIED 新增 upload 段
app/backend/config.py            # MODIFIED 展平 max_upload_file_size_mb 和 min_quad_area_ratio
app/backend/errors.py            # MODIFIED 新增 INVALID_REQUEST_PARAMS
docs/Shared/error-codes.md       # MODIFIED 新增 INVALID_REQUEST_PARAMS
```

## 数据模型

### 页面元数据

路径：`data/pages/{session_id}/{page_id}.json`

```json
{
  "page_id": "uuid4",
  "session_id": "uuid4",
  "page_no": 1,
  "original_image_path": "data/pages/{session_id}/{page_id}.jpg",
  "processed_image_path": null,
  "image_width": 1920,
  "image_height": 1080,
  "quad_points": [[0, 0], [1920, 0], [1920, 1080], [0, 1080]],
  "uploaded_at": "2026-05-12T10:00:00+00:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `page_id` | string | 来自会话页面项 |
| `session_id` | string | 所属采集会话 |
| `page_no` | int | 来自会话页面项，不由文件目录扫描生成 |
| `original_image_path` | string | 上传原始图片保存路径 |
| `processed_image_path` | null | 本阶段固定为 null |
| `image_width` | int | 图片宽度（像素） |
| `image_height` | int | 图片高度（像素） |
| `quad_points` | array 或 null | 四个角点坐标；缺失时保存 null |
| `uploaded_at` | string | ISO 8601 UTC 上传时间 |

### 存储布局

```
data/pages/
└── {session_id}/
    ├── {page_id}.jpg
    └── {page_id}.json
```

会话 JSON 仍位于 `data/sessions/{session_id}.json`，并通过 `upload_ref` 指向页面元数据。

## 配置

`app/config/default.yaml` 新增：

```yaml
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
```

`config.py` 变更：

- `DEFAULT_CONFIG` 新增 `max_upload_file_size_mb: 10`、`min_quad_area_ratio: 0.01`
- `_flatten_config` 新增对 `upload.max_file_size_mb`、`upload.min_quad_area_ratio` 的展平
- `_validate_config` 校验 `max_upload_file_size_mb` 为正整数，`min_quad_area_ratio` 为 `(0, 1)` 区间浮点数

## 共享错误码变更

`docs/Shared/error-codes.md` 新增：

| 错误码 | HTTP 状态码 | 场景 |
|--------|------------|------|
| `INVALID_REQUEST_PARAMS` | 400 | 请求参数缺失、类型错误、格式错误或取值非法 |

同时在 `app/backend/errors.py` 的 `ErrorCode` 枚举中新增此项。

该错误码是共享契约变更，implementation plan 必须先用测试覆盖 `ErrorCode.INVALID_REQUEST_PARAMS`，再实现上传参数校验。

## API 契约

### POST /api/mobile/{session_id}/pages

上传图片页面到指定会话。

**Content-Type**：`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `image` | file | 是 | 图片文件，真实类型限制为 jpg/jpeg/png/bmp |
| `image_width` | int | 是 | 原图宽度（像素），必须为正整数 |
| `image_height` | int | 是 | 原图高度（像素），必须为正整数 |
| `quad_points` | JSON string | 否 | 四个角点坐标，缺失时保存 null |

**Response 201**：

```json
{
  "success": true,
  "data": {
    "page_id": "uuid4",
    "session_id": "uuid4",
    "page_no": 1,
    "original_image_path": "data/pages/{session_id}/{page_id}.jpg",
    "processed_image_path": null,
    "quad_points": [[0, 0], [1920, 0], [1920, 1080], [0, 1080]],
    "image_width": 1920,
    "image_height": 1080,
    "uploaded_at": "2026-05-12T10:00:00+00:00"
  }
}
```

成功响应不包含 `error: null`，保持现有 `responses.success()` 格式。

**错误响应**：

| 条件 | HTTP | error.code |
|------|------|------------|
| 会话不存在 | 404 | `SESSION_NOT_FOUND` |
| 会话已过期 | 409 | `SESSION_EXPIRED` |
| 会话已锁定或已取消 | 409 | `SESSION_LOCKED` |
| 缺少 `image` 字段 | 400 | `INVALID_REQUEST_PARAMS` |
| 缺少 `image_width` 或 `image_height` | 400 | `INVALID_REQUEST_PARAMS` |
| `image_width` 或 `image_height` 非正整数 | 400 | `INVALID_REQUEST_PARAMS` |
| 文件真实类型不在白名单内 | 400 | `UNSUPPORTED_FILE_TYPE` |
| 文件超过大小限制 | 400 | `FILE_TOO_LARGE` |
| `quad_points` JSON 解析失败 | 400 | `INVALID_QUAD_POINTS` |
| `quad_points` 缺角点、非数字、NaN/Inf | 400 | `INVALID_QUAD_POINTS` |
| `quad_points` 坐标越界或为负 | 400 | `INVALID_QUAD_POINTS` |
| `quad_points` 自相交 | 400 | `INVALID_QUAD_POINTS` |
| `quad_points` 面积过小或退化为线/点 | 400 | `INVALID_QUAD_POINTS` |

实现顺序：

1. 调用真实 `SessionService.add_page(session_id, upload_ref=None)`，让会话服务完成 active/expired/locked guard 并分配 `page_id/page_no`。
2. 校验 `image`、`image_width`、`image_height`。
3. 读取 magic bytes，校验真实文件类型和大小。
4. 校验 `quad_points`；缺失时为 null。
5. 以会话分配的 `page_id` 保存原图和元数据。
6. 调用 `SessionService.attach_page_upload(session_id, page_id, upload_ref)` 或等价方法写回 `upload_ref`。

如果文件保存失败，implementation plan 必须明确补偿策略：删除已创建的会话页面项，或将该页面项标记为无 `upload_ref` 并返回错误。本 spec 建议删除该页面项，避免 finish 固化空上传页。

## 文件校验规则

### 真实类型检测

| 扩展名 | magic bytes |
|--------|-------------|
| jpg/jpeg | `\xFF\xD8\xFF` |
| png | `\x89PNG` |
| bmp | `BM` |

- 真实类型不在白名单内 → `UNSUPPORTED_FILE_TYPE`
- 保存文件时使用真实类型对应的规范扩展名，不使用用户原始扩展名

### 文件大小限制

- 配置项 `max_upload_file_size_mb`，默认 10 MB
- 超限 → `FILE_TOO_LARGE`

### 路径安全

- 不信任用户提交的原始文件名
- 文件名取 `{page_id}.{真实类型扩展名}`
- 保存路径 `data/pages/{session_id}/{page_id}.{ext}`
- 路径拼接前校验 `session_id` 和 `page_id` 不含 `..`、`/`、`\`、`~`、null 字节等危险字符

## quad_points 校验规则

输入为 JSON 字符串 `[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]`，点顺序约定为「左上、右上、右下、左下」。

| 规则 | 失败返回 |
|------|----------|
| 可解析为合法 JSON 数组 | `INVALID_QUAD_POINTS` |
| 顶层数组长度等于 4 | `INVALID_QUAD_POINTS` |
| 每个点为包含 2 个数字的数组 | `INVALID_QUAD_POINTS` |
| 坐标非 NaN、非 Inf、非负 | `INVALID_QUAD_POINTS` |
| 坐标在 `[0, image_width] × [0, image_height]` 范围内 | `INVALID_QUAD_POINTS` |
| 四边形不自相交 | `INVALID_QUAD_POINTS` |
| 四边形面积 ≥ 图片面积 × `min_quad_area_ratio` | `INVALID_QUAD_POINTS` |
| `quad_points` 字段缺失 | 不报错，元数据保存 null |

`image_width` / `image_height` 必须先校验为正整数，否则返回 `INVALID_REQUEST_PARAMS`。

## 模块职责

| 文件 | 职责 |
|------|------|
| `app/backend/services/file_validator.py` | 读取 magic bytes 判断真实类型、白名单校验、大小校验、路径安全校验 |
| `app/backend/services/quad_validator.py` | JSON 解析、点数量校验、数字性与范围校验、自相交判断、面积校验 |
| `app/backend/services/page_service.py` | 调用 SessionService 创建页面项、协调校验、保存图片、写元数据、回写 `upload_ref` |
| `app/backend/routes/mobile.py` | 解析 multipart，调用 page_service，返回统一响应 |

## 状态流转

```
POST /api/mobile/{session_id}/pages
  → SessionService.add_page(session_id, upload_ref=None)
      ├─ missing → SESSION_NOT_FOUND
      ├─ expired → SESSION_EXPIRED
      ├─ locked/cancelled → SESSION_LOCKED
      └─ active → 返回 page_id/page_no
  → 校验 multipart 参数
  → 校验文件真实类型和大小
  → 校验 quad_points
  → 保存 data/pages/{session_id}/{page_id}.{ext}
  → 保存 data/pages/{session_id}/{page_id}.json
  → SessionService.attach_page_upload(session_id, page_id, "pages/{session_id}/{page_id}.json")
  → 返回 201
```

## 测试策略

遵循 TDD：先写失败测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 层次 | 对应 TDD ID |
|----------|------|-------------|
| `test_file_validator.py` | 单元 | BE-FILE-001, 002, 003, 004 |
| `test_quad_validator.py` | 单元 | BE-FILE-009 |
| `test_page_service.py` | 单元 | BE-FILE-005, 006, 008, 010 |
| `test_mobile_pages.py` | API 集成 | BE-FILE-007, 008, 010 |

### `test_file_validator.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_accepts_jpg_by_magic_bytes` | BE-FILE-001 | 真实 jpg 文件被拒绝 |
| `test_accepts_png_by_magic_bytes` | BE-FILE-001 | 真实 png 文件被拒绝 |
| `test_accepts_bmp_by_magic_bytes` | BE-FILE-001 | 真实 bmp 文件被拒绝 |
| `test_rejects_pdf_by_magic_bytes` | BE-FILE-001 | pdf 文件被接受 |
| `test_rejects_text_file_renamed_to_jpg` | BE-FILE-002 | 伪造扩展名被接受 |
| `test_rejects_file_exceeding_size_limit` | BE-FILE-003 | 超大文件被接受 |
| `test_file_size_at_boundary_accepted` | BE-FILE-003 | 边界值被错误拒绝 |
| `test_rejects_path_traversal_in_session_id` | BE-FILE-004 | `../` 路径未被拒绝 |
| `test_rejects_null_byte_in_id` | BE-FILE-004 | null 字节未被拒绝 |
| `test_generates_extension_from_magic_bytes` | BE-FILE-001 | 扩展名不是由真实类型决定 |

### `test_quad_validator.py`

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_accepts_valid_quad_points` | BE-FILE-009 | 合法四点被拒绝 |
| `test_rejects_non_json_string` | BE-FILE-009 | 非法 JSON 被接受 |
| `test_rejects_three_points` | BE-FILE-009 | 3 点被接受 |
| `test_rejects_non_numeric_coordinates` | BE-FILE-009 | 字符串坐标被接受 |
| `test_rejects_nan_or_inf_coordinates` | BE-FILE-009 | NaN/Inf 被接受 |
| `test_rejects_negative_coordinates` | BE-FILE-009 | 负坐标被接受 |
| `test_rejects_out_of_bounds_coordinates` | BE-FILE-009 | 越界坐标被接受 |
| `test_rejects_self_intersecting_quad` | BE-FILE-009 | 自相交四边形被接受 |
| `test_rejects_zero_area_quad` | BE-FILE-009 | 四点重合被接受 |
| `test_rejects_area_below_min_ratio` | BE-FILE-009 | 极小面积被接受 |
| `test_none_returns_none` | BE-FILE-008 | None 输入抛异常 |

### `test_page_service.py`

使用临时目录和 fake `SessionService`。fake 必须记录 `add_page` / `attach_page_upload` 调用，确保页序来自会话服务。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_save_page_creates_image_file` | BE-FILE-005 | 文件未落盘 |
| `test_save_page_creates_metadata_json` | BE-FILE-007 | 元数据文件未创建 |
| `test_save_page_returns_page_dict` | BE-FILE-007 | 返回结构与约定不一致 |
| `test_page_id_and_page_no_come_from_session_service` | BE-FILE-006 | 文件模块自行生成页序 |
| `test_upload_ref_written_back_to_session_page` | BE-FILE-006 | 会话页面项未关联元数据 |
| `test_quad_points_null_when_missing` | BE-FILE-008 | 缺 quad 时上传被阻断 |
| `test_session_isolation_different_directories` | BE-FILE-005 | 不同 session 文件混淆 |
| `test_upload_does_not_call_algorithm_module` | BE-FILE-010 | 上传阶段触发算法调用 |
| `test_save_failure_removes_created_session_page` | 衔接一致性 | 文件失败后会话留下空页 |

### `test_mobile_pages.py`

使用 Flask test client + 真实 `SessionService` + 临时配置目录。

| 测试 | TDD ID | RED 失败点 |
|------|--------|------------|
| `test_upload_page_returns_201` | BE-FILE-007 | 端点缺失或状态码不对 |
| `test_upload_page_response_has_page_id_from_session` | BE-FILE-007 | 响应缺 page_id 或不是会话分配 |
| `test_upload_without_quad_points_returns_201` | BE-FILE-008 | 缺 quad_points 时上传被拒绝 |
| `test_upload_rejects_non_image_file` | BE-FILE-001 | pdf 上传未返回 UNSUPPORTED_FILE_TYPE |
| `test_upload_rejects_oversized_file` | BE-FILE-003 | 超大文件未返回 FILE_TOO_LARGE |
| `test_upload_rejects_invalid_quad_points` | BE-FILE-009 | 非法 quad 未返回 INVALID_QUAD_POINTS |
| `test_upload_missing_image_returns_400` | BE-FILE-007 | 缺文件时未返回 INVALID_REQUEST_PARAMS |
| `test_upload_missing_dimensions_returns_400` | BE-FILE-007 | 缺宽高时未返回 INVALID_REQUEST_PARAMS |
| `test_upload_expired_session_returns_409` | 会话状态 | expired 会话未拒绝 |
| `test_upload_nonexistent_session_returns_404` | 会话状态 | missing 会话未拒绝 |
| `test_upload_locked_session_returns_409` | 会话状态 | locked 会话未拒绝 |
| `test_session_page_upload_ref_points_to_metadata` | 衔接一致性 | 会话 pages 未写回 upload_ref |

## 与后续阶段的衔接

- 页面管理阶段继续以会话 `pages` 清单为准；删除、排序、补拍不得扫描 `data/pages/` 推导顺序。
- finish 固化读取会话 `pages` 的 `page_id` 顺序，Task 桩的 `page_order` 再供任务生命周期使用。
- 任务生命周期阶段通过 `upload_ref` 读取页面元数据，拿到 `original_image_path` 和 `quad_points`。
- 外部算法模块成功生成处理后图片路径时，再把 `processed_image_path` 写入页面元数据。

## 自审结论

- 与 PR-BE-002 的页面清单方案衔接：会话 `pages` 是唯一页序来源，上传只写 `upload_ref`。
- 无 OCR、LLM、图像预处理、裁剪、透视矫正或规则抽取实现要求。
- 上传阶段只保存客户端上传的原始图像和元数据，后端不生成 processed image。
- 成功响应格式沿用现有 `responses.success()`，不包含 `error: null`。
- `INVALID_REQUEST_PARAMS` 是显式共享错误码变更，implementation plan 必须先测试后实现。
- 文件扩展名由 magic bytes 真实类型决定，不使用用户原始文件名和扩展名。
