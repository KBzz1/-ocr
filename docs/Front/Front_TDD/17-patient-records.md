# 前端 TDD — 患者中心记录归档

> API 契约以 `app/backend/tests/test_api_contracts.py` 为可执行权威来源

## 测试目标

为新建任务弹窗、患者管理、患者详情、任务改绑与删除提供组件、路由和 E2E 测试。

## 单元 / 组件测试

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| FE-PAT-T-001 | 单元 | `patients.ts` 暴露 `createPatient/getPatients/getPatientDetail/updatePatient/deletePatient/getPatientRecords` | API client 缺失 |
| FE-PAT-T-002 | 单元 | `tasks.ts` 的 `createTask` 接受 `patient_id/document_type/record_date/record_time` 并序列化 | 旧 client 无 payload |
| FE-PAT-T-003 | 单元 | `tasks.ts` 暴露 `updateTaskMetadata(taskId, patch)` 调用 PATCH `/api/tasks/{id}/metadata` | 改绑 client 缺失 |
| FE-PAT-T-004 | 单元 | `mobileUpload.ts` 不再导出 `updateTaskDocumentType` 或断言其不存在 | 旧 client 未下线 |
| FE-PAT-T-005 | 单元 | `TaskSummary` 类型新增 `patient/document_type/record_date/record_time` | 类型与后端契约漂移 |
| FE-PAT-T-006 | 组件 | `CreateTaskDialog` 同屏展示患者选择、新建患者、记录类型、记录日期、时间，并提交完整 payload | 旧 `createTask()` 无 payload |
| FE-PAT-T-007 | 组件 | 提交前精确同名搜索展示两个已有患者并要求用户点击 "仍然新建" | 同名患者被静默复用 |
| FE-PAT-T-008 | 组件 | 提交成功后弹窗切换为二维码；响应未返回前不存在二维码 | 二维码抢先展示 |
| FE-PAT-T-009 | 组件 | `MobileCapturePage` 移除模板选择器/状态/`changeTaskDocumentType` 调用 | 旧 UI 残留 |
| FE-PAT-T-010 | 组件 | `PatientsPage` 提供搜索、新建、点击进入详情、显示姓名/编号/任务数/最近记录时间 | 列表/搜索/导航缺失 |
| FE-PAT-T-011 | 组件 | 搜索请求进行中禁用搜索按钮，避免快速连击产生并发请求 | 并发请求回填错位 |
| FE-PAT-T-012 | 组件 | `PatientDetailPage` 左侧按 `document_type` 分组导航及数量 | 导航缺失或分组错乱 |
| FE-PAT-T-013 | 组件 | 默认选择第一组，右侧按服务端顺序展示时间轴 | 排序/默认组错乱 |
| FE-PAT-T-014 | 组件 | `review`/`done` 任务点击展开才调用审核接口 | 详情复制审核契约 |
| FE-PAT-T-015 | 组件 | `uploading`/`processing`/`failed` 不请求审核结果 | 错误调用审核 API |
| FE-PAT-T-016 | 组件 | 字段按 Schema 分组展示全部字段（含空值） | 空字段被吞 |
| FE-PAT-T-017 | 组件 | 详情页提供 "进入审核/查看结果" 跳转 | 跳转入口缺失 |
| FE-PAT-T-018 | 组件 | 改名后刷新页头和列表数据 | 旧数据残留 |
| FE-PAT-T-019 | 组件 | `TaskList` 每行展示患者姓名/编号、记录类型、记录时间、"患者已删除" 标记和改绑入口 | 元数据列缺失 |
| FE-PAT-T-020 | 组件 | 改绑弹窗支持选择现有患者或新建患者，processing 任务禁用改绑 | processing 可改绑 |
| FE-PAT-T-021 | 组件 | 患者删除弹窗提供 "仅删除患者" 与 "同时删除患者及关联任务" 两个选项 | 删除选项缺失 |
| FE-PAT-T-022 | 组件 | 同时删除返回后端错误时，页面保留原数据并显示统一错误消息 | 数据被重置 |
| FE-PAT-T-023 | 组件 | 审核页头显示患者姓名、编号、记录类型、记录时间 | 审核页头缺元数据 |
| FE-PAT-T-024 | 路由 | `appRoutes.patients.path === '/patients'` 且 `buildPatientPath('P/A') === '/patients/P%2FA'` | 路由/构建函数缺失 |
| FE-PAT-T-025 | 控制台 | `rg "console\.(log|debug|info|warn|error)" app/frontend/src` 无业务源码命中 | 隐私日志泄露 |

## E2E 路径

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| FE-PAT-E-001 | E2E | 新建 "测试用例" 患者 → 同一弹窗创建任务 → 创建成功后出现二维码 | 创建后无二维码 |
| FE-PAT-E-002 | E2E | 患者管理能搜索到该患者并进入详情 | 搜索/导航失败 |
| FE-PAT-E-003 | E2E | 患者详情显示该任务及记录时间，review fixture 任务可展开字段摘要 | 详情/字段展开失败 |
| FE-PAT-E-004 | E2E | 从患者详情进入审核页 | 跳转失败 |
| FE-PAT-E-005 | E2E | 仅删除患者后，任务管理仍显示该任务并标记 "患者已删除" | 任务消失或标记缺失 |

## Fixture

- 复用 `app/frontend/tests/fixtures/tasks.ts` 并扩展 `mockCreateTask` 默认结果，包含 `patient/document_type/record_date/record_time`
- 患者 fixture 使用 "测试用例" 等虚构姓名
- 审核接口 mock 使用占位字段值；不在 mock 中放真实姓名、身份证号或病历原文

## 隐私约束

- 组件测试和 E2E 不得使用真实患者姓名或 OCR 原文
- 控制台日志断言：业务源码不存在 `console.*`；测试 setup 与调试辅助不在业务源码中
- 错误信息必须使用 `normalizeApiError` 统一处理
