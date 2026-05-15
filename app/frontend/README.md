# app/frontend

电脑端工作台和手机端采集页前端工程。当前阶段已包含 Vite + React + TypeScript 地基、电脑端工作台首页、新建采集入口、二维码弹窗、当前会话状态、手机端采集、四边形框选、页面列表、任务列表、审核和导出页面骨架。

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

## 手机端采集约束

- 手机端采集页视觉和交互以 `docs/UI_image/目标设计稿/` 下的未拍照态、框选态、已采集列表态为目标基准。
- 框选页只收集用户确认的四边形坐标；不实现 OCR、透视矫正、图像增强、自动边界识别或字段推断。
- 已上传列表应优先展示框选后的四边形区域预览；该预览只基于本地原图预览和用户确认坐标。
- `src/app/routes.tsx` 固定工作台、手机采集、任务列表、审核、导出路由。

## 职责

- 展示本地服务状态、采集入口和按需二维码。
- 预留后续任务列表、人工审核、导出和手机端采集的目录扩展方向。

## 不负责

- OCR、LLM 字段抽取、图像处理算法。
- 文件系统内部细节。
- 从 schema、OCR 文本或页面内容自行生成字段候选。
