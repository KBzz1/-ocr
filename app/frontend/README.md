# app/frontend

电脑端工作台和手机端采集页前端工程。当前阶段完成 FE-01 工作台首页第一阶段：Vite + React + TypeScript 地基、本地资源目录、测试环境约束、电脑端工作台首页、新建采集入口、二维码弹窗和当前会话状态。

## 技术栈

- Vite + React + TypeScript
- Vitest + React Testing Library
- Playwright
- MSW

## 目录

- `src/app/`：应用壳、路由入口和后续模块挂载点。
- `src/api/`：本地后端 API 封装和统一响应解析。
- `src/components/`：通用、布局和工作台组件。
- `src/pages/workstation/`：电脑端工作台首页。
- `src/state/`：工作台聚合和状态派生逻辑。
- `src/styles/`：全局 CSS 和设计 token，必须本地打包。
- `src/assets/`：本地 logo、图标、字体等静态资源。
- `tests/setupTests.ts`：Vitest/RTL/MSW 全局测试约束。
- `tests/fixtures/`：组件测试和 E2E 使用的本地 fixture。
- `tests/e2e/`：Playwright 端到端测试。

## 命令

```bash
npm install
npm run dev
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

已验证：

- `npm run test`
- `npm run typecheck`
- `npm run build`
- `npm run test:e2e`

当前环境限制：

- `@playwright/test@1.52.0` 在 Node 24 下会在 test runner 初始化阶段无输出卡住；`npm run test:e2e` 通过 `scripts/run-playwright.mjs` 自动使用本机 Node 18/20/22 运行 Playwright。
- Codex 沙箱内不能绑定本地 Vite 端口，也不能执行 `/usr/bin/node` fallback；E2E 需要在非沙箱本机环境运行。
- E2E 保持未 mock API 请求失败和外部资源请求失败的约束。
- 当前 Playwright 已覆盖已实现页面：工作台、任务列表、手机采集三页上传、审核字段状态、失败审核态和导出下载；PRD 中后续完整业务链路随页面能力继续补充。

## 离线资源规则

- CSS、图标、字体、logo 和图片资源必须本地打包。
- 不使用 CDN、远程字体、远程图片、遥测或运行时联网下载模型。
- 测试环境中任何未 mock 的请求都会失败；外部域名请求也会失败。
- 首页不直接展示 IP、端口、本机访问地址、局域网访问地址或完整采集 URL；连接信息只允许出现在按需帮助说明中。

## 下一阶段契约层

- `src/api/` 已预留手机采集、任务、审核和导出 API 边界。
- `src/app/routes.tsx` 固定工作台、手机采集、任务列表、审核、导出路由。
- 页面实现仍按 FE-02 到 FE-05 分阶段推进；契约层不实现 OCR、图像处理、字段推断或前端 Excel 生成。

## 职责

- 展示本地服务状态、采集入口和按需二维码。
- 预留后续任务列表、人工审核、导出和手机端采集的目录扩展方向。

## 不负责

- OCR、LLM 字段抽取、图像处理算法。
- 文件系统内部细节。
- 从 schema、OCR 文本或页面内容自行生成字段候选。
- 手机端拍照、图片上传、四边形框选、页序管理、人工审核和导出页面尚未在 FE-01 中实现。
