# MVP 端到端验收设计

## 范围

本 spec 定义 `docs/PRD任务清单.md` 中 `E2E-MVP-01` 和 `E2E-MVP-02` 的正向实现设计。目标是把当前 MVP 主流程从“模块分别可用”推进到“可验收闭环”：

```text
电脑端新建任务
  -> 手机端上传多张图片
  -> 完成上传并用测试 fixture 模拟处理结果
  -> 成功任务进入 review
  -> 电脑端审核保存并标记 done
  -> JSON/Excel 导出
```

同时覆盖失败主流程：

```text
算法未配置 / 算法异常 / 空结构化字段 / 契约非法
  -> 任务进入 failed
  -> 任务管理展示失败原因
  -> 审核页不可伪装为可审核结果
```

本 spec 不设计 Windows 本地运行包。运行形态后续可能采用 Docker，应在主流程 E2E 稳定后单独写部署/运行 spec。

## 权威依据

- `docs/产品PRD.md`：当前产品主流程和 MVP 边界。
- `docs/PRD任务清单.md`：当前任务优先级，运行包已延后。
- `docs/Shared/state-enums.md`：任务状态和字段状态。
- `docs/Shared/error-codes.md`：标准错误码。
- `docs/Shared/terminology.md`：术语。
- `docs/superpowers/specs/2026-05-19-mvp-simplification-design.md`：MVP 轻量化收敛设计。
- `app/README.md`、`app/backend/README.md`、`app/frontend/README.md`：代码边界。

如旧 spec 或 BDD/TDD 文档仍出现 `CaptureSession`、quad、`ready_for_review`、`confirmed`、`exported` 等旧设计，本 E2E 验收以当前 MVP PRD、共享状态枚举和本 spec 为准。

## 当前推进原则

- E2E 优先验证用户主流程，不提前投入 Windows 运行包。
- 测试使用本地 fixture 或 API mock 模拟处理结果，不访问外网，不调用云 API，不下载模型。
- 当前不要求真实触发本地算法模块；算法成功、失败、空字段和契约非法均通过测试 fixture 或 mock 响应模拟。
- 模拟出的结构化字段必须代表“外部算法返回”，不得在前端、后端或测试中根据 schema/OCR 文本推断字段。
- 失败主流程必须进入 `failed`，不得出现人工补字段、规则兜底或前端补造可审核字段。
- MVP 不恢复采集会话、四边形框选、补拍替换、拖拽排序、复杂字段状态或独立导出状态。
- 所有真实运行数据仍不得提交到 `data/`、`exports/`、`logs/`。

## 目标验收层

### 后端 E2E

后端 E2E 用 Flask test client 和测试 fixture 验证真实服务契约。它证明 API、状态流转、持久化、模拟算法失败映射、审核和导出在同一后端进程内闭环。

主要文件：

```text
app/backend/tests/test_backend_e2e.py
app/backend/tests/test_api_contracts.py
app/backend/tests/test_mobile_upload_routes.py
app/backend/tests/test_review_routes.py
app/backend/tests/test_export_routes.py
```

后端 E2E 是浏览器 E2E 的基础。如果后端 E2E 失败，先修后端契约，不通过前端 mock 掩盖。

### 前端浏览器 E2E

前端 E2E 用 Playwright 验证用户可观察流程和页面状态。默认使用 MSW/route mock 固定后端响应，覆盖路由、按钮状态、上传交互、审核保存、完成和导出入口。

主要文件：

```text
app/frontend/tests/e2e/current-workflows.spec.ts
app/frontend/tests/e2e/workstation.spec.ts
app/frontend/tests/fixtures/tasks.ts
app/frontend/tests/fixtures/review.ts
app/frontend/tests/fixtures/export.ts
```

前端 E2E 必须安装网络 gate：未 mock 的 API 请求失败，外部网络请求失败。测试不得依赖真实医院网络、云服务或 CDN。

### 轻量联调检查

主流程稳定后，可增加一个最小联调脚本或 Playwright 模式，使用本地后端服务和测试 fixture 跑一遍真实 HTTP 链路。该检查只作为 E2E 增强，不替代后端测试和前端 mock E2E；它仍然模拟算法结果，不要求本地存在真实算法模块。

如果后续改用 Docker，该联调检查应迁移到 Docker Compose 或等价命令中。

## 成功主流程

### 后端成功流

步骤：

```text
POST /api/tasks
POST /api/mobile-upload/{task_id}/images?token={upload_token}  上传第 1 张
POST /api/mobile-upload/{task_id}/images?token={upload_token}  上传第 2 张
POST /api/mobile-upload/{task_id}/images?token={upload_token}  上传第 3 张
POST /api/mobile-upload/{task_id}/finish?token={upload_token}
GET  /api/tasks/{task_id}
GET  /api/tasks/{task_id}/review
PUT  /api/tasks/{task_id}/review
POST /api/tasks/{task_id}/complete
GET  /api/tasks/{task_id}/export/json
GET  /api/tasks/{task_id}/export/excel
```

断言：

- `POST /api/tasks` 创建 `uploading` 任务，返回 `task_id`、`upload_token`、手机上传 URL。
- 图片上传只接受 `uploading` 状态和正确 token。
- 页序按上传成功顺序写入 `page_no = 1, 2, 3`。
- 完成上传后的处理结果由测试 fixture 或 mock 模拟，任务进入 `review`。
- review 初始化字段来自模拟的外部算法候选，不来自前端或 schema 推断。
- `PUT /review` 保存人工最终值，不覆盖自动候选原值。
- `POST /complete` 后任务进入 `done`。
- JSON/Excel 导出可在 `review` 和 `done` 状态执行，导出不改变任务状态。
- 导出内容来自人工最终值。

### 前端成功流

步骤：

```text
/                         点击“新建任务”，展示二维码和上传 URL
/mobile/upload/:taskId    选择 3 张图片，看到第 1 至第 3 页
/mobile/upload/:taskId    点击“完成上传”，提示回到电脑端
/tasks                    任务状态展示处理中或待审核
/tasks/:taskId/review     查看原图、OCR 文本、结构化字段
/tasks/:taskId/review     修改字段并保存
/tasks/:taskId/review     标记完成，页面显示已完成
/tasks/:taskId/review     JSON/Excel 导出按钮可用并触发下载
```

断言：

- 工作台不展示独立会话状态、过期时间、取消采集、修订采集。
- 手机上传页不出现四边形框选、补拍替换、拖拽排序。
- 审核页只展示后端返回字段；后端返回空字段列表时显示空态，不自行补字段。
- 字段状态只使用 `unreviewed / confirmed / modified`。
- 未 mock API 请求会使测试失败。
- 浏览器控制台不输出完整 OCR 文本、字段原文或图片 base64。

## 失败主流程

### 后端失败场景

必须覆盖：

- 算法模块未配置：任务进入 `failed`，`error_code = ALGORITHM_MODULE_NOT_CONFIGURED`。
- 模拟算法异常：任务进入 `failed`，`error_code = ALGORITHM_MODULE_FAILED`。
- 字段抽取返回空列表：任务进入 `failed`，`error_code = ALGORITHM_CONTRACT_INVALID`。
- 字段候选契约非法：任务进入 `failed`，`error_code = ALGORITHM_CONTRACT_INVALID`。

共同断言：

- 任务保存 `error_code`、`error_message`、`failed_at`。
- 任务状态历史记录失败流转。
- `GET /api/tasks/{task_id}/review` 返回 `INVALID_TASK_TRANSITION` 或等价审核不可读错误。
- 不写入可审核的 `review_result.json`。
- 不创建导出文件。
- 日志只记录错误摘要，不记录完整 OCR 文本、模型输出全文、图片 base64 或身份证号。

### 前端失败场景

必须覆盖：

- 任务管理页展示失败状态和失败原因摘要。
- 失败任务不展示“进入审核”作为可用主操作。
- 失败任务可展示“重新处理”入口；重新处理成功后按后端返回状态更新。
- 失败任务不得展示人工补字段、人工降级、查看日志等不属于 MVP 的入口。
- 审核 URL 被直接打开时，页面展示失败或不可审核状态，不渲染空白可编辑字段表单。

## Fixture 设计

### 图片 fixture

使用测试内存图片或仓库已有静态测试图片，不提交真实病历图片。后端测试使用最小 magic bytes 覆盖 jpg/png/bmp 校验；前端浏览器测试使用现有本地 asset。

### 成功处理 fixture

成功处理 fixture 直接提供处理后的 OCR 文本、页面记录和字段候选，或通过测试替身让任务进入 `review`。它不代表本仓库具备 OCR、文档解析或字段抽取能力。E2E 实施时优先选择最薄的测试 fixture 或 API mock，不为测试强行接入算法端口。

字段候选必须包含：

```json
{
  "field_key": "chief_complaint",
  "field_name": "主诉",
  "original_value": "fixture 返回的主诉内容",
  "evidence": "fixture evidence",
  "page_no": 1,
  "confidence": "medium"
}
```

字段值只代表模拟的外部模块返回，不代表本仓库具备抽取能力。

### 失败处理 fixture

失败 fixture 直接模拟算法未配置、算法异常、空字段和契约非法后的任务结果或 API 响应。不在业务代码加入测试分支。每个失败 fixture 只负责触发一个标准失败类型，避免一个测试同时覆盖多个错误来源。

## 数据与文件边界

- 测试运行目录使用 pytest tmp_path 或 Playwright 临时目录。
- 导出测试只验证临时目录中的文件和下载响应，不写入仓库 `exports/`。
- 日志测试读取临时 `logs/`，只断言摘要事件和脱敏结果。
- 不提交 `data/`、`exports/`、`logs/` 下的运行产物。

## 不做事项

- 不实现 OCR、LLM 字段抽取、图像预处理、裁剪、透视矫正、规则抽取。
- 不恢复 `/api/capture-sessions*` 或 `/api/mobile/{session_id}/*`。
- 不恢复 `quad_points`、`INVALID_QUAD_POINTS` 或四边形框选 UI。
- 不恢复 `ready_for_review`、`confirmed`、`exported` 等旧任务状态。
- 不恢复 `suspicious`、`empty`、`confirmed_empty` 等复杂字段状态。
- 不把导出成功作为任务状态流转。
- 不做 Windows 本地运行包、Dockerfile、Compose 或安装器。

## 测试命令

后端：

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

前端单测：

```bash
npm --prefix app/frontend test
```

前端 E2E：

```bash
npm --prefix app/frontend run test:e2e
```

若前端命令名称与 `package.json` 不一致，以 `app/frontend/package.json` 为准，并同步更新实现计划。

## 实施顺序

1. 盘点现有后端 E2E 与前端 E2E，标出和本 spec 不一致的旧状态、旧接口、旧 fixture。
2. 补齐后端成功主流程三图上传、审核保存、done 后导出不改状态。
3. 补齐后端四类模拟算法失败主流程。
4. 补齐前端成功主流程浏览器 E2E。
5. 补齐前端失败主流程浏览器 E2E。
6. 跑后端、前端单测和前端 E2E，修正暴露出的契约缺口。
7. 更新 `docs/PRD任务清单.md` 中 `E2E-MVP-01/02` 状态；运行包任务保持延后，直到 Docker 或本地脚本方案明确。

## 验收标准

- 后端全量测试通过。
- 前端单测通过。
- 前端 E2E 成功主流程和失败主流程通过。
- E2E 流程中没有旧采集会话、quad 或旧状态断言。
- 失败任务不会生成可审核字段，也不会被前端展示成人工补录路径。
- 导出使用人工最终值，导出成功不改变 `review` 或 `done` 任务状态。
- 文档和测试中的任务状态、字段状态、错误码与 `docs/Shared/` 保持一致。
