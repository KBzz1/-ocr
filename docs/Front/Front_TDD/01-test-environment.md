# 前端 TDD — 测试环境约定

> 关联: `15-fixtures.md`

| 项目 | 约定 |
|------|------|
| 单元/组件测试 | Vitest + React Testing Library |
| 浏览器/E2E | Playwright |
| API Mock | MSW；任何未 mock 的请求必须让测试失败 |
| 移动端视口 | iPhone 12/13 级别视口 `390 x 844`，另测窄屏 `360 x 740` |
| 电脑端视口 | `1366 x 768`、`1920 x 1080` |
| 网络约束 | 禁止外部域名请求；只允许 localhost、127.0.0.1、局域网 IP 或相对路径 |
| 算法能力 | OCR/LLM/图像处理使用固定 fixture 或错误 fixture；不测算法效果，不做前端降级 |
| 测试数据 | `__fixtures__/tasks.ts`、`fields.ts`、`sessions.ts`、`images.ts`、`exports.ts` |
