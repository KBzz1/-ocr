# MVP 轻量化收敛设计

## 范围

本 spec 定义从当前较重的“采集会话工作站”设计收敛为“个人 OCR 结构化 MVP 工具”的实现边界和迁移顺序。目标是先砍掉复杂业务面，保留医生个人使用时最有价值的链路：

```text
电脑端新建任务
  -> 手机扫码拍照/选择多图上传
  -> 完成上传后本地 OCR/结构化处理
  -> 电脑端审核字段
  -> 标记完成并导出 JSON/Excel
```

本 spec 只定义后续实现设计，不在本文中实现代码。

## 权威依据

- `docs/产品PRD.md`：当前 MVP 产品目标。
- `docs/PRD任务清单.md`：MVP 任务索引和后置能力。
- `docs/Shared/state-enums.md`：MVP 任务状态和字段状态。
- `docs/Shared/error-codes.md`：MVP 错误码。
- `docs/Shared/terminology.md`：MVP 术语。
- `app/frontend/README.md`
- `app/frontend/mobile-capture.README.md`
- `app/frontend/workstation.README.md`

本 spec 取代旧设计中涉及采集会话、四边形框选、会话过期、修订采集、拖拽排序的正向实现要求。旧 spec 可作为历史资料保留，但后续开发以本 spec 和 MVP PRD 为准。

## MVP 保留能力

- 电脑端创建任务。
- 创建任务后生成手机上传 URL/二维码。
- 手机端拍照或选择图片。
- 多张图片上传到同一个任务。
- 图片页序按上传成功顺序确定。
- 完成上传后任务进入处理。
- 后端调用本地 OCR/结构化模块。
- 电脑端查看原图、OCR 文本和结构化字段。
- 人工修改字段并保存最终值。
- 任务标记 `done`。
- `review` 和 `done` 任务可导出 JSON/Excel。

## MVP 删除或后置能力

以下能力不再作为当前实现目标，后续代码收敛时应从公开 API、前端入口、状态枚举和测试主流程中移除：

- `CaptureSession` 独立业务实体。
- `/api/capture-sessions*` API。
- `/api/mobile/<session_id>/*` 旧会话上传 API。
- 会话状态：`active / locked / expired / cancelled`。
- 会话过期、取消、锁定、解锁、修订采集。
- 四边形框选、重新框选、`quad_points`、`INVALID_QUAD_POINTS`。
- 手机端拖拽排序、补拍替换某页。
- 任务状态：`capturing / uploaded / ready_for_review / confirmed / exported`。
- 字段状态：`suspicious / empty / confirmed_empty`。
- 导出后把任务推进到 `exported`。
- 基于会话或 quad 的算法输入构建。

若后续确实需要补图、排序、框选，应作为新版本能力重新写 spec，不应在 MVP 收敛中顺手保留。

## 目标状态机

任务状态：

| 状态 | 含义 | 合法下一状态 |
|------|------|--------------|
| `uploading` | 已创建任务，手机端可继续上传图片 | `processing`, `failed` |
| `processing` | 正在调用本地 OCR/结构化模块 | `review`, `failed` |
| `review` | 处理成功，等待电脑端人工审核 | `processing`, `done`, `failed` |
| `done` | 人工审核完成，可查看和导出 | `processing` |
| `failed` | 上传完成、处理或导出前置步骤失败 | `processing` |

字段状态：

| 状态 | 含义 |
|------|------|
| `unreviewed` | 来自自动抽取结果，尚未人工确认 |
| `confirmed` | 人工已确认 |
| `modified` | 人工已修改最终值 |

导出不再改变任务状态。导出成功只写 `export_summary` 或 `ExportRecord`。

## 后端设计

### 服务结构

后端以 `Task` 为唯一业务根。手机上传直接绑定 `task_id`，不再通过 session 间接找到任务。

建议保留和收敛的服务：

- `TaskService`：创建任务、状态流转、触发处理、重试、标记完成、导出摘要。
- `PageService`：保存任务图片、按上传成功顺序分配 `page_no`、读取任务图片列表。
- `ProcessingOrchestrator`：从任务图片列表构建算法输入，调用本地 OCR/结构化模块。
- `ReviewService`：读取自动候选和人工结果，保存最终字段值。
- `ExportService`：从人工最终值导出 JSON/Excel。

建议删除或停止注册：

- `SessionService`
- `capture_session_bp`
- 旧 `mobile.py` 中基于 `session_id` 的接口
- `quad_validator.py`

如果为了小步迁移暂时保留文件，必须确保它们不再被 app 注册、不再被新 API 调用、不再出现在 MVP 主流程测试中。

### API

目标 API：

```text
POST /api/tasks
GET  /api/tasks
GET  /api/tasks/{task_id}
POST /api/mobile-upload/{task_id}/images
POST /api/mobile-upload/{task_id}/finish
POST /api/tasks/{task_id}/process
GET  /api/tasks/{task_id}/review
PUT  /api/tasks/{task_id}/review
POST /api/tasks/{task_id}/complete
GET  /api/tasks/{task_id}/export/json
GET  /api/tasks/{task_id}/export/excel
```

`POST /api/tasks` 返回：

```json
{
  "task_id": "task_001",
  "status": "uploading",
  "upload_token": "opaque-token",
  "mobile_upload_url": "http://192.168.1.5:8081/mobile/upload/task_001?token=opaque-token"
}
```

`POST /api/mobile-upload/{task_id}/images`：

- 仅允许 `uploading` 任务上传。
- 校验 `token`。
- 接收 `image`、可选 `image_width`、可选 `image_height`。
- 不接收 `quad_points`。
- 上传成功后按当前任务已有图片数 + 1 写入 `page_no`。

`POST /api/mobile-upload/{task_id}/finish`：

- 如果任务无图片，返回 `TASK_EMPTY`。
- 如果任务有图片，进入 `processing` 并触发本地算法处理。
- 重复调用不得重复创建任务或重复写入图片。

### 数据结构

Task 最小结构：

```json
{
  "task_id": "task_001",
  "status": "uploading",
  "created_at": "2026-05-19T10:00:00+08:00",
  "updated_at": "2026-05-19T10:00:00+08:00",
  "upload_token": "opaque-token",
  "images": [],
  "error_code": null,
  "error_message": null,
  "review_summary": null,
  "export_summary": {
    "last_exported_at": null,
    "formats": [],
    "files": []
  }
}
```

PageImage 最小结构：

```json
{
  "page_id": "page_001",
  "task_id": "task_001",
  "page_no": 1,
  "original_image_path": "/abs/path/data/tasks/task_001/pages/page_001.jpg",
  "preview_url": "/api/tasks/task_001/images/page_001",
  "image_width": 1920,
  "image_height": 1080,
  "uploaded_at": "2026-05-19T10:05:00+08:00"
}
```

MVP 不保存 `session_id`、`upload_ref`、`processed_image_path`、`quad_points`、`quad_updated_at`。

### 算法输入

`ProcessingOrchestrator` 从 Task 的 `images` 构建输入：

```json
[
  {
    "task_id": "task_001",
    "page_id": "page_001",
    "page_no": 1,
    "original_path": "/abs/path/page_001.jpg",
    "image_width": 1920,
    "image_height": 1080
  }
]
```

MVP 不要求图像预处理输出 `processed_image_path`。如果外部算法模块仍需要预处理，可由算法模块内部处理；本仓库不实现裁剪、透视矫正或图像增强。

## 前端设计

### 路由

目标路由：

```text
/                         工作台总览
/mobile/upload/:taskId    手机上传页
/tasks                    任务管理
/tasks/:taskId/review     审核界面
```

旧路由 `/mobile/sessions/:sessionId` 不再作为 MVP 入口。

### API 层

建议新增或收敛为：

- `src/api/tasks.ts`：创建任务、列表、详情、处理、完成。
- `src/api/mobileUpload.ts`：手机上传状态、上传图片、完成上传。
- `src/api/review.ts`：审核读取和保存。
- `src/api/export.ts`：导出 JSON/Excel。

建议删除或停止使用：

- `src/api/captureSessions.ts`
- `tests/fixtures/sessions.ts`
- `tests/fixtures/uploads.ts` 中基于 session 的 mock。

### 组件和页面

工作台总览：

- 点击"新建任务"调用 `POST /api/tasks`。
- 弹窗展示 `mobile_upload_url` 的二维码、任务编号、已上传图片数。
- 不显示剩余时间、会话状态、取消采集、修订采集。

手机上传页：

- 加载任务上传状态。
- 单个"拍照/选择图片"入口。
- 上传列表展示页序、缩略图或文件名、上传状态。
- 至少一张图片后允许"完成上传"。
- 不出现四边形框选页、拖拽排序、重新框选、补拍替换。

任务管理：

- 状态筛选只包含：全部、上传中、处理中、待审核、已完成、失败。
- 操作只包含：查看二维码、查看进度、进入审核、重新处理、导出、查看原因。
- 不显示修订采集、取消会话、已导出状态筛选。

审核界面：

- 原图列表和预览。
- OCR 文本。
- 结构化字段表单。
- 字段编辑保存。
- 字段状态：未审核、已确认、已修改。
- 标记任务完成。
- 导出 JSON/Excel。

## 删除顺序

为了降低一次性大改风险，建议按以下顺序收敛：

1. **共享契约先行**
   - 更新后端 `TaskStatus`、`FieldStatus`、错误码。
   - 增加 MVP 状态和 API 测试。
   - 让旧状态在新测试中失败，确认 RED。

2. **后端任务根替代会话根**
   - `POST /api/tasks` 创建 `uploading` 任务。
   - 新增 `/api/mobile-upload/{task_id}/images` 和 `/finish`。
   - `PageService` 改为 task-bound 图片保存。
   - Orchestrator 改为读取 `task.images`。

3. **停止暴露旧会话 API**
   - 不注册 `capture_session_bp`。
   - 移除或废弃 `/api/mobile/<session_id>/*`。
   - 删除 session/quad 主流程测试，改为 MVP 测试。

4. **前端共享契约收敛**
   - 路由从 `/mobile/sessions/:sessionId` 改为 `/mobile/upload/:taskId`。
   - 状态文案改为五状态。
   - API mock 改为 task/mobile-upload。

5. **前端页面删减**
   - 工作台新建任务弹窗改为任务二维码。
   - 手机端删除 `QuadSelector` 和框选流程。
   - 手机端删除拖拽排序、补拍替换、重新框选。
   - 任务管理删除旧操作。

6. **E2E 收口**
   - 新成功链路：新建任务 -> 手机上传 3 张图 -> 完成上传 -> review -> done -> 导出。
   - 新失败链路：算法未配置或契约非法 -> failed -> 展示原因。

## 测试策略

### 后端测试

必须新增或改写：

- `test_enums.py`
  - 只包含 `uploading / processing / review / done / failed`。
  - `failed -> uploading` 非法。
  - 旧状态值构造应失败。

- `test_task_routes.py`
  - `POST /api/tasks` 创建 `uploading` 任务并返回手机上传 URL。
  - `GET /api/tasks` 返回五状态任务。

- `test_mobile_upload_routes.py`
  - 上传图片成功写入任务图片列表。
  - 页序按上传成功顺序递增。
  - 非 `uploading` 状态上传返回 `TASK_UPLOAD_CLOSED`。
  - 无图片完成上传返回 `TASK_EMPTY`。
  - 完成上传后进入 `processing` 或在算法未配置时进入 `failed`。

- `test_orchestrator.py`
  - 图片输入来自 `task.images`。
  - 输入中不包含 `quad_points`。

- `test_api_contracts.py` / `test_backend_e2e.py`
  - 移除 `/api/capture-sessions*` 主流程断言。
  - 覆盖 MVP 成功和失败路径。

可以删除或重写：

- `test_capture_session.py`
- `test_session_service.py`
- `test_quad_validator.py`
- 基于 `/api/mobile/<session_id>/pages/<page_id>/quad` 的测试。

### 前端测试

必须新增或改写：

- 路由测试：
  - `/mobile/upload/:taskId` 是手机上传入口。
  - 不再依赖 `/mobile/sessions/:sessionId`。

- 工作台测试：
  - 新建任务调用 `POST /api/tasks`。
  - 弹窗展示任务上传二维码。

- 手机上传页测试：
  - 拍照/选择图片后直接上传。
  - 不渲染四边形框选。
  - 不渲染拖拽排序。
  - 至少一张图片后才能完成上传。

- 任务列表测试：
  - 五状态筛选。
  - 不显示修订采集/取消会话。

- 审核和导出测试：
  - `review` 和 `done` 可导出。
  - 导出不要求任务进入 `exported`。

可以删除或重写：

- `QuadSelector.test.tsx`
- `captureSessions.test.ts`
- 基于 session fixtures 的 E2E。

## 验收门

后端：

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

前端：

```bash
npm run test
npm run typecheck
npm run build
npm run test:e2e
```

静态扫描：

```bash
rg -n "capture-sessions|CaptureSession|SESSION_|INVALID_QUAD_POINTS|quad_points|capturing|uploaded|ready_for_review|exported|/mobile/sessions" app docs
```

允许命中范围：

- 历史 spec 或后置能力说明。
- 迁移说明中明确标注“不再使用”的内容。

不允许命中范围：

- 正向 PRD。
- `docs/Shared/` 当前契约。
- 前后端生产代码。
- 当前 MVP 测试主流程。

## 风险和取舍

- **图片输入错误无法原任务修订**：MVP 用新建任务解决，换取更少状态和更少手机端复杂交互。
- **没有手动框选可能影响 OCR 质量**：先依赖本地 OCR/结构化模块处理原图，后续若质量不足，再独立设计框选或裁剪能力。
- **旧代码改动面较大**：采用先新增 task-bound API、再停止注册旧 API、最后删除孤立文件的顺序，降低一次性破坏风险。
- **旧测试会大量失效**：这是预期结果，旧测试体现的是旧业务。收敛时应以 MVP PRD 和本 spec 改写测试，而不是为了通过旧测试保留旧行为。

## 不做事项

- 不把旧会话 API 包一层继续对外兼容。
- 不在前端隐藏旧功能但后端继续暴露旧主流程。
- 不保留 `exported` 任务状态。
- 不把 `quad_points` 作为可选字段继续穿透到算法输入。
- 不引入云 API、CDN、遥测或运行时联网下载。
- 不实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则兜底抽取。
