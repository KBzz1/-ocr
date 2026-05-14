# 前端下一阶段并行/串行编排设计

## 范围

本 spec 定义 FE-01 基线收口之后，前端从工作台首页继续推进到手机采集、任务列表、人工审核、导出和离线 E2E 的任务编排方式。重点不是新增页面细节，而是明确：

- 哪些任务必须串行。
- 哪些任务可以并行。
- 每个并行任务包的写入边界。
- 合并顺序和验收门。
- 防止不同执行者互相覆盖、越界实现或提前写不该写的业务。

本 spec 覆盖 `docs/PRD任务清单.md` 中 FE-02、FE-03、FE-04、FE-05、FE-06 的执行组织，并承接 FE-01 当前状态。是否派发子 agent 由任务独立性决定；共享契约、路由骨架、集成收口和提交前审核默认串行执行。

## 权威依据

- `AGENTS.md`：离线运行、无 CDN、无云 API、无遥测、前端不得推断结构化字段。
- `docs/产品PRD.md`：前端 PRD。
- `docs/PRD任务清单.md`：FE-01 到 FE-06。
- `docs/Shared/state-enums.md`：任务状态、会话状态、字段状态。
- `docs/Shared/error-codes.md`：错误码和用户可理解错误。
- `docs/superpowers/specs/2026-05-13-frontend-workstation-design.md`：FE-01 工作台设计。
- `docs/superpowers/plans/2026-05-13-frontend-workstation-foundation-plan.md`：FE-01 执行计划。
- `docs/Front/Front_TDD/00-boundaries-and-principles.md`。
- `docs/Front/Front_TDD/01-test-environment.md`。
- `docs/Front/Front_TDD/02-quality-gates.md`。
- `docs/Front/Front_TDD/04-mobile-capture.md`。
- `docs/Front/Front_TDD/05-page-management.md`。
- `docs/Front/Front_TDD/06-quad-interaction.md`。
- `docs/Front/Front_TDD/07-task-list.md`。
- `docs/Front/Front_TDD/08-manual-review.md`。
- `docs/Front/Front_TDD/09-field-evidence.md`。
- `docs/Front/Front_TDD/10-field-status-confirmation.md`。
- `docs/Front/Front_TDD/11-export.md`。
- `docs/Front/Front_TDD/12-error-recovery.md`。
- `docs/Front/Front_TDD/13-offline-security-privacy.md`。
- `docs/Front/Front_TDD/14-e2e-paths.md`。
- `docs/Front/Front_TDD/15-fixtures.md`。
- `docs/Front/Front_TDD/16-implementation-order.md`。

## 当前基线判断

FE-01 当前应先作为前端基线被收口。基线收口不等于冻结业务，而是确认后续 agent 可以依赖这些事实：

- `app/frontend/` 已经有 Vite + React + TypeScript 工程。
- Vitest、React Testing Library、MSW 和 Playwright 配置已存在。
- 本地资源目录、全局样式、API 客户端和工作台目录结构已存在。
- 测试环境未 mock 的 API 请求应失败。
- 前端资源不应依赖 CDN、远程字体、远程图片或遥测。

FE-01 基线收口必须先串行执行，因为后续页面都会依赖工程脚本、测试设置、API 客户端、状态映射和本地资源规则。

## 总体原则

- 以 TDD 顺序推进：先写 RED 测试，再写最小实现，再重构。
- 每个并行执行者只拥有自己的写入边界。
- API 契约、状态枚举、错误码映射属于共享基础，变更必须先串行合并。
- 手机采集、任务列表、审核、导出可以并行做 UI 和测试，但前提是 S1/S2 已经稳定，且不能同时重写共享 API 客户端和全局状态。
- 前端只展示后端和本地 fixture 返回的数据，不从 OCR 文本、schema 或页面内容推断结构化字段。
- 四边形框选只采集用户确认的坐标，不实现裁剪、透视矫正或图像处理算法。
- 导出只触发后端导出接口，不在前端拼 Excel。
- 所有资源必须本地打包，不引入 CDN、远程字体、远程图片、云服务 SDK 或遥测。

## 必须串行的任务

### S0：FE-01 基线收口

目的：

- 确认当前前端地基可作为后续开发共同基础。
- 记录 Playwright 当前环境是否可运行；如果运行卡住，单独作为 FE-06 风险项，不阻塞组件开发。

写入边界：

- `app/frontend/README.md`
- 必要时 `app/frontend/package.json`
- 必要时 `app/frontend/vite.config.ts`
- 必要时 `app/frontend/tests/setupTests.ts`
- 必要时 `app/frontend/playwright.config.ts`

验收：

- `npm run test` 通过。
- `npm run typecheck` 通过。
- `npm run build` 通过。
- 静态扫描只允许本地或测试 fixture 中的局域网 URL。
- 未 mock API 请求在 Vitest/MSW 中失败。

串行原因：

- 后续所有任务共享同一测试环境和构建配置。
- 如果先并行开发，测试约束不稳定会导致各分支以不同假设写代码。

### S1：共享前端契约层

目的：

- 统一 FE-02 到 FE-05 共用的 API 类型、状态文案、错误展示策略和下载处理接口。

写入边界：

- `app/frontend/src/api/`
- `app/frontend/src/app/routes.tsx`
- `app/frontend/src/styles/status.ts`
- `app/frontend/src/state/`
- `app/frontend/tests/fixtures/`

必须定义：

- 采集会话 API：加载会话、上传页面、完成采集。
- 任务 API：列表、详情、触发处理、重试。
- 审核 API：读取审核数据、保存字段结果、确认审核。
- 导出 API：JSON 导出、Excel 导出。
- 统一错误展示模型：用户文案、错误码、是否可重试。
- 共享状态映射：任务状态、会话状态、字段状态。

串行原因：

- 手机采集、任务列表、审核、导出都会使用这些类型和状态。
- 共享契约如果并行改，容易出现重复类型、状态文案冲突和导出接口不一致。

### S2：主导航和路由骨架

目的：

- 固定桌面端和手机端入口，避免后续页面并行开发时反复改路由。

写入边界：

- `app/frontend/src/app/`
- `app/frontend/src/components/layout/`
- `app/frontend/src/pages/` 下只新增页面入口壳。

路由约定：

- `/`：工作台首页。
- `/mobile/sessions/:sessionId`：手机采集页。
- `/tasks`：任务列表。
- `/tasks/:taskId/review`：人工审核页。
- `/tasks/:taskId/export`：导出入口或任务详情中的导出面板。

串行原因：

- 并行任务需要稳定路由挂载点。
- E2E 主流程依赖固定 URL。

### S3：集成合并和 E2E 收口

目的：

- 将并行完成的页面和 API 接线，验证完整成功路径和失败路径。

写入边界：

- `app/frontend/tests/e2e/`
- `app/frontend/tests/fixtures/`
- 必要时小幅修改页面之间的跳转和数据接线。

验收：

- 工作台新建采集后，手机端通过本地 session URL 进入采集页。
- 手机端完成采集后，任务列表出现任务。
- 成功 fixture 进入 `ready_for_review`，可打开审核页。
- 审核确认后可触发 JSON/Excel 导出。
- 算法失败 fixture 进入 `failed`，不可正常进入审核确认和导出。
- 无外部域名请求。

串行原因：

- E2E 涉及所有页面和共享 fixture，必须在并行任务合并后统一执行。

## 可以并行的任务包

### P1：FE-02 手机采集页

依赖：

- 必须等 S0 完成。
- 推荐等 S1 的采集会话 API 类型稳定后开始。
- 可以在 S2 路由骨架合并后独立开发。

范围：

- 手机会话加载。
- 拍照或选择本地图片。
- 上传预览。
- 四边形角点拖动 UI。
- 上传原图、尺寸和 `quad_points`。
- 页面上传状态。
- 页面列表管理：查看、删除、排序、补拍。
- 完成采集并锁定会话。

写入边界：

- `app/frontend/src/pages/mobile-capture/`
- `app/frontend/src/components/mobile-capture/`
- `app/frontend/src/api/captureSessions.ts`
- `app/frontend/tests/fixtures/sessions.ts`
- `app/frontend/tests/fixtures/uploads.ts`
- 手机采集相关测试文件。

禁止：

- 不实现图像裁剪、透视矫正、OCR 或字段抽取。
- 不使用第三方云上传。
- 不在 locked 会话继续允许编辑页面。
- 不修改任务列表、审核页或导出页。

验收：

- expired 会话显示过期态。
- active 会话允许选择图片并确认四边形坐标。
- 上传失败保留待上传页面并允许重试。
- 完成采集后禁止继续编辑。
- 重复点击完成采集不会重复创建任务。

### P2：FE-03 任务列表和失败重试

依赖：

- 必须等 S0 完成。
- 推荐等 S1 的任务 API 类型和状态映射稳定后开始。
- 可以和 P1、P3、P4 并行。

范围：

- 任务列表展示。
- 状态筛选和刷新。
- 失败原因展示。
- 重新处理入口。
- 从工作台最近任务跳转到任务列表或审核页。

写入边界：

- `app/frontend/src/pages/tasks/`
- `app/frontend/src/components/tasks/`
- `app/frontend/src/api/tasks.ts`
- `app/frontend/tests/fixtures/tasks.ts`
- 任务列表相关测试文件。

禁止：

- 不提供人工降级继续确认或导出路径。
- 不自造任务状态。
- 不展示开发者堆栈或“查看日志”作为医生操作。
- 不重写工作台首页布局。

验收：

- 列表显示任务编号、创建时间、页数、处理状态、审核状态、导出状态。
- 任务状态文案来自共享枚举映射。
- failed 任务显示原因和重新处理入口。
- failed 任务不能直接进入正常审核确认流程。

### P3：FE-04 人工审核页

依赖：

- 必须等 S0 完成。
- 必须等 S1 的审核 API 类型、字段状态和错误模型稳定后开始。
- 可以和 P1、P2、P4 并行，但不能改导出接口。

范围：

- 审核页面布局：原图、解析文本、结构化字段并列查看。
- 多页切换。
- 字段编辑、清空、保存。
- 字段状态：未审核、已确认、已修改、存疑、为空。
- 来源证据展示。
- 确认审核前统计和后端确认校验。

写入边界：

- `app/frontend/src/pages/review/`
- `app/frontend/src/components/review/`
- `app/frontend/src/api/review.ts`
- `app/frontend/tests/fixtures/review.ts`
- 审核相关测试文件。

禁止：

- 不从 schema、OCR 文本或页面内容推断字段值。
- 不覆盖自动候选原值。
- 不绕过后端确认校验。
- 不允许 failed 任务进入正常审核流。

验收：

- 审核页只展示后端返回的候选字段、人工结果和来源证据。
- 编辑保存只保存人工最终值和字段状态。
- 有未审核、存疑或不可接受空值时，确认审核被前端提示和后端校验阻断。
- 无来源字段提示人工核验，不自动补来源。

### P4：FE-05 导出和错误恢复

依赖：

- 必须等 S0 完成。
- 必须等 S1 的导出 API 和统一错误模型稳定后开始。
- 推荐等 P3 的确认审核状态模型稳定后合并。

范围：

- JSON 导出入口。
- Excel 导出入口。
- 导出前完整性提示。
- 导出成功记录展示。
- 手机连接失败、上传失败、处理失败、抽取失败、导出失败的用户可理解错误。

写入边界：

- `app/frontend/src/pages/export/`
- `app/frontend/src/components/export/`
- `app/frontend/src/api/export.ts`
- `app/frontend/src/components/errors/`
- `app/frontend/tests/fixtures/export.ts`
- 导出和错误恢复相关测试文件。

禁止：

- 不在前端拼 Excel。
- 不导出未审核自动候选作为最终结果。
- 不吞掉后端完整性错误。
- 不展示堆栈、完整病历原文、图片 base64 或模型输出全文。

验收：

- confirmed 任务显示 JSON 和 Excel 导出入口。
- 未确认任务导出按钮不可直接执行，并显示“请先确认审核”。
- 后端返回完整性错误时，前端展示错误并不触发下载。
- 导出失败不破坏审核数据。
- 导出成功后展示最近导出时间和格式。

### P5：FE-06 离线、安全和 E2E 质量门

依赖：

- S0 后即可开始排查质量门。
- 完整 E2E 必须等 P1 到 P4 合并后执行。

范围：

- 外部资源扫描。
- MSW 未 mock 请求失败。
- Playwright 配置和当前环境卡住问题排查。
- 成功主流程 E2E。
- 算法失败 E2E。
- 离线约束 E2E。
- README 中记录可运行命令和已知环境限制。

写入边界：

- `app/frontend/tests/e2e/`
- `app/frontend/tests/setupTests.ts`
- `app/frontend/playwright.config.ts`
- `app/frontend/README.md`
- 必要时 `app/frontend/package.json`

禁止：

- 不改业务组件来绕过测试。
- 不放宽未 mock 请求失败门禁。
- 不允许外部域名白名单扩大到公网。

验收：

- `npm run test` 通过。
- `npm run typecheck` 通过。
- `npm run build` 通过。
- Playwright 若环境可用，`npm run test:e2e` 通过。
- Playwright 若当前环境不可用，README 必须记录失败命令、表现和下一步排查位置。
- 静态扫描不发现 CDN、远程字体、远程图片、遥测或公网 API。

## 推荐执行拓扑

```text
S0 FE-01 基线收口
        |
        v
S1 共享前端契约层
        |
        v
S2 主导航和路由骨架
        |
        +---------------- P1 FE-02 手机采集页
        |
        +---------------- P2 FE-03 任务列表和失败重试
        |
        +---------------- P3 FE-04 人工审核页
        |
        +---------------- P4 FE-05 导出和错误恢复
        |
        +---------------- P5 FE-06 质量门先行排查
        |
        v
S3 集成合并和 E2E 收口
```

## 合并顺序

1. 合并 S0。
2. 合并 S1。
3. 合并 S2。
4. P1、P2、P3、P4、P5 可并行开发；如果当前变更集中在同一批共享文件，优先串行完成。
5. 优先合并 P2，因为任务列表是 P3 审核入口和 P4 导出入口的承接页。
6. 合并 P1，验证采集完成后任务出现。
7. 合并 P3，验证 ready_for_review 任务可审核确认。
8. 合并 P4，验证 confirmed 任务可导出。
9. 最后合并 P5 的完整 E2E 和质量门修复。

## 执行分配建议

### 串行协调者

职责：

- 执行 S0、S1、S2、S3。
- 审核并行任务的写入边界。
- 处理跨页面接口冲突。
- 最终跑完整质量门。

必须串行处理的情况：

- 任务会修改 `src/api/`、`src/app/routes.tsx`、`src/state/`、`tests/setupTests.ts` 或 `playwright.config.ts`。
- 任务需要更新 PRD 清单、spec、plan 或 README 的验收口径。
- 任务是提交前审核、集成验证或 E2E 收口。

### 可并行任务 A：手机采集

负责 P1。不得修改任务列表、审核、导出页面。若需要新增共享类型，先向协调者提交契约变更建议，不直接改共享契约。

### 可并行任务 B：任务列表

负责 P2。可以消费任务 API 和状态映射。不得修改审核字段编辑、导出下载或手机采集上传逻辑。

### 可并行任务 C：人工审核

负责 P3。只展示和保存后端返回的审核数据。不得实现字段推断、OCR 文本规则抽取或前端补字段。

### 可并行任务 D：导出和错误恢复

负责 P4。只触发后端导出接口和展示错误，不在前端生成 Excel 内容。

### 可并行任务 E：质量门

负责 P5。可以和其他任务并行跑检查、补测试、修 Playwright 配置，但不得为了让测试通过而放宽离线约束或未 mock 请求失败规则。

## 冲突处理规则

- 两个执行者需要修改同一文件时，优先由串行协调者修改共享文件。
- 页面专属组件放在页面目录或对应 `components/<domain>/` 下，避免把业务状态塞进全局组件。
- 公共组件必须无业务推断逻辑，只接收明确 props。
- 测试 fixture 可以扩展，但不能把真实患者数据、完整病历原文或模型输出全文写入仓库。
- 若后端契约和前端 TDD 文档冲突，先暂停实现并记录冲突，不自行选择其中一边。

## 质量门

每个任务包合并前至少运行：

```bash
cd app/frontend
npm run test
npm run typecheck
```

修改构建、资源、路由或全局样式时额外运行：

```bash
cd app/frontend
npm run build
```

修改 E2E、跨页面流程或 Playwright 配置时运行：

```bash
cd app/frontend
npm run test:e2e
```

如果 `npm run test:e2e` 因当前机器环境卡住或无法启动浏览器，必须在任务总结中写明：

- 执行的命令。
- 失败或卡住的表现。
- 已验证的替代命令。
- 下一步排查位置。

## 明确不做

- 不实现 OCR、LLM 字段抽取、图像裁剪、透视矫正、图像预处理或规则抽取。
- 不接入云 API、CDN、远程字体、远程图片或遥测。
- 不写回 HIS/EMR。
- 不在前端根据 schema 或 OCR 文本补造结构化字段。
- 不提供算法失败后的人工补录降级确认或导出路径。
- 不提交 `data/`、`exports/`、`logs/` 中的真实运行数据。

## 成功定义

完成本 spec 对应的下一阶段编排后，应达到：

- FE-02 到 FE-05 可以由不同 agent 并行推进且写入边界清楚。
- 共享 API、状态、错误模型只在串行阶段收口。
- 每个页面都有可独立验证的组件测试。
- 完整成功 E2E 覆盖工作台、手机采集、任务列表、审核确认和 JSON/Excel 导出。
- 算法失败 E2E 覆盖 failed 状态、不可审核确认、不可导出和重试入口。
- 离线资源和未 mock 请求失败门禁持续有效。

## 自检

- 未使用占位描述。
- 串行任务、并行任务、合并顺序和写入边界均已明确。
- 没有要求前端实现仓库边界禁止的 OCR、LLM、图像处理或字段推断。
- 所有质量门均使用 `app/frontend` 下现有 npm 脚本。
