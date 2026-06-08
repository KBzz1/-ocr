# AGENTS.md

## 作用

本文件是 `app/frontend/` 的长期 onboarding。进入前端代码、组件测试或 Playwright E2E 前先读本文件，再按需读 `README.md`、`tests/fixtures/` 和具体测试文件。

## 目录职责

- `src/`：电脑端工作台、手机上传页、患者管理、任务管理和审核界面。
- `tests/setupTests.ts`：Vitest/RTL/MSW 全局测试约束。
- `tests/fixtures/`：组件测试和 E2E 使用的本地 fixture。
- `tests/e2e/`：Playwright 端到端测试。
- `scripts/run-playwright.mjs`：Playwright 统一入口，负责 Node 版本检查和 fallback。

## 工作规则

- 前端只展示、采集和提交用户输入；不得从 schema、OCR 文本或页面内容推断或补造结构化字段。
- 不使用 CDN、远程字体、远程图片、遥测或运行时联网资源。
- 业务源码不得用 `console.*` 输出患者姓名、OCR 原文、字段值或完整接口对象。
- 创建任务相关 UI 和测试必须按当前契约走：选择或新建患者、选择记录类型、填写记录日期和可选时间，然后创建任务并展示二维码。
- 手机上传页只负责图片选择/拍照、上传和完成上传；不在手机端修改记录类型、不展示 OCR 文本和结构化字段。

## Playwright E2E

- 优先从仓库根目录运行：`npm --prefix app/frontend run test:e2e`；在 `app/frontend/` 内可运行：`npm run test:e2e`。
- 不要直接用 `npm exec playwright test` 替代项目脚本。当前项目脚本会限制 Node `18/20/22`，并在默认 Node 不兼容时尝试回退到 `/usr/bin/node`。
- 如果本机默认 Node 是 `24+`，仍使用项目脚本运行 E2E；直接调用 Playwright 可能在收集测试阶段卡住或行为不一致。
- 如果提示缺少浏览器缓存，开发机上先在 `app/frontend/` 执行一次：`npm exec playwright -- install chromium`。这只用于测试环境准备，不属于应用运行时依赖。
- 如果沙箱内启动 Vite web server 出现 `listen EPERM 127.0.0.1:5173`，不要改 Vite 或 Playwright 配置规避；应在允许绑定本地端口的执行环境中运行项目脚本。
- E2E 的网络请求必须全部 mock。新增患者/任务流程时，同步 mock `/api/patients`、`/api/tasks`、患者详情、患者记录时间轴和移动端上传状态，mock 响应字段要匹配前端类型契约。

## 验证

常用验证入口：

```bash
npm --prefix app/frontend run typecheck
npm --prefix app/frontend run test -- --run
npm --prefix app/frontend run build
npm --prefix app/frontend run test:e2e
```
