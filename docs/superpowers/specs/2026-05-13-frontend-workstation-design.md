# FE-01 前端地基与电脑端工作台设计

## 范围

对应 `docs/PRD任务清单.md` 中：

- FE-01-01 前端地基和离线资源
- FE-01-02 工作台启动态
- FE-01-03 新建采集入口和二维码弹窗
- FE-01-04 当前采集会话卡片
- FE-01-05 首页任务概览和最近任务骨架
- FE-01-06 系统提醒和医生可理解文案

本 spec 定义第一阶段前端地基和电脑端工作台首页的可执行设计。第一阶段验收目标是：浏览器打开首页，看到业务化系统状态；点击“新建采集”后调用后端创建采集会话；弹窗展示二维码、会话状态、剩余时间和已上传页数；关闭弹窗后首页不常驻二维码但保留当前会话状态。

这不是最终前端范围收缩。后续阶段继续覆盖：

- FE-02 手机端采集、拍照/选图、四边形框选、页面管理和完成采集。
- FE-03 任务列表、筛选、状态刷新、失败重试。
- FE-04 人工审核、字段编辑、字段状态、来源核验和确认。
- FE-05 导出入口、导出前校验、JSON/Excel 下载和错误恢复。
- FE-06 离线资源、隐私、安全和完整 E2E。

## 实施状态

截至 2026-05-14，FE-01 第一阶段已实现并完成基础验证：

- 前端工程、离线资源目录、Vitest/RTL/MSW/Playwright 配置已建立。
- 电脑端工作台首页、新建采集入口、二维码弹窗、当前会话卡片、任务概览、最近任务和系统提醒已实现。
- `npm run test`、`npm run typecheck`、`npm run build` 已通过。
- 2026-05-15 已补充 `scripts/run-playwright.mjs` 规避 Node 24 下 Playwright test runner 初始化卡住问题；非沙箱本机环境执行 `npm run test:e2e` 已通过，不降低离线资源和未 mock 请求失败要求。

## 权威依据

- `docs/产品PRD.md`：PR-FE-001。
- `docs/PRD任务清单.md`：FE-01 ~ FE-06。
- `docs/Shared/state-enums.md`：任务状态、采集会话状态、字段状态。
- `docs/Shared/error-codes.md`：统一错误响应和用户可理解错误。
- `docs/Front/AGENTS.md`：设计稿只作视觉参考，不覆盖 PRD/BDD/TDD。
- `docs/Front/Front_BDD/workstation.md`。
- `docs/Front/Front_BDD/task-list.md`。
- `docs/Front/Front_BDD/error-recovery.md`。
- `docs/Front/Front_BDD/offline-security.md`。
- `docs/Front/Front_TDD/00-boundaries-and-principles.md`。
- `docs/Front/Front_TDD/01-test-environment.md`。
- `docs/Front/Front_TDD/02-quality-gates.md`。
- `docs/Front/Front_TDD/03-workstation.md`。
- `docs/Front/Design/`：首页草稿、图片设计稿和 logo。
- 后端可执行契约：`app/backend/tests/test_api_contracts.py`、`app/backend/tests/test_backend_e2e.py`。

## 设计原则

- 首页是工作站，不是营销页；优先服务重复操作、扫描、核验和异常恢复。
- 首页状态用医生可理解的业务语言：`系统已启动`、`离线运行`、`手机采集可用`。
- 首页不直接展示本机访问地址、局域网访问地址、端口号或完整采集 URL。
- 连接细节只在“系统状态”或“手机无法连接？”高级说明中出现。
- 二维码按需展示：用户主动新建采集或查看当前会话时显示，关闭弹窗后不常驻首页。
- CSS、图标、字体、logo 和图片资源必须本地打包，不使用 CDN、远程字体、远程图片、遥测或运行时联网下载。
- 前端不实现 OCR、LLM、图像处理、裁剪、透视矫正、规则抽取或字段补造。
- 前端不从 schema、OCR 文本或页面内容推断结构化字段。
- 任务状态、会话状态、字段状态必须来自共享状态枚举，不自造业务状态。
- 失败任务显示“查看原因”“重新处理”，不向医生展示“查看日志”、堆栈、开发者错误细节。

## 建议技术栈

第一阶段可采用：

- Vite + React + TypeScript。
- Vitest + React Testing Library。
- Playwright。
- MSW。
- 本地打包图标：优先用项目内 SVG React 组件或本地安装的图标库并进入 bundle。
- 样式：CSS Modules、普通 CSS 或 Tailwind 构建产物均可，但不得运行时加载 Tailwind CDN。

如果后续选择其他前端框架，必须保持以下契约不变：

- 本地资源打包。
- API 封装边界。
- 组件测试和 E2E 门禁。
- 目录职责。

## 文件边界

建议首批落地文件：

```text
app/frontend/
├── package.json
├── index.html
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── app/
│   │   ├── App.tsx
│   │   └── routes.tsx
│   ├── api/
│   │   ├── client.ts
│   │   ├── system.ts
│   │   ├── captureSessions.ts
│   │   └── tasks.ts
│   ├── assets/
│   │   ├── logos/
│   │   ├── icons/
│   │   └── fonts/
│   ├── components/
│   │   ├── common/
│   │   ├── layout/
│   │   └── workstation/
│   ├── pages/
│   │   └── workstation/
│   │       ├── WorkstationPage.tsx
│   │       └── workstation.types.ts
│   ├── state/
│   │   └── workstationStore.ts
│   └── styles/
│       ├── globals.css
│       ├── tokens.css
│       └── status.ts
├── tests/
│   ├── setupTests.ts
│   ├── fixtures/
│   │   ├── sessions.ts
│   │   ├── system.ts
│   │   └── tasks.ts
│   └── e2e/
│       └── workstation.spec.ts
└── README.md
```

第一阶段不写：

- `mobile-capture/` 的拍照、选图、四边形框选实现。
- 审核页字段编辑和来源证据实现。
- 导出页面和文件下载实现。

但可以预留路由占位，避免后续导航结构反复改动。

## 本地资源设计

### CSS

- 不使用 `https://cdn.tailwindcss.com`。
- 若使用 Tailwind，必须作为构建依赖，输出到本地 bundle。
- 状态色、间距、字体栈写入 `src/styles/tokens.css` 和 `src/styles/status.ts`。

### 图标

- 不使用 `https://unpkg.com/...`。
- 首选项目内 SVG 组件，例如 `src/assets/icons/*.tsx`。
- 如果使用图标包，必须通过 npm 依赖本地构建进 bundle。

### 字体

- 第一阶段默认使用系统字体栈：

```css
font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
```

- 如需自带字体，放入 `src/assets/fonts/` 并通过本地 CSS 引入。

### Logo

- 将 `docs/Front/Design/重庆大学logo.webp` 和 `docs/Front/Design/新桥医院logo.jpg` 复制或引用到 `src/assets/logos/`。
- 不从远程 URL 加载 logo。

## API 契约

### GET /api/system/status

用途：

- 首页显示 `系统已启动`、`离线运行`、`手机采集可用`。
- `lan_addresses` 只用于创建二维码的后端逻辑或高级帮助说明，不在首页常驻展示。

前端处理：

- `status === "running"`：展示 ready 状态，新建采集按钮可用。
- 请求失败或超时：展示 `服务无响应` 和 `重试`，禁用新建采集。
- `status === "error"` 或后端返回错误结构：展示后端清洗后的用户可理解错误。

### POST /api/capture-sessions

用途：

- 点击“新建采集”。
- 成功后打开二维码弹窗。

前端期望响应：

```json
{
  "success": true,
  "data": {
    "session_id": "sess_001",
    "status": "active",
    "created_at": "2026-05-13T10:00:00+08:00",
    "expires_at": "2026-05-13T10:30:00+08:00",
    "qr_code_url": "http://192.168.1.100:8080/capture?session=sess_001",
    "page_count": 0
  }
}
```

前端处理：

- 用 `qr_code_url` 生成二维码图形。
- 不把 `qr_code_url` 明文常驻首页。
- 记录当前会话，用于首页会话卡片。
- 失败时提示 `创建采集会话失败，请重试`，不保留旧二维码。

### GET /api/capture-sessions/{session_id}

用途：

- 刷新弹窗和当前会话卡片。
- 显示会话状态、已上传页数、剩余时间。

状态处理：

| 状态值 | 首页卡片文案 | 弹窗处理 |
|--------|--------------|----------|
| `active` | 会话进行中 | 显示二维码、剩余时间、页数 |
| `expired` | 会话已过期 | 禁用二维码，提供重新生成 |
| `locked` | 采集已完成 | 提示到任务列表/最近任务查看 |
| `cancelled` | 会话已取消 | 回到无会话空状态 |

### GET /api/tasks

用途：

- 首页任务概览。
- 最近任务列表。
- 空任务状态。

第一阶段只读展示，不实现复杂筛选页。

## 状态与颜色映射

任务状态以 `docs/Shared/state-enums.md` 为准：

| 状态值 | 中文文案 | 首页统计 | 最近任务操作 | 颜色 |
|--------|----------|----------|--------------|------|
| `created` | 已创建 | 不纳入核心统计 | 查看进度 | 灰色 |
| `uploading` | 上传中 | 不纳入核心统计 | 查看进度 | 灰蓝色 |
| `uploaded` | 上传完成 | 不纳入核心统计 | 查看进度 | 灰蓝色 |
| `processing` | 处理中 | 处理中 | 查看进度 | 紫色/靛色 |
| `ready_for_review` | 待审核 | 待审核 | 开始审核 | 蓝色 |
| `confirmed` | 已确认 | 不纳入核心统计 | 导出结果 | 绿色 |
| `exported` | 已导出 | 已导出 | 查看结果 | 绿色 |
| `failed` | 失败 | 处理失败 | 查看原因/重新处理 | 橙色或红色 |

首页四个概览卡固定为：

- 待审核：统计 `ready_for_review`。
- 处理中：统计 `processing`。
- 处理失败：统计 `failed`。
- 已导出：统计 `exported`。

## 页面结构

### Layout

- 左侧导航：工作台总览、任务管理、人工审核、导出记录、系统状态、设置。
- 顶部栏：页面标题、logo、帮助中心入口。
- 主内容区：首屏操作区、任务概览、最近任务、系统提醒。

### WorkstationPage

数据来源：

- `useSystemStatus()`
- `useCurrentCaptureSession()`
- `useTaskOverview()`
- `useSystemReminders()`

渲染：

- `SystemStatusStrip`
- `NewCapturePanel`
- `CurrentSessionCard`
- `TaskOverviewCards`
- `RecentTasksTable`
- `SystemRemindersPanel`
- `CaptureSessionModal`

## 组件设计

### SystemStatusStrip

显示：

- 系统名称。
- `系统已启动`。
- `离线运行`。
- `手机采集可用`。
- 帮助中心入口。

不显示：

- IP。
- 端口。
- 完整 URL。
- 技术栈或运行命令。

### NewCapturePanel

行为：

- 正常状态下按钮可用。
- 系统状态错误或无响应时按钮禁用。
- 点击后调用 `createCaptureSession()`。
- 请求中防重复点击。

### CaptureSessionModal

显示：

- 二维码。
- `会话已创建` / `等待手机扫码` / `图像传输中`。
- 剩余时间。
- 已上传页数。
- 重新生成二维码。
- 关闭。
- 手机无法连接？

规则：

- 关闭弹窗不取消会话。
- 二维码不常驻首页。
- “手机无法连接？”展开后才显示局域网地址候选或手动输入。

### CurrentSessionCard

无 active 会话：

- 显示空状态。
- 引导新建采集。

有 active 会话：

- 显示会话进行中。
- 显示已上传页数和剩余时间。
- 提供查看二维码。
- 提供结束会话入口占位；真实结束会话可在后续接取消/finish 策略。

### TaskOverviewCards

第一阶段：

- 从 `GET /api/tasks` 聚合计数。
- 点击卡片可预留跳转到任务列表并带状态筛选。

不得：

- 使用硬编码示例数字。
- 伪造任务。

### RecentTasksTable

列：

- 任务编号。
- 创建时间。
- 页数。
- 当前状态。
- 审核进度。
- 操作。

操作映射：

- `ready_for_review`：开始审核。
- `processing` / `uploaded` / `uploading`：查看进度。
- `failed`：查看原因，可在菜单中提供重新处理。
- `confirmed`：导出结果。
- `exported`：查看结果。

### SystemRemindersPanel

标题固定为 `系统提醒`。

提醒类型：

- 处理失败。
- 手机连接异常。
- 导出成功。
- 会话过期。

文案要求：

- 说明问题和下一步操作。
- 不展示堆栈、完整日志、完整病历原文、身份证号、图片 base64 或模型输出全文。

## 测试设计

### 组件测试

覆盖：

- 系统 running 时显示三项业务状态，首页不显示 IP/端口。
- 系统错误时禁用新建采集。
- 点击新建采集只发起一次 POST。
- 创建成功后弹窗显示二维码、会话状态、剩余时间和页数。
- 创建失败后不保留旧二维码。
- 关闭弹窗后首页不显示二维码。
- 当前会话卡片可重新打开二维码。
- 空任务显示空状态，不显示假任务。
- 任务状态色和文案与共享枚举一致。
- 失败任务操作不显示“查看日志”。

### E2E

覆盖：

- 浏览器访问工作台首页无 console error。
- 页面加载不请求外部域名。
- 点击“新建采集”后出现二维码弹窗。
- 首页不直接展示 IP、端口或完整采集 URL。
- 断网/离线模拟下，已本地加载资源不因远程资源失败而崩溃。

### RED 断言

- 如果页面请求 CDN、远程字体、远程图片或外部 API，测试必须失败。
- 如果首页常驻展示 IP、端口或完整采集 URL，测试必须失败。
- 如果二维码使用 `127.0.0.1` 作为手机访问地址，测试必须失败。
- 如果任务失败状态显示“查看日志”，测试必须失败。
- 如果任务统计使用硬编码示例数字，测试必须失败。

## 可并行任务包

这些任务可以并行推进，但当前阶段推荐压缩为 3 个子代理任务包，降低文件冲突和集成成本。

### FE-WP-A 工程地基与离线资源

负责人写入范围：

- `app/frontend/package.json`
- `app/frontend/vite.config.ts`
- `app/frontend/tsconfig.json`
- `app/frontend/index.html`
- `app/frontend/src/main.tsx`
- `app/frontend/src/app/`
- `app/frontend/src/styles/`
- `app/frontend/src/assets/`
- `app/frontend/tests/setupTests.ts`

产出：

- 前端能本地启动和构建。
- CSS、图标、字体、logo 不依赖外部域名。
- 测试环境拦截未 mock 请求。

### FE-WP-B 首页 UI 与静态视觉

负责人写入范围：

- `app/frontend/src/components/layout/`
- `app/frontend/src/components/common/`
- `app/frontend/src/components/workstation/`
- `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- `app/frontend/src/pages/workstation/workstation.types.ts`

产出：

- 按设计稿实现首页布局骨架。
- 实现系统状态、新建采集、当前会话、任务概览、最近任务、系统提醒和二维码弹窗静态/受控组件。
- 不接业务 API 也能展示 loading/empty/error 状态。
- 响应 1366x768 和 1920x1080。
- 首页不直接展示 IP、端口或完整采集 URL。
- 不出现“系统运行日志”或“查看日志”。

### FE-WP-C 数据联调、二维码和测试门禁

负责人写入范围：

- `app/frontend/src/api/`
- `app/frontend/src/state/workstationStore.ts`
- `app/frontend/src/styles/status.ts`
- `app/frontend/tests/fixtures/`
- `app/frontend/tests/e2e/`
- 组件测试文件
- 必要时小幅修改 `FE-WP-B` 产出的组件 props/callback，不重写布局

产出：

- 统一成功/错误响应解析。
- system、captureSessions、tasks API 封装。
- 任务状态、会话状态、颜色文案映射。
- MSW fixtures。
- 点击新建采集调用后端接口。
- 生成二维码。
- 展示会话状态、剩余时间、已上传页数。
- 关闭弹窗后不常驻二维码。
- 当前会话卡片可重新打开二维码。
- 从任务 API 聚合首页统计。
- 最近任务按状态显示操作。
- 系统提醒不使用“日志”文案。
- 空任务状态明确。
- 工作台首页 E2E。
- 新建采集到二维码弹窗 E2E。
- 无外部请求门禁。
- 首页不暴露 IP/端口门禁。

## 合并顺序

建议顺序：

1. FE-WP-A 先合并，给所有前端任务提供工程和测试环境。
2. FE-WP-B 与 FE-WP-C 可并行：B 先做 UI 组件，C 先做 API/状态/RED 测试。
3. FE-WP-C 最后接线，把真实 API 状态和二维码流程接入 B 的 UI。
4. 主工作区做一次集成检查和必要小修。

## 与后续阶段的接口

第一阶段必须为后续留下稳定接口：

- 手机采集页复用 `captureSessions` API 和会话状态类型。
- 任务列表页复用 `tasks` API、状态映射和任务表组件。
- 审核页复用 layout、状态 badge、错误提示和 API client。
- 导出页复用 task 状态、错误处理和下载工具。

## 验收标准

- `app/frontend` 有清晰工程结构和本地资源目录。
- 页面加载没有外部域名请求。
- 首页显示“系统已启动”“离线运行”“手机采集可用”。
- 首页不直接展示 IP、端口或完整采集地址。
- 点击“新建采集”调用后端创建会话接口。
- 弹窗展示二维码、会话状态、剩余时间和已上传页数。
- 弹窗关闭后二维码不常驻首页。
- 当前会话卡片能重新打开二维码。
- 任务概览和最近任务使用后端任务数据，不使用硬编码示例任务。
- 任务状态色和文案与 `docs/Shared/state-enums.md` 对齐。
- 首页提醒区标题为“系统提醒”，不展示“查看日志”。
