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
| BE-MVP-04 OCR/文档解析和慢阻肺专病抽取 | 需收敛 | `app/backend/services/algorithm_ports/`、`app/backend/services/copd_extraction/` | OCR/文档解析来自本地模块；慢阻肺专病字段抽取纳入主代码 |
| BE-MVP-05 审核结果保存 | 已完成 | `app/backend/services/review_service.py` | 字段状态先保留 `unreviewed / confirmed / modified` |
| BE-MVP-06 导出服务 | 已完成 | `app/backend/services/export_service.py` | `review` 和 `done` 可导出 JSON/Excel，导出来自人工最终值 |
| BE-MVP-07 批量导出与 OCR 文本重抽取框架 | 已完成 | `app/backend/services/export_service.py`、`app/backend/services/reextraction_service.py` | 先支持批量 JSON zip 和基于已保存 OCR 文本重新触发 LLM 字段抽取；不重新跑 OCR，不做汇总 Excel |
| FE-MVP-01 工作台总览 | 已完成 | `app/frontend/src/pages/workstation/` | 新建任务、二维码、最近任务、状态统计 |
| FE-MVP-02 手机上传页 | 已完成 | `app/frontend/src/pages/mobile-capture/` | 只做拍照/选择图片、多图上传、完成上传 |
| FE-MVP-03 任务管理 | 已完成 | `app/frontend/src/pages/tasks/` | 任务列表、筛选、状态操作 |
| FE-MVP-04 审核界面 | 已完成 | `app/frontend/src/pages/review/` | 原图、OCR 文本、结构化字段编辑、保存、完成、导出 |
| FE-MVP-05 批量导出与重抽取入口 | 待开始 | `app/frontend/src/pages/tasks/`、`app/frontend/src/pages/review/` | 现有前端仅有 API client；后续补任务多选、批量 zip 下载和 OCR 文本重抽取确认入口 |
| REL-MVP-01 本地运行包 | 已完成 | `scripts/package_offline_docker_bundle.sh`、`deploy/windows/`、`Dockerfile`、`docker-compose.yml` | Windows 离线 Docker 包已形成；OCR 通过容器内子进程调用 PaddleOCR-VL |

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

### BE-MVP-04 OCR、文档解析和慢阻肺专病抽取

- [x] **BE-MVP-04-01 本地 OCR/文档解析端口**
  - 范围：定义并接入本机 Python OCR runner，输出转换为文档解析结果。
  - 边界：本仓库不实现 OCR、图像预处理、裁剪或透视矫正；Docker 镜像暂作为后续部署方式。

- [x] **BE-MVP-04-02 输入改为任务图片列表**
  - 范围：输入使用上传顺序的原图列表。
  - 边界：MVP 不依赖 processed 图像或 quad 元数据。

- [x] **BE-MVP-04-03 算法失败映射**
  - 范围：外部模块未配置或异常、结构化处理整体不可用、全字段为空、契约非法均进入 `failed`。
  - 边界：单字段可疑进入审核页，不直接阻断整个任务。

- [ ] **BE-MVP-04-04 慢阻肺专病字段抽取**
  - 范围：按慢阻肺/呼吸系统入院记录 schema 生成全量字段结果，支持未抽取、可疑、复核失败和质量风险提示。
  - 边界：只做当前专病，不扩展为通用医学规则引擎。

- [x] **BE-MVP-04-05 基于已保存 OCR 文本重新抽取框架**
  - 范围：新增 `POST /api/tasks/{task_id}/reextract`，读取已保存 `document_result.json` 或审核结果中的 OCR 文本，复用现有 LLM 字段抽取端口和 schema 校验，生成新的字段候选。
  - 边界：不重新跑 OCR，不重新处理图片，不覆盖已保存的人工审核最终值；缺少 OCR 文本时返回 `REEXTRACTION_VALIDATION_FAILED`。
  - 设计：`docs/superpowers/specs/2026-05-29-batch-export-reextract-design.md`。
  - 计划：`docs/superpowers/plans/2026-05-29-batch-export-reextract-plan.md`。

- [x] **BE-MVP-04-06 schema/prompt 版本元数据框架**
  - 范围：重抽取记录 `schema_version`、`prompt_version`、`source=ocr_text_only`、`run_id` 和候选数量，prompt 版本由 COPD prompt 模块显式常量化。
  - 边界：当前只记录版本和审计元数据；字段方案编辑、prompt 模板管理和版本切换 UI 后置。

### BE-COPD-01 慢阻肺专病字段抽取

- [x] **BE-COPD-01-01 慢阻肺专病 schema**
  - 范围：定义慢阻肺/呼吸系统入院记录结构化字段，含字段 key、中文名、字段组和类型。
  - 边界：为 MVP 字段来源，后续可扩展其他病种 schema。
  - 设计：`docs/superpowers/specs/2026-05-17-copd-extraction-design.md`。
  - 计划：`docs/superpowers/plans/2026-05-17-copd-extraction-plan.md`。

- [x] **BE-COPD-01-02 字段结果契约**
  - 范围：定义结构化字段抽取结果契约，含 `extraction_status`、`verification_status`、`quality_flags`、`ocr_correction` 元数据。
  - 边界：单字段风险进入 `review`，整任务失败仅限无效/全空/无法解析输出。

- [x] **BE-COPD-01-03 OCR 文本分段**
  - 范围：基于规则将 OCR 全文切分为入院记录文书段落。
  - 边界：不实现 OCR 本身；分段为专病抽取提供结构化输入。

- [x] **BE-COPD-01-04 LLM prompt harness**
  - 范围：构建慢阻肺专病字段抽取 prompt，支持字段级和组级抽取。
  - 边界：prompt 工程属于本仓库核心业务代码。

- [x] **BE-COPD-01-05 薄规则质量核验**
  - 范围：规则化校验抽取字段的格式、值域和一致性，生成 `quality_flags` 风险标记。
  - 边界：规则核验不替代人工审核，风险标记用于辅助前端展示。

- [x] **BE-COPD-01-06 LLM 客户端与抽取编排**
  - 范围：调用本地 llama.cpp 服务执行字段抽取，含重试、超时和错误映射。
  - 边界：llama.cpp 为外部本地服务；本仓库负责调用编排和失败处理。

- [x] **BE-COPD-01-07 后端 wiring 与审核元数据保存**
  - 范围：在后端处理流程中集成 COPD 抽取编排器，保留字段抽取元数据供前端展示。
  - 边界：先以 fake port 验证契约，再接入真实 llama.cpp 客户端。

### BE-MVP-05 审核和导出

- [x] **BE-MVP-05-01 审核结果读取和保存**
  - 范围：读取自动候选、保存人工最终值。
  - 边界：不覆盖自动抽取原值。

- [~] **BE-MVP-05-02 字段状态和抽取元数据收敛**
  - 范围：人工审核状态保留 `unreviewed / confirmed / modified`；自动抽取元数据展示未抽取、可疑、复核失败和质量风险。
  - 边界：复杂导出前质控流程后置。

- [x] **BE-MVP-05-03 标记任务完成**
  - 范围：审核完成后任务进入 `done`。
  - 边界：导出不引入独立 `exported` 状态。

- [x] **BE-MVP-05-04 JSON/Excel 导出**
  - 范围：`review` 和 `done` 任务可导出人工最终值。
  - 边界：导出失败不破坏审核数据。

- [x] **BE-MVP-05-05 批量 JSON zip 导出框架**
  - 范围：新增 `POST /api/tasks/export/batch-zip`，接收 `task_ids`，复用现有单任务 JSON 导出模型，生成 `batch-review-export.zip`。
  - 边界：只纳入 `review` / `done` 任务；任一任务不可导出则整体失败；暂不打包 Excel，避免放大当前 Excel 字段不完整问题。
  - 设计：`docs/superpowers/specs/2026-05-29-batch-export-reextract-design.md`。
  - 计划：`docs/superpowers/plans/2026-05-29-batch-export-reextract-plan.md`。

- [ ] **BE-MVP-05-06 Excel 导出字段完整性修复**
  - 范围：排查当前 Excel 只能看到少数字段的问题，确保导出字段数量、字段顺序、sheet 分组和 JSON 导出模型一致。
  - 边界：修复单任务 Excel 后，再考虑是否把 Excel 纳入批量 zip；不得在前端拼 Excel。

- [ ] **BE-MVP-05-07 批量导出清单与失败报告**
  - 范围：批量 zip 内增加 manifest 或导出摘要，记录任务数、成功任务、跳过/失败原因和生成时间。
  - 边界：不引入独立 `exported` 状态；导出失败不修改审核数据。

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

- [ ] **FE-MVP-03-04 批量导出多选入口**
  - 范围：任务管理页支持选择多个 `review` / `done` 任务并调用批量 zip 下载 API。
  - 边界：当前前端已具备 `exportTasksBatchZip(taskIds)` API client；完整多选 UI、禁用态、失败提示和下载反馈后续实现。

- [ ] **FE-MVP-03-05 字段方案管理入口占位**
  - 范围：为后续字段方案/版本选择预留入口，展示当前 schema/prompt 版本和重抽取来源。
  - 边界：前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段；字段方案保存和版本切换必须走后端受控 API。

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

- [ ] **FE-MVP-04-05 OCR 文本重抽取确认入口**
  - 范围：审核页或任务详情页提供“基于现有 OCR 文本重新抽取”入口，调用 `reextractTaskFromOcr(taskId)`，展示 `schema_version`、`prompt_version`、`run_id` 和候选数量。
  - 边界：当前前端已具备 API client；UI 必须明确说明不重新识别图片、不覆盖人工已修改最终值，重抽取结果需回到审核页人工确认。

- [ ] **FE-MVP-04-06 重抽取结果对比与采用**
  - 范围：对比旧人工最终值、新候选值和证据，支持逐字段采用或保留原人工结果。
  - 边界：不得自动覆盖 `confirmed` / `modified` 字段；不得由前端推断字段值。

## E2E 和发布任务

近期推进顺序：MVP 成功/失败主流程 E2E 已完成；运行形态收敛为 Windows 离线 Docker 包。后续发布工作重点是离线验收、依赖锁定和现场排障记录。

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

- [x] **REL-MVP-01 Windows 本地运行包**
  - 状态：已形成 Windows 离线 Docker 包。
  - 范围：后端、前端、配置、模型挂载目录、运行数据目录、Docker 镜像、Windows 导入/启动/停止/日志脚本整合。
  - 边界：不在运行时联网下载模型或依赖；OCR runner 在后端容器内作为子进程调用，不单独起 OCR 容器；真实运行数据仍只落在 `data/`、`exports/`、`logs/`。
  - 经验：2026-05-28 Windows OCR 验证发现 Docker 依赖版本漂移会导致同一参数在 Windows Docker 下超时，部署镜像需锁定 `paddlepaddle-gpu==3.2.1`、`paddleocr==3.5.0`、`paddlex[ocr]==3.5.0`。
  - 经验：2026-05-29 Windows LLM 验证发现默认 `llama-cpp-python` wheel 可能是 CPU-only，字段抽取阶段显存为空且 CPU 占用高；部署镜像需在 CUDA devel 镜像内以 `GGML_CUDA=on` 源码编译 `llama-cpp-python==0.3.22`，并用 `gpus: all` 运行。
  - 经验：2026-05-29 完整流程验证通过；字段复核 JSON 需使用 `llm_max_tokens=4096` 并限制短 comment，失败重试需复用已成功 OCR 的 `document_result.json`，避免字段抽取失败后重复触发 OCR 长尾。

- [ ] **REL-MVP-02 离线验收**
  - 状态：Windows 桌面离线部署包已跑通完整流程，待整理为正式验收记录。
  - 范围：断网启动、前端加载、无外部请求、手机同网可上传、GPU OCR 可完成、导出可用。
  - 边界：验收标准保持离线运行、不联网下载任何内容；验收基线使用 Windows 离线 Docker 包。

## 后置能力

以下能力不属于当前 MVP，除非重新调整范围，否则不进入近期实现计划：

- 采集会话 `active / locked / expired / cancelled`。
- 会话过期、取消、修订采集、解锁。
- 四边形框选、重新框选、裁剪、透视矫正。
- 手机端拖拽排序、补拍替换某页。
- 复杂导出前质控流程。
- 导出前复杂完整性预警面板。
- 多医生协同、云同步、医院系统接口。

## 已规划的后续增强

以下能力已经有后端框架或 API 基础，但完整产品化仍需继续排期：

- 批量导出完整 UI：任务多选、批量 zip 下载、失败提示和导出摘要。
- Excel 导出字段完整性修复：先修复单任务 Excel 只能看到少数字段的问题，再评估是否纳入批量 zip。
- 基于 OCR 文本重新抽取完整 UI：在审核页或任务详情页增加确认入口、版本信息展示和重抽取结果对比。
- 字段方案/schema/prompt 版本管理：后端受控维护字段 schema 和 prompt 版本，支持选择版本后基于已保存 OCR 文本重新抽取。
- 重抽取结果采用策略：新候选结果不得静默覆盖人工已审核字段，需支持逐字段采用、保留和审计。

## 全局边界

- 不接入 HIS/EMR，不写回病历系统。
- 不调用云 API，不使用 CDN、遥测或运行时联网下载。
- 不在本仓库实现 OCR、图像预处理、裁剪、透视矫正或自动边界识别。
- 慢阻肺/呼吸系统入院记录专病字段抽取在主代码内实现，但不得扩展为通用医学规则引擎。
- 外部模块缺失、异常、字段结果整体不可用或契约非法时，任务必须进入 `failed`；单字段可疑进入审核页。
- 前端不得从 schema、OCR 文本或页面内容推断、补造结构化字段。
- 真实运行数据不得提交到 `data/`、`exports/`、`logs/`。
