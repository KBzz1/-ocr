# FE-01 前端地基与电脑端工作台执行计划

## 背景

当前阶段进入前端实施准备。`docs/Front/Design/` 下的首页 HTML 和图片设计稿作为视觉草稿使用，不替代 PRD、BDD、TDD 或后端 API 契约。

本计划依据 `docs/superpowers/specs/2026-05-13-frontend-workstation-design.md` 执行。第一阶段先完成前端地基、电脑端首页、扫码二维码弹窗和后端采集会话衔接，以便验证“浏览器打开首页，点击新建采集，看到二维码和会话状态”。

这不是最终范围收缩；后续仍继续实现手机采集、任务列表、审核、字段来源、导出和 E2E。

## 目标

- 建立 `app/frontend/` 的前端工程地基，满足离线运行和本地打包约束。
- 首页按 PRD 展示业务化运行状态，不直接暴露 IP、端口或完整采集地址。
- 点击“新建采集”后调用后端 `POST /api/capture-sessions`。
- 扫码弹窗展示二维码、会话状态、剩余时间、已上传页数、“重新生成二维码”“关闭”“手机无法连接？”。
- 当前采集会话卡片展示 active 会话的状态、页数、剩余时间，并提供“查看二维码”“结束会话”入口占位。
- 首页任务统计颜色、状态文案与 `docs/Shared/state-enums.md` 对齐。
- 首页提醒区命名为“系统提醒”，失败任务操作不展示“查看日志”。

## 执行状态

截至 2026-05-14，FE-01 第一阶段实现已落地：

- `app/frontend/` 已建立 Vite + React + TypeScript 工程。
- Vitest、React Testing Library、MSW 和 Playwright 配置已建立。
- 首页、新建采集、二维码弹窗、当前会话卡片、任务概览、最近任务和系统提醒已接入本地 API 封装和 fixtures。
- `npm run test`、`npm run typecheck`、`npm run build` 已通过。
- 2026-05-15 已补充 `scripts/run-playwright.mjs` 规避 Node 24 下 Playwright test runner 初始化卡住问题；非沙箱本机环境执行 `npm run test:e2e` 已通过，不放宽外部请求和未 mock 请求门禁。

## 推荐任务包

为了降低合并冲突，当前阶段不建议同时开 6 个子代理。推荐压缩为 3 个任务包：

1. `FE-WP-A` 工程地基。
2. `FE-WP-B` 首页 UI。
3. `FE-WP-C` 数据联调、二维码和测试门禁。

### FE-WP-A 工程地基与离线资源

范围：

- 初始化 `app/frontend` 工程。
- 建立 `src/app`、`src/styles`、`src/assets`、`tests`。
- CSS、图标、字体、logo 全部本地打包。
- 配置 Vitest/RTL、Playwright、MSW。
- 添加外部域名请求失败门禁。

验收：

- `npm` 脚本可运行测试和构建。
- 页面不请求 CDN、远程字体、远程图片或外部 API。
- 未 mock API 请求会让测试失败。

写入边界：

- `app/frontend/package.json`
- `app/frontend/vite.config.ts`
- `app/frontend/tsconfig.json`
- `app/frontend/index.html`
- `app/frontend/src/main.tsx`
- `app/frontend/src/app/`
- `app/frontend/src/styles/`
- `app/frontend/src/assets/`
- `app/frontend/tests/setupTests.ts`
- `app/frontend/README.md`

### FE-WP-B 首页 UI 与静态视觉

范围：

- 实现左侧导航、顶部 logo、帮助入口。
- 实现系统状态、新建采集、当前会话、任务概览、最近任务、系统提醒区域。
- 实现二维码弹窗和当前会话卡片的静态/受控组件外观。
- 适配 `1366x768` 和 `1920x1080`。
- 基于设计稿保留工作站风格，但修正不符合 PRD 的文案。

验收：

- 首页不是营销页。
- 标题、按钮、卡片、表格在桌面视口不遮挡。
- 系统提醒标题不是“系统运行日志”。
- 失败操作文案不是“查看日志”。
- 首页不直接展示 IP、端口或完整采集 URL。

写入边界：

- `app/frontend/src/components/layout/`
- `app/frontend/src/components/common/`
- `app/frontend/src/components/workstation/`
- `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- `app/frontend/src/pages/workstation/workstation.types.ts`

### FE-WP-C 数据联调、二维码和测试门禁

范围：

- 封装 `GET /api/system/status`。
- 封装 `POST /api/capture-sessions`。
- 封装 `GET /api/capture-sessions/{session_id}`。
- 封装 `GET /api/tasks`。
- 定义任务状态、会话状态、状态色和操作文案。
- 建立 MSW fixtures。
- 点击新建采集创建会话。
- 展示二维码弹窗。
- 展示会话状态、剩余时间、已上传页数。
- 支持关闭、重新生成二维码、手机无法连接。
- 当前会话卡片可重新打开二维码。
- 从 `GET /api/tasks` 聚合首页统计。
- 最近任务根据状态展示操作按钮。
- 系统提醒展示处理失败、手机连接异常、导出成功等摘要。
- Playwright 覆盖首页加载、新建采集到二维码弹窗、无外部请求、首页不暴露 IP/端口。

验收：

- 成功响应和统一错误响应都被正确解析。
- 状态映射与 `docs/Shared/state-enums.md` 对齐。
- API 层不把错误堆栈、敏感原文传给 toast。
- 关闭弹窗后二维码不常驻首页。
- 创建失败不保留旧二维码。
- 不使用硬编码示例任务或示例统计。
- `failed` 操作为“查看原因”“重新处理”，不出现“查看日志”。
- 概览卡统计 `ready_for_review`、`processing`、`failed`、`exported`。
- E2E 可在本地离线资源下运行。
- console 无错误。
- 未 mock 请求失败。

写入边界：

- `app/frontend/src/api/`
- `app/frontend/src/state/`
- `app/frontend/src/styles/status.ts`
- `app/frontend/tests/fixtures/`
- `app/frontend/tests/e2e/`
- 组件测试文件
- 必要时小幅修改 UI 组件以接入 props/callback，不重写布局

## 并行策略

可以并行：

- `FE-WP-A` 必须先启动并优先合并，它是其他任务的地基。
- `FE-WP-B` 可以在 `FE-WP-A` 的目录约定稳定后开始，先用本地 fixture/props 写 UI。
- `FE-WP-C` 可以在 `FE-WP-A` 后开始，先写 API、状态映射和 RED 测试，再把数据接入 `FE-WP-B` 的组件。

建议拆分 worktree：

| worktree | 任务 | 写入边界 |
|----------|------|----------|
| `fe01-foundation` | FE-WP-A | 工程配置、全局样式、测试配置、资产目录 |
| `fe01-home-ui` | FE-WP-B | layout、首页组件、二维码弹窗静态 UI、任务/提醒组件 |
| `fe01-data-e2e` | FE-WP-C | API、状态映射、fixtures、二维码联调、组件测试、E2E |

合并顺序：

1. `fe01-foundation`。
2. `fe01-home-ui` 与 `fe01-data-e2e` 并行推进，但 `fe01-data-e2e` 最终负责接线收口。
3. 主工作区做一次集成检查和必要的小修。

## 第一阶段测试顺序

按 RED → GREEN → REFACTOR 执行：

1. 离线资源门禁：页面加载不请求 CDN、远程字体、远程图片或外部域名。
2. 工作台状态：系统状态接口返回 running 时显示业务化状态，首页不显示 IP 或端口。
3. 空任务：任务为空时显示明确空状态。
4. 新建采集：点击按钮调用 `POST /api/capture-sessions`。
5. 二维码弹窗：成功后展示二维码、会话状态、剩余时间、已上传页数。
6. 当前会话卡片：弹窗关闭后首页保留会话业务状态，可重新查看二维码。
7. 失败路径：创建会话失败时提示“创建采集会话失败，请重试”，不保留旧二维码。
8. 状态色和文案：任务统计和最近任务按共享状态枚举映射。

## 明确不做

- 不实现手机端拍照、图片上传和四边形框选；这些进入下一阶段。
- 不实现 OCR、LLM、图像处理、裁剪、透视矫正或规则抽取。
- 不实现完整人工审核和导出页面。
- 不在首页展示完整 IP、端口、局域网地址或采集 URL。
- 不向医生展示“查看日志”操作。

## 验收标准

- 断网环境下前端资源可加载，无外部域名请求。
- 浏览器打开工作台首页后可看到“系统已启动”“离线运行”“手机采集可用”。
- 首页不直接展示 IP、端口或完整采集地址。
- 点击“新建采集”后创建后端采集会话。
- 弹窗展示二维码、会话状态、剩余时间和已上传页数。
- 关闭弹窗后二维码不常驻首页，但当前会话卡片可重新打开。
- 失败任务操作文案使用“查看原因”“重新处理”等医生可理解表达。
