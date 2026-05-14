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

当前环境限制：

- `npm run test:e2e` 在当前 Codex 沙箱中会无输出卡住，使用 `timeout 30s npm run test:e2e` 会以退出码 `124` 结束。
- 同一环境中 `npx playwright --version` 和 Playwright 配置导入可以运行，卡点发生在 Playwright test runner 进入测试枚举/运行阶段。
- 该问题作为 FE-06 离线/E2E 质量门的待排查项记录；不得因此放宽未 mock 请求失败或外部资源拦截规则。

## 离线资源规则

- CSS、图标、字体、logo 和图片资源必须本地打包。
- 不使用 CDN、远程字体、远程图片、遥测或运行时联网下载模型。
- 测试环境中任何未 mock 的请求都会失败；外部域名请求也会失败。
- 首页不直接展示 IP、端口、本机访问地址、局域网访问地址或完整采集 URL；连接信息只允许出现在按需帮助说明中。

## 职责

- 展示本地服务状态、采集入口和按需二维码。
- 预留后续任务列表、人工审核、导出和手机端采集的目录扩展方向。

## 不负责

- OCR、LLM 字段抽取、图像处理算法。
- 文件系统内部细节。
- 从 schema、OCR 文本或页面内容自行生成字段候选。
- 手机端拍照、图片上传、四边形框选、页序管理、人工审核和导出页面尚未在 FE-01 中实现。
