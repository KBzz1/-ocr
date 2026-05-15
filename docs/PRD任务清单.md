# PRD 任务清单

> 本清单用于跟踪 `docs/产品PRD.md` 的整体实现进度。它不是细粒度实施计划；具体实现仍按对应 BDD/TDD、spec 和 plan 执行。

## 状态说明

| 状态 | 含义 |
|------|------|
| `已完成` | 已有实现并通过对应测试 |
| `进行中` | 已有分支/spec/plan 正在推进 |
| `待开始` | PRD 已定义，尚未进入实现 |
| `阻塞` | 依赖外部算法模块、前置契约或上游任务 |

任务项中 `[x]` 表示已完成，`[~]` 表示进行中，`[ ]` 表示待开始。

## 当前并行工作

| 任务 | 状态 | 工作区/文件 | 边界 |
|------|------|-------------|------|
| 后端最小骨架 | 已完成 | `app/backend/`、`docs/superpowers/plans/2026-05-11-backend-minimal-skeleton.md` | 配置、状态枚举、统一错误、健康检查、JsonStore；不含业务流程 |
| PR-BE-002 采集会话管理 | 已完成 | `app/backend/services/session_service.py`、`docs/superpowers/plans/2026-05-11-capture-session-implementation.md` | 创建会话、页面清单、过期/锁定 guard、finish 幂等、页序固化、Task 桩；不做真实图片文件校验 |
| PR-BE-003/011 图片上传与元数据 | 已完成 | `app/backend/services/file_validator.py`、`app/backend/services/quad_validator.py`、`app/backend/services/page_service.py`、`app/backend/routes/mobile.py`、`docs/superpowers/specs/2026-05-12-file-upload-design.md`、`docs/superpowers/2026-05-14-mobile-capture-ux-redesign.md` | 已接入上传保存原图和 quad 元数据、重新框选坐标更新和补拍替换图片；不独立维护页序，不做裁剪、透视矫正或图像处理 |
| PR-BE-004 任务生命周期 | 已完成 | `app/backend/services/task_service.py`、`app/backend/routes/task.py`、`docs/superpowers/specs/2026-05-12-task-lifecycle-design.md` | 任务列表/详情、状态流转、处理/重试入口、算法未配置失败落库；不实现算法适配器或字段生成 |
| PR-BE-005/006 外部算法端口 | 已完成 | `app/backend/services/algorithm_ports/`、`docs/superpowers/specs/2026-05-12-algorithm-ports-design.md` | 定义本地算法端口、编排、fixture、失败映射和结果持久化；不实现 OCR/LLM/图像算法 |
| PR-BE-007 Schema 管理 | 已完成 | `app/config/schemas/medical_record.v1.yaml`、`app/backend/services/schema_service.py`、`docs/superpowers/specs/2026-05-12-schema-loader-design.md` | 加载当前 schema、记录版本、校验候选字段 key；schema 不生成字段值 |
| BE-07 人工审核结果 | 已完成 | `app/backend/services/review_service.py`、`app/backend/routes/review.py`、`docs/superpowers/specs/2026-05-12-review-results-design.md` | 读取自动候选并保存人工审核结果；确认前校验未审核/存疑/不可接受空值；不导出 |
| BE-08 导出服务 | 已完成 | `app/backend/services/export_service.py`、`app/backend/routes/export.py`、`docs/superpowers/specs/2026-05-13-export-service-design.md` | 基于人工 `final_value` 导出 JSON/Excel；导出前阻断未完成审核字段；不实现前端入口 |
| BE-09 日志、隐私和部署 | 已完成 | `app/backend/services/local_event_log.py`、`app/backend/services/offline_check_service.py`、`app/backend/services/cleanup_service.py`、`docs/superpowers/specs/2026-05-12-local-logs-privacy-design.md` | 本地事件、隐私脱敏、离线检查和任务级清理；不实现真实算法 |
| BE-10 API 契约和后端 E2E | 已完成 | `app/backend/tests/test_backend_e2e.py`、`app/backend/tests/test_api_contracts.py`、`docs/superpowers/specs/2026-05-13-backend-e2e-contracts-design.md` | 使用本地 fixtures 覆盖成功/失败主流程和 API 契约；不访问外网 |
| BE-01 Windows 启停与离线启动 | 已完成 | `run.bat`、`stop.bat`、`scripts/offline_startup_check.py`、`docs/superpowers/specs/2026-05-12-windows-offline-startup-design.md` | 聚焦 Windows 启停、PID、健康检查和断网启动验收；不实现业务 API |
| FE-01 工作台首页第一阶段 | 已完成 | `app/frontend/`、`docs/Front/Design/`、`docs/superpowers/specs/2026-05-13-frontend-workstation-design.md`、`docs/superpowers/plans/2026-05-13-frontend-workstation-foundation-plan.md`、`docs/superpowers/plans/2026-05-14-workstation-mobile-completion-gaps-plan.md` | 已完成前端地基、首页、新建采集、二维码弹窗和会话状态；补齐工作台状态重试入口、二维码连接帮助地址选择和手动 URL 覆盖；"结束会话"为有意占位，待后端取消/结束会话 API 定义后接入；`npm run test`、`npm run typecheck`、`npm run build` 通过 |
| FE-S1/S2 共享契约和路由骨架 | 已完成 | `app/frontend/src/api/`、`app/frontend/src/app/routes.tsx`、`app/frontend/src/styles/status.ts`、`app/frontend/tests/fixtures/`、`docs/superpowers/plans/2026-05-14-frontend-shared-contracts-routing-plan.md` | 已完成手机采集、任务、审核、导出 API 边界，状态文案、错误归一化、路由常量和占位入口；`npm run test`、`npm run typecheck`、`npm run build` 通过；当前沙箱 Playwright 30 秒超时 |
| FE-02 手机采集页 UX 重构 | 已完成 | `app/frontend/src/pages/mobile-capture/`、`app/frontend/src/components/mobile-capture/QuadSelector.tsx`、`docs/superpowers/2026-05-14-mobile-capture-ux-redesign.md`、`docs/superpowers/plans/2026-05-14-mobile-capture-ux-redesign-plan.md`、`docs/superpowers/plans/2026-05-14-workstation-mobile-completion-gaps-plan.md`、`docs/Front/Design/图片设计稿/` | 已完成单入口拍摄/选择、真实四角拖动、行内页面操作、拖拽排序、底部内容流、重新框选和补拍替换；补齐已保存页面框选坐标回显（`quad_points`→框选四角）；Vitest/typecheck/build 与后端相关 pytest 通过 |

## 后端任务

### BE-00 基础契约与运行骨架

- [x] **BE-00-01 后端最小服务骨架**
  - 范围：Flask app factory、配置加载、统一响应、统一错误、系统状态。
  - 边界：只提供可运行基础，不进入业务实体。

- [x] **BE-00-02 共享状态和错误码基础**
  - 范围：任务状态、会话状态、字段状态、标准错误响应。
  - 边界：状态变更必须先对齐 `docs/Shared/`。

- [x] **BE-00-03 本地 JSON 存储工具**
  - 范围：安全路径、原子写入、JSON 读写。
  - 边界：不引入数据库；真实运行数据不提交。

### BE-01 系统启动与局域网访问

- [x] **BE-01-01 系统状态接口**
  - 范围：返回 `status`、`version`、`started_at`、`lan_addresses`。
  - 边界：不访问外网，不依赖云服务。

- [x] **BE-01-02 Windows 启停脚本联调**
  - 范围：`run.bat`、`stop.bat` 启动本地后端并打开工作台。
  - 边界：不要求 Docker、WSL、GPU 或开发环境。

- [x] **BE-01-03 离线启动验收**
  - 范围：断网环境启动、工作台可访问、局域网地址可用于手机。
  - 边界：不得联网下载依赖、模型或前端资源。

### BE-02 采集会话管理（PR-BE-002）

- [x] **BE-02-01 创建采集会话**
  - 范围：生成 `session_id`、`created_at`、`expires_at`、`status: active`、二维码 URL。
  - 边界：不生成二维码图片细节，只提供手机访问 URL。

- [x] **BE-02-02 查询采集会话**
  - 范围：返回状态、页数、过期时间、页面清单。
  - 边界：查询时可自动把过期 active 会话转为 `expired`。

- [x] **BE-02-03 页面清单骨架**
  - 范围：会话 JSON 中维护 `pages`，支持新增、删除、排序、补拍。
  - 边界：这里只维护页序元数据，不保存真实图片和 quad 信息。

- [x] **BE-02-04 会话写操作 guard**
  - 范围：active 允许编辑；expired 返回 `SESSION_EXPIRED`；locked 返回 `SESSION_LOCKED`。
  - 边界：所有后续上传和页面管理复用同一 guard。

- [x] **BE-02-05 完成采集 finish**
  - 范围：锁定会话、写入 `locked_at`、固化 page order、创建或复用最小 Task 桩。
  - 边界：Task 桩只表示 `uploaded`，不启动算法处理。

- [x] **BE-02-06 finish 幂等**
  - 范围：重复 finish 返回同一个 locked 状态和同一个 task_id。
  - 边界：不得重复创建任务或改变已固化页序。

### BE-03 图片上传与文件管理（PR-BE-003、PR-BE-011）

- [x] **BE-03-01 上传配置和参数错误码**
  - 范围：文件大小、quad 最小面积配置；必要时新增 `INVALID_REQUEST_PARAMS`。
  - 边界：共享错误码变更必须同步 `docs/Shared/error-codes.md` 和测试。

- [x] **BE-03-02 文件类型和大小校验**
  - 范围：jpg/jpeg/png/bmp magic bytes、大小限制、拒绝伪装文件。
  - 边界：不信任文件名和 Content-Type。

- [x] **BE-03-03 路径和文件名安全**
  - 范围：基于 page_id 生成文件名，拒绝路径穿越和危险字符。
  - 边界：不使用用户原始文件名作为保存路径。

- [x] **BE-03-04 quad_points 校验**
  - 范围：四点、数值、范围、自相交、面积过小；缺失时保存 null。
  - 边界：不做裁剪、透视矫正或边界自动识别。

- [x] **BE-03-05 上传 API**
  - 范围：`POST /api/mobile/{session_id}/pages` 接收原图、图片尺寸、可选 quad。
  - 边界：必须调用 PR-BE-002 会话服务分配 page_id/page_no，不独立计算页序。

- [x] **BE-03-06 页面元数据持久化**
  - 范围：保存 `original_image_path`、`processed_image_path: null`、尺寸、quad、上传时间。
  - 边界：processed 路径由后续外部算法成功返回后再写入。

- [x] **BE-03-07 upload_ref 回写**
  - 范围：上传成功后把页面元数据相对路径写回会话 `pages[].upload_ref`。
  - 边界：会话 pages 是唯一页序来源。

- [x] **BE-03-08 上传失败补偿**
  - 范围：文件或元数据保存失败时清理已创建的空页面项和临时文件。
  - 边界：不得留下 finish 可固化的空上传页。

- [x] **BE-03-09 已上传页面框选坐标更新**
  - 范围：`PUT /api/mobile/{session_id}/pages/{page_id}/quad` 保存新的 `quad_points`，复用坐标校验和会话写 guard。
  - 边界：不重新上传原图，不改变页序，不做裁剪、透视矫正或图像质量判断。

- [x] **BE-03-10 已上传页面补拍替换图片**
  - 范围：`PUT /api/mobile/{session_id}/pages/{page_id}/image` 替换当前页原图和框选元数据，保持 `page_id`、`page_no` 和会话页序不变。
  - 边界：替换失败时保留旧图片和旧元数据，不做图像处理、裁剪、透视矫正或质量判断。

### BE-04 任务生命周期（PR-BE-004）

- [x] **BE-04-01 任务列表和详情**
  - 范围：查询任务编号、创建时间、页数、状态、异常信息。
  - 边界：不展示或生成结构化字段。

- [x] **BE-04-02 状态流转校验**
  - 范围：created/uploading/uploaded/processing/ready_for_review/confirmed/exported/failed 合法流转。
  - 边界：非法流转返回 `INVALID_TASK_TRANSITION`。

- [x] **BE-04-03 触发处理与重试入口**
  - 范围：uploaded 任务触发处理；failed 任务可重试；A-lite 因算法模块未配置进入 `failed`。
  - 边界：只保留后续外部模块编排入口，不实现算法适配器。

- [x] **BE-04-04 失败任务信息保存**
  - 范围：保存 error_code、error_message、failed_at 和状态历史；中间产物引用留给 BE-05 接入算法端口后写入。
  - 边界：失败任务不得进入审核态，不提供人工降级补字段路径。

### BE-05 外部算法端口（PR-BE-005、PR-BE-006）

- [x] **BE-05-01 图像处理端口契约**
  - 范围：输入原图路径和 quad，输出 processed 图像路径。
  - 边界：本仓库只定义端口和失败处理，不实现图像处理。

- [x] **BE-05-02 文档解析端口契约**
  - 范围：输入 processed 图像列表，保存外部返回的 pages、blocks、tables、merged_text。
  - 边界：不改写 OCR/解析结果。

- [x] **BE-05-03 字段抽取端口契约**
  - 范围：输入解析结果和 schema，保存候选字段、证据、置信度。
  - 边界：不基于 schema 或 OCR 文本自行生成字段。

- [x] **BE-05-04 算法失败映射**
  - 范围：未配置、异常、空结果、契约非法都进入 `failed`。
  - 边界：不得降级为人工补录或规则兜底。

### BE-06 Schema 管理（PR-BE-007）

- [x] **BE-06-01 通用病历 schema 文件**
  - 范围：字段组、字段 key、显示名、版本号、文书类型。
  - 边界：schema 只定义字段范围，不生成字段值。

- [x] **BE-06-02 schema 加载和版本记录**
  - 范围：任务记录使用的 schema 版本。
  - 边界：历史任务不受后续 schema 修改影响。

- [x] **BE-06-03 候选字段契约校验**
  - 范围：字段 key 必须来自 schema，结构必须合法。
  - 边界：非法候选导致任务 failed。

### BE-07 人工审核结果（PR-BE-008）

- [x] **BE-07-01 审核结果读取**
  - 范围：返回自动候选、人工结果、字段状态、来源证据。
  - 边界：failed 任务不可进入正常审核流。

- [x] **BE-07-02 字段编辑保存**
  - 范围：保存最终值、字段状态、审核时间、修改痕迹。
  - 边界：不覆盖自动抽取原值。

- [x] **BE-07-03 任务确认校验**
  - 范围：未审核、存疑、不可接受空值阻断确认。
  - 边界：错误返回 `REVIEW_VALIDATION_FAILED`。

### BE-08 导出服务（PR-BE-009）

- [x] **BE-08-01 导出前完整性检查**
  - 范围：统计未审核、存疑、空值字段。
  - 边界：不满足确认条件时阻断导出。

- [x] **BE-08-02 JSON 导出**
  - 范围：导出人工审核后的最终结果、任务信息、字段状态。
  - 边界：不得导出未审核自动候选作为最终结果。

- [x] **BE-08-03 Excel 导出**
  - 范围：按字段组组织 Excel，保存到 `exports/`。
  - 边界：导出失败返回 `EXPORT_FAILED`，不破坏审核数据。

### BE-09 日志、隐私和部署（PR-BE-010、PR-BE-001）

- [x] **BE-09-01 本地日志事件**
  - 范围：启动、上传、处理、审核、导出、失败原因。
  - 边界：日志不包含完整病历原文、身份证号、图片 base64 或模型全文输出。

- [x] **BE-09-02 离线依赖和模型目录检查**
  - 范围：检查本地依赖、模型路径、配置占位。
  - 边界：不联网下载依赖或模型。

- [x] **BE-09-03 数据清理策略**
  - 范围：上传、结果、导出、日志的本地保留和手动清理入口。
  - 边界：不得误删其他任务目录或根目录。

### BE-10 API 契约和后端 E2E

- [x] **BE-10-01 API 全量契约测试**
  - 范围：系统、会话、上传、任务、结果、审核、导出。
  - 边界：测试只使用本地 fixtures。

- [x] **BE-10-02 成功 fixture 主流程**
  - 范围：采集多页 → 任务处理成功 → ready_for_review。
  - 边界：算法结果来自外部成功 fixture，不在仓库内推断。

- [x] **BE-10-03 失败 fixture 主流程**
  - 范围：算法未配置/失败/空字段/契约非法全部进入 failed。
  - 边界：不得进入可审核或可导出状态。

## 前端任务

### FE-01 工作台（PR-FE-001）

- [x] **FE-01-01 前端地基和离线资源**
  - 范围：建立 `app/frontend/` 工程结构；CSS、图标、字体和 logo 全部本地打包；定义 API、组件、样式、资产目录边界。
  - 边界：不得使用 CDN、远程字体、远程图片、遥测或运行时联网下载。

- [x] **FE-01-02 工作台启动态**
  - 范围：显示系统已启动、离线运行、手机采集可用等业务化状态。
  - 边界：首页不直接展示本机访问地址、局域网访问地址、端口号或完整采集 URL；连接信息只在系统状态或帮助高级说明中展示。

- [x] **FE-01-03 新建采集入口和二维码弹窗**
  - 范围：调用 `POST /api/capture-sessions`，弹窗展示二维码、会话状态、剩余时间、已上传页数，并提供重新生成二维码、关闭、手机无法连接等操作。
  - 边界：二维码只指向本地局域网/热点地址。

- [x] **FE-01-04 当前采集会话卡片**
  - 范围：active 会话展示进行中状态、已上传页数、剩余时间，并支持重新打开二维码和结束会话入口占位。
  - 边界：二维码按需展示，关闭弹窗后不常驻首页。

- [x] **FE-01-05 首页任务概览和最近任务骨架**
  - 范围：任务为空时显示明确空状态；有任务时按共享状态展示待审核、处理中、失败、已导出统计和最近任务操作。
  - 边界：不伪造示例任务。

- [x] **FE-01-06 系统提醒和医生可理解文案**
  - 范围：首页提醒区命名为“系统提醒”；失败任务展示“查看原因”“重新处理”等操作。
  - 边界：不向医生展示“系统运行日志”“查看日志”或开发者堆栈信息。

### FE-02 手机采集页（PR-FE-002、PR-FE-009）

- [x] **FE-02-01 手机会话加载**
  - 范围：扫码进入后查询会话状态，显示 active/expired/locked。
  - 边界：手机端不做复杂审核。

- [x] **FE-02-02 拍照和选择图片**
  - 范围：单个"拍摄/选择图片"入口支持拍摄或选择本地图片，进入框选页生成上传预览。
  - 边界：不使用第三方云上传。

- [x] **FE-02-03 四边形框选 UI**
  - 范围：四个角点拖动，默认范围可直接确认，框选页不展示像素输入和坐标滑块，异常可重拍。
  - 边界：前端只收集用户确认的坐标，不做裁剪/透视矫正算法。

- [x] **FE-02-04 页面上传状态**
  - 范围：上传原图、尺寸、quad_points；成功回到列表；失败页只显示重试和删除。
  - 边界：上传失败不丢失当前待上传页面。

- [x] **FE-02-05 页面列表管理**
  - 范围：完成采集前查看、删除、拖拽排序、补拍当前页、重新框选已上传页，行内按钮触控高度不小于 44px。
  - 边界：locked 后禁止编辑。

- [x] **FE-02-06 完成采集**
  - 范围：调用 finish，展示会话已锁定并提示回到电脑端。
  - 边界：重复点击不重复创建任务。

### FE-03 任务列表（PR-FE-003）

- [ ] **FE-03-01 任务列表展示**
  - 范围：任务编号、创建时间、页数、处理状态、审核状态、导出状态。
  - 边界：状态文案来自共享状态枚举。

- [ ] **FE-03-02 任务状态刷新**
  - 范围：上传后自动新增，处理状态更新。
  - 边界：不自行推断后端状态。

- [ ] **FE-03-03 失败任务展示和重试**
  - 范围：展示失败原因，提供重新处理入口。
  - 边界：不提供人工降级继续确认/导出路径。

### FE-04 审核页（PR-FE-004、PR-FE-005、PR-FE-006）

- [ ] **FE-04-01 审核页面布局**
  - 范围：原图、解析文本、结构化字段并列查看。
  - 边界：只展示后端结果，不推断字段。

- [ ] **FE-04-02 多页切换**
  - 范围：按页查看原图，查看合并文本和字段结果。
  - 边界：页面顺序来自任务结果。

- [ ] **FE-04-03 字段编辑**
  - 范围：编辑、清空、保存字段最终值。
  - 边界：保存人工结果，不覆盖自动候选。

- [ ] **FE-04-04 字段状态**
  - 范围：未审核、已确认、已修改、存疑、为空。
  - 边界：状态转换遵循共享字段状态。

- [ ] **FE-04-05 来源证据**
  - 范围：点击字段查看来源文本或来源页面。
  - 边界：无来源字段提示人工核验。

- [ ] **FE-04-06 确认审核**
  - 范围：显示未审核/存疑/空值统计，满足条件后确认任务。
  - 边界：不绕过后端确认校验。

### FE-05 导出和错误恢复（PR-FE-007、PR-FE-008）

- [ ] **FE-05-01 JSON 导出入口**
  - 范围：触发 JSON 导出，展示成功/失败。
  - 边界：导出内容来自人工审核结果。

- [ ] **FE-05-02 Excel 导出入口**
  - 范围：触发 Excel 导出，展示成功/失败。
  - 边界：不在前端拼 Excel。

- [ ] **FE-05-03 常见错误提示**
  - 范围：手机连接失败、上传失败、处理失败、抽取失败、导出失败。
  - 边界：错误文案基于后端错误码，不暴露堆栈。

### FE-06 前端离线和 E2E

- [ ] **FE-06-01 离线资源检查**
  - 范围：前端资源本地打包，无 CDN、遥测或外部域名。
  - 边界：测试环境未 mock 的网络请求必须失败。

- [ ] **FE-06-02 完整成功 E2E**
  - 范围：工作台 → 手机采集三页 → 完成采集 → 任务待审核 → 审核确认 → JSON/Excel 导出。
  - 边界：算法结果使用本地 fixture。

- [ ] **FE-06-03 算法失败 E2E**
  - 范围：算法未配置时任务失败，审核入口不可正常继续。
  - 边界：不出现人工补录降级路径。

## 集成和发布任务

- [ ] **REL-01 Windows 本地运行包**
  - 范围：后端、前端、配置、运行时目录、启动脚本整合。
  - 边界：不要求医生安装开发工具。

- [ ] **REL-02 本地配置模板**
  - 范围：模型路径、数据目录、日志目录、导出目录配置说明。
  - 边界：不提交真实路径、密钥或患者数据路径。

- [ ] **REL-03 离线验收脚本**
  - 范围：断网启动、核心 API、前端加载、无外部请求。
  - 边界：不联网下载任何内容。

- [ ] **REL-04 隐私验收**
  - 范围：确认 data/exports/logs 不提交，日志无敏感原文。
  - 边界：不检查真实患者数据内容。

## 建议执行顺序

1. ~~完成 `BE-02` 采集会话管理。~~ ✅
2. ~~并行完成 `BE-03` 图片上传与元数据，但必须等 `BE-02` 的会话 pages 契约稳定后合并。~~ ✅
3. ~~完成 `FE-01` 第一阶段：前端地基、本地资源打包、工作台首页、新建采集、二维码弹窗、当前会话状态，并接通 `GET /api/system/status`、`POST /api/capture-sessions`、`GET /api/capture-sessions/{session_id}`、`GET /api/tasks`。~~ ✅
4. ~~完成 `BE-05` 算法端口失败契约，并把外部模块编排接入 BE-04 的 process/retry 入口。~~ ✅
5. ~~完成 `BE-06` schema 加载、版本记录和候选字段 key 校验。~~ ✅
6. ~~并行推进 `BE-07` 审核结果、`BE-09` 日志/隐私/离线检查、`BE-01` Windows 启停与离线启动。~~ ✅
7. ~~等 `BE-07` 审核数据结构稳定后，推进 `BE-08` 导出服务。~~ ✅
8. ~~按 `docs/superpowers/specs/2026-05-14-frontend-next-stage-orchestration-design.md` 串行收口共享契约和路由骨架。~~ ✅
9. ~~当前下一步实现 `FE-02` 手机采集页。~~ ✅
10. 当前下一步完成 `FE-03` 到 `FE-05` 的任务列表、审核和导出交互。
11. 做 `FE-06` 和 `REL-*` 的 E2E、离线和发布验收。

## 全局边界

- 不接入 HIS/EMR，不写回病历系统。
- 不调用云 API，不使用 CDN、遥测或运行时联网下载。
- 不在本仓库实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正或规则抽取。
- 算法模块缺失、异常、空结构化字段或契约非法时，任务必须进入 `failed`。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 真实运行数据不得提交到 `data/`、`exports/`、`logs/`。
