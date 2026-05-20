# MVP PRD 任务清单

> 本清单跟踪 `docs/产品PRD.md` 的当前 MVP 设计。历史上已实现但不属于 MVP 的采集会话、四边形框选、会话过期、修订采集、拖拽排序等能力不再作为后续设计目标；代码可后续按新设计逐步收敛。

## 状态说明

| 状态 | 含义 |
|------|------|
| `已完成` | 已有实现并通过对应测试 |
| `需收敛` | 现有实现或文档来自旧设计，需要按 MVP 重构或删减 |
| `待开始` | MVP 已定义，尚未进入实现 |
| `阻塞` | 依赖外部算法模块、前置契约或上游任务 |
| `延后` | 方向可能调整，暂不作为近期主线推进 |

任务项中 `[x]` 表示已完成，`[~]` 表示需收敛或进行中，`[ ]` 表示待开始。

## MVP 当前目标

| 任务 | 状态 | 工作区/文件 | 边界 |
|------|------|-------------|------|
| BE-00 后端最小骨架 | 已完成 | `app/backend/` | 保留 Flask app、配置、统一响应、JsonStore、系统状态 |
| BE-MVP-01 任务创建和二维码上传入口 | 已完成 | `app/backend/routes/task.py`、`app/backend/routes/mobile.py` | 创建 `uploading` 任务并生成手机上传 URL；不再创建采集会话 |
| BE-MVP-02 图片上传和页序 | 已完成 | `app/backend/services/page_service.py` | 上传原图，页序按上传成功顺序确定；不做 quad、补拍替换、拖拽排序 |
| BE-MVP-03 简化任务生命周期 | 已完成 | `app/backend/services/task_service.py` | 状态统一为 `uploading / processing / review / done / failed` |
| BE-MVP-04 OCR/结构化模块调用 | 已完成/需对齐 | `app/backend/services/algorithm_ports/` | 调用本地算法模块，失败进入 `failed`；不实现算法 |
| BE-MVP-05 审核结果保存 | 已完成 | `app/backend/services/review_service.py` | 字段状态先保留 `unreviewed / confirmed / modified` |
| BE-MVP-06 导出服务 | 已完成 | `app/backend/services/export_service.py` | `review` 和 `done` 可导出 JSON/Excel，导出来自人工最终值 |
| FE-MVP-01 工作台总览 | 已完成 | `app/frontend/src/pages/workstation/` | 新建任务、二维码、最近任务、状态统计 |
| FE-MVP-02 手机上传页 | 已完成 | `app/frontend/src/pages/mobile-capture/` | 只做拍照/选择图片、多图上传、完成上传 |
| FE-MVP-03 任务管理 | 已完成 | `app/frontend/src/pages/tasks/` | 任务列表、筛选、状态操作 |
| FE-MVP-04 审核界面 | 已完成 | `app/frontend/src/pages/review/` | 原图、OCR 文本、结构化字段编辑、保存、完成、导出 |
| REL-MVP-01 本地运行包 | 延后 | `run.bat`、`stop.bat`、配置目录 / 后续 Docker 方案 | 近期不投入 Windows 运行包细节；优先完成 E2E 主流程闭环，运行形态后续按 Docker 或本地脚本重新设计 |

## 后端任务

### BE-00 基础契约与运行骨架

- [x] **BE-00-01 后端最小服务骨架**
  - 范围：Flask app factory、配置加载、统一响应、系统状态。
  - 边界：只提供可运行基础。

- [x] **BE-00-02 共享状态和错误码收敛**
  - 范围：任务状态改为 `uploading / processing / review / done / failed`；错误码移除 `SESSION_*` 和 `INVALID_QUAD_POINTS`。
  - 边界：代码和测试需要后续同步新枚举。

### BE-MVP-01 任务创建和手机上传入口

- [x] **BE-MVP-01-01 创建上传任务**
  - 范围：`POST /api/tasks` 创建 `uploading` 任务，返回 `task_id`、上传 URL 和二维码内容。
  - 边界：不创建 `CaptureSession`。

- [x] **BE-MVP-01-02 上传令牌校验**
  - 范围：手机上传接口校验 `task_id` 和 `upload_token`。
  - 边界：MVP 只做轻量校验，不做会话过期。

- [ ] **BE-MVP-01-03 上传状态查询**
  - 范围：手机端可查询当前任务上传状态、已上传数量和图片列表。
  - 边界：非 `uploading` 任务只读展示，不允许继续上传。

### BE-MVP-02 图片上传和文件管理

- [x] **BE-MVP-02-01 文件类型和大小校验**
  - 范围：jpg/jpeg/png/bmp magic bytes、大小限制、拒绝伪装文件。
  - 边界：不信任文件名和 Content-Type。

- [x] **BE-MVP-02-02 简化上传 API**
  - 范围：`POST /api/mobile-upload/{task_id}/images` 接收原图并保存到任务目录。
  - 边界：不接收或保存 `quad_points`。

- [x] **BE-MVP-02-03 页序按上传顺序确定**
  - 范围：每张图片按上传成功顺序写入 `page_no`。
  - 边界：MVP 不支持拖拽排序、补拍替换、重新框选。

- [x] **BE-MVP-02-04 完成上传**
  - 范围：`POST /api/mobile-upload/{task_id}/finish`，有图片则进入 `processing`，无图片返回 `TASK_EMPTY`。
  - 边界：重复完成上传不得重复触发多个处理任务。

### BE-MVP-03 任务生命周期

- [x] **BE-MVP-03-01 状态流转校验**
  - 范围：只允许 MVP 五状态合法转换。
  - 边界：非法转换返回 `INVALID_TASK_TRANSITION`。

- [x] **BE-MVP-03-02 触发处理与重试**
  - 范围：完成上传、失败重试、待审核或已完成任务重新处理。
  - 边界：重新处理使用现有图片输入，不提供修订采集。

- [x] **BE-MVP-03-03 失败任务信息保存**
  - 范围：保存 error_code、error_message、failed_at 和状态历史。
  - 边界：失败任务不得被前端伪装成可审核结果。

### BE-MVP-04 OCR 和结构化模块

- [x] **BE-MVP-04-01 本地算法端口**
  - 范围：定义本地 OCR/结构化模块调用边界。
  - 边界：本仓库不实现 OCR、LLM 字段抽取、图像预处理或规则抽取。

- [x] **BE-MVP-04-02 输入改为任务图片列表**
  - 范围：输入使用上传顺序的原图列表。
  - 边界：MVP 不依赖 processed 图像或 quad 元数据。

- [x] **BE-MVP-04-03 算法失败映射**
  - 范围：未配置、异常、空字段、契约非法均进入 `failed`。
  - 边界：不得规则兜底或补造字段。

### BE-MVP-05 审核和导出

- [x] **BE-MVP-05-01 审核结果读取和保存**
  - 范围：读取自动候选、保存人工最终值。
  - 边界：不覆盖自动抽取原值。

- [x] **BE-MVP-05-02 字段状态收敛**
  - 范围：MVP 字段状态只保留 `unreviewed / confirmed / modified`。
  - 边界：`suspicious / empty / confirmed_empty` 后置。

- [x] **BE-MVP-05-03 标记任务完成**
  - 范围：审核完成后任务进入 `done`。
  - 边界：导出不引入独立 `exported` 状态。

- [x] **BE-MVP-05-04 JSON/Excel 导出**
  - 范围：`review` 和 `done` 任务可导出人工最终值。
  - 边界：导出失败不破坏审核数据。

## 前端任务

### FE-MVP-01 工作台总览

- [x] **FE-MVP-01-01 新建任务和二维码弹窗**
  - 范围：调用 `POST /api/tasks`，展示任务上传二维码和已上传图片数量。
  - 边界：不展示会话状态、剩余时间、取消采集、修订采集。

- [x] **FE-MVP-01-02 最近任务和统计**
  - 范围：展示 `uploading / processing / review / done / failed` 统计和最近任务。
  - 边界：状态文案来自 `docs/Shared/state-enums.md`。

### FE-MVP-02 手机上传页

- [x] **FE-MVP-02-01 手机上传任务加载**
  - 范围：扫码后加载任务上传状态。
  - 边界：不加载采集会话，不处理 expired/locked/cancelled。

- [x] **FE-MVP-02-02 拍照和选择图片**
  - 范围：单个"拍照/选择图片"入口支持拍摄或选择本地图片。
  - 边界：不进入四边形框选页。

- [x] **FE-MVP-02-03 已上传图片列表**
  - 范围：展示上传顺序、上传状态、缩略图或文件名。
  - 边界：不支持拖拽排序、补拍替换、重新框选。

- [x] **FE-MVP-02-04 完成上传**
  - 范围：至少 1 张图片后可点击完成上传，提示回到电脑端。
  - 边界：不重复触发处理。

### FE-MVP-03 任务管理

- [x] **FE-MVP-03-01 任务列表展示**
  - 范围：任务编号、创建时间、图片数量、状态、错误原因。
  - 边界：不展示会话字段。

- [x] **FE-MVP-03-02 状态筛选**
  - 范围：全部、上传中、处理中、待审核、已完成、失败。
  - 边界：不使用旧状态筛选。

- [x] **FE-MVP-03-03 操作入口**
  - 范围：查看二维码、查看进度、进入审核、重新处理、导出、查看原因。
  - 边界：不提供修订采集或取消会话。

### FE-MVP-04 审核界面

- [x] **FE-MVP-04-01 审核页面布局**
  - 范围：原图、OCR 文本、结构化字段并列查看。
  - 边界：只展示后端结果，不推断字段。

- [x] **FE-MVP-04-02 字段编辑保存**
  - 范围：编辑字段、保存人工最终值、刷新后不丢失。
  - 边界：不覆盖自动候选。

- [x] **FE-MVP-04-03 字段确认和任务完成**
  - 范围：字段状态 `unreviewed / confirmed / modified`，任务可标记 `done`。
  - 边界：复杂空值确认、存疑状态后置。

- [x] **FE-MVP-04-04 导出入口**
  - 范围：审核页触发 JSON/Excel 导出。
  - 边界：不在前端拼 Excel。

## E2E 和发布任务

近期推进顺序：先完成 MVP 成功/失败主流程 E2E 验收，再决定运行形态。Windows 本地运行包优先级降低；如果后续采用 Docker，应先补充 Docker 运行形态设计，再更新发布任务。

- [x] **E2E-MVP-01 成功主流程**
  - 范围：工作台新建任务 → 手机上传 3 张图片 → 完成上传 → processing → review → 审核保存 → done → JSON/Excel 导出。
  - 边界：算法结果使用本地 fixture。
  - 设计：`docs/superpowers/specs/2026-05-20-mvp-e2e-acceptance-design.md`。
  - 计划：`docs/superpowers/plans/2026-05-20-mvp-e2e-acceptance-plan.md`。

- [x] **E2E-MVP-02 失败主流程**
  - 范围：算法未配置/失败/空字段/契约非法均进入 `failed`，任务管理页展示原因。
  - 边界：不出现人工补字段降级路径。
  - 设计：`docs/superpowers/specs/2026-05-20-mvp-e2e-acceptance-design.md`。
  - 计划：`docs/superpowers/plans/2026-05-20-mvp-e2e-acceptance-plan.md`。

- [ ] **REL-MVP-01 Windows 本地运行包**
  - 状态：延后。
  - 范围：后端、前端、配置、运行时目录、启动脚本整合。
  - 边界：暂不作为近期主线；后续可能由 Docker 运行方案替代或简化，不要求现在收敛 Windows 打包细节。

- [ ] **REL-MVP-02 离线验收**
  - 状态：延后到运行形态明确之后。
  - 范围：断网启动、前端加载、无外部请求、手机同网可上传。
  - 边界：验收标准保持离线运行、不联网下载任何内容；具体执行方式跟随后续 Docker 或本地脚本方案。

## 后置能力

以下能力不属于当前 MVP，除非重新调整范围，否则不进入近期实现计划：

- 采集会话 `active / locked / expired / cancelled`。
- 会话过期、取消、修订采集、解锁。
- 四边形框选、重新框选、裁剪、透视矫正。
- 手机端拖拽排序、补拍替换某页。
- 复杂字段状态：`suspicious / empty / confirmed_empty`。
- 导出前复杂完整性预警面板。
- 多医生协同、云同步、医院系统接口。

## 全局边界

- 不接入 HIS/EMR，不写回病历系统。
- 不调用云 API，不使用 CDN、遥测或运行时联网下载。
- 不在本仓库实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正、自动边界识别或规则抽取。
- 算法模块缺失、异常、空结构化字段或契约非法时，任务必须进入 `failed`。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 真实运行数据不得提交到 `data/`、`exports/`、`logs/`。
