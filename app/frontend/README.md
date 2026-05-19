# app/frontend

电脑端工作台和手机端上传页前端工程。当前 MVP 目标是：工作台总览、任务管理、审核界面，以及一个轻量手机多图上传页。

## 技术栈

- Vite + React + TypeScript
- Vitest + React Testing Library
- Playwright
- MSW

## MVP 页面

- 工作台总览：新建任务、展示手机上传二维码、最近任务、状态统计。
- 手机上传页：扫码进入任务上传页，拍照/选择图片，多图上传，完成上传。
- 任务管理：任务列表、状态筛选、查看失败原因、进入审核、重新处理、导出。
- 审核界面：原图、OCR 文本、结构化字段编辑、保存、标记完成、导出。

## 目录

- `src/app/`：应用壳、路由入口和模块挂载点。
- `src/api/`：本地后端 API 封装和统一响应解析。
- `src/components/`：通用、布局和工作台组件。
- `src/pages/workstation/`：电脑端工作台总览。
- `src/pages/mobile-capture/`：手机上传页，后续可改名为 mobile-upload。
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

## 离线资源规则

- CSS、图标、字体、logo 和图片资源必须本地打包。
- 不使用 CDN、远程字体、远程图片、遥测或运行时联网下载模型。
- 测试环境中任何未 mock 的请求都会失败；外部域名请求也会失败。

## 手机上传约束

- 手机端只负责拍照/选择图片、多图上传和完成上传。
- 图片页序按上传成功顺序确定。
- 不做四边形框选、重新框选、裁剪、透视矫正、自动边界识别。
- 不做拖拽排序、补拍替换某页、复杂页面管理。
- 不展示 OCR 文本、结构化字段、审核或导出功能。

## 职责

- 展示本地服务状态、任务入口和按需二维码。
- 上传手机图片到指定任务。
- 展示任务列表、处理状态、失败原因和重试入口。
- 展示原图、OCR 文本、结构化字段和人工审核状态。
- 触发保存、标记完成和导出。

## 不负责

- OCR、LLM 字段抽取、图像处理算法。
- 文件系统内部细节。
- 从 schema、OCR 文本或页面内容自行生成字段候选。
- 采集会话、会话过期、修订采集、四边形框选。
