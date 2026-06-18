# MVP 导出完整性 + 批量/重抽取 UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛 PRD 阶段 2 三块改动:Excel 导出字段完整性修复 (BE-MVP-05-06)、任务管理页批量导出 UI (FE-MVP-03-04)、审核页 OCR 文本重抽取入口 (FE-MVP-04-05),并保持重抽取后端行为为"直接覆盖审核字段"。

**Architecture:**
- 后端 Excel 完整性:在 `ReviewService.get_or_init` 读取 review_result.json 后按当前 schema 补齐缺失字段并按 schema 顺序重排;在 `ExportService._build_export_model` 中也使用 schema 顺序构造导出字段视图,保证用户未先打开审核页时直接导出也能获得完整字段。把"空 final_value 占位字段"从 `_compute_blocking_fields` 的阻断列表中剔除。
- 后端重抽取覆盖契约:改造 `ReextractionService.reextract`,在新候选通过校验后,按 schema 顺序覆盖 `review_result.json["fields"]`,把字段状态重置为 `unreviewed`,在 `history` 追加 `reextract` 记录。任务为 `done` 时先 `reopen_review`。失败路径不动。
- 前端批量导出:改造 `TasksPlaceholder`/`TaskList`,加多选、批量按钮、摘要条。复用现有 `exportTasksBatchZip` API client。
- 前端重抽取入口:在 `ReviewPage` 顶部操作区加「重新抽取」按钮,成功后展示运行元数据条并刷新 review 字段。**不**写任何免责文案。

**Tech Stack:** Flask / JsonStore / pytest、React 18 / TypeScript / Vite / Vitest / React Testing Library / MSW。

**前置约定:**
- 后端测试命令:`conda run -n manzufei_ocr python -m pytest app/backend/tests -q`
- 前端测试命令(在 `app/frontend/` 下):`npm test -- --reporter=basic`
- 前端类型检查:`npm run typecheck`
- 实施前先记录 `git status --short`。当前 spec/plan/PRD/HTML/图片可能是用户已有未提交改动;不要回滚或误删,只把本计划相关改动纳入提交。

---

## Task 1: Excel 字段完整性 - 补齐与阻断逻辑

**Files:**
- Modify: `app/backend/services/review_service.py`
- Modify: `app/backend/services/export_service.py`
- Test: `app/backend/tests/test_review_service.py`
- Test: `app/backend/tests/test_export_service.py`

- [ ] 写失败测试:review_result.json 缺 schema 字段时,`ReviewService.get_or_init` 补齐占位字段并写回;`summary.total_count` 与 schema 字段数一致。
- [ ] 写失败测试:占位字段 `final_value` 为空、`status == 'unreviewed'`、`extraction_status == 'not_found'`。
- [ ] 写失败测试:`ExportService._compute_blocking_fields` 对空 final_value 占位字段返回空阻断列表。
- [ ] 写失败测试:Excel 导出在 review 缺 schema 字段时,sheet1 包含全部 schema 字段且按 schema 顺序排列;JSON 导出 model 字段集合与 schema 一致。
- [ ] 写失败测试:不先调用 `ReviewService.get_or_init`,直接调用 `ExportService.export_excel` / `_build_export_model` 时,旧 review_result.json 缺 schema 字段仍导出完整 schema 字段。
- [ ] 实现 `ReviewService._hydrate_missing_fields(review, schema)`:按 schema `field_groups` 顺序遍历,对 review 中不存在的 `field_key` 插入占位字段,对已存在 schema 字段保留原值并按 schema 顺序重排,补齐或顺序变化后写回 store。
- [ ] 改造 `ReviewService.get_or_init`:在读取 review 后、return 前调用 `_hydrate_missing_fields`,并刷新 `summary`。
- [ ] 改造 `ExportService._build_export_model`:不要直接遍历 `review["fields"]`;先按当前 schema 生成 schema 字段视图,缺失字段使用与 review hydration 一致的空占位结构,再生成导出 model。
- [ ] 改造 `ExportService._compute_blocking_fields`:仅当 `final_value` 非空且 `status == unreviewed` 时才视为未确认。
- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_review_service.py app/backend/tests/test_export_service.py -q`,确认全绿。
- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests -q`,确认没破坏其他测试。

## Task 2: 重抽取覆盖契约 (BE-MVP-04-05)

**Files:**
- Modify: `app/backend/services/reextraction_service.py`
- Test: `app/backend/tests/test_reextraction_service.py`

- [ ] 修改 `test_reextract_uses_saved_document_text_and_records_versions` 的断言:覆盖后 `final_value` 等于新候选 `original_value`;`status == 'unreviewed'`;`history` 末项 `action == 'reextract'`;`from_value` 是覆盖前的人工值;`run_id` 等于本次 run。
- [ ] 新增失败测试:重抽取后 `field_candidates.json`、`reextract_runs/{run_id}.json` 内容不变,作为审计线索。
- [ ] 新增失败测试:done 任务重抽取后,任务 `status == 'review'`,且 `review_result.json` 已被覆盖(包含新候选的 `final_value` 和 `history` 末项的 `reextract` 记录)。
- [ ] 新增失败测试:review 缺 schema 字段、候选补齐这些字段时,重抽取后 review 也补齐并采用新候选值(避免 review 残留旧 schema 字段集合)。
- [ ] 新增失败测试:新候选有 schema 不存在的 `field_key` 时,该候选被丢弃,不写入 review。
- [ ] 失败路径测试(缺少 OCR 文本、非法契约、字段端口未配置)保持不动。
- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_reextraction_service.py -q`,确认新增/修改后的测试先失败,失败原因指向 review 未被覆盖。
- [ ] 实现 `ReextractionService._overwrite_review_with_candidates(task, review, candidates, schema, run_id)`:按 schema 顺序遍历,对每个 schema 字段在新候选中找到匹配则覆盖 review 字段(`auto_value`/`final_value`/`evidence`/.../状态重置为 unreviewed/`history` 追加 reextract 记录),找不到则保留 review 原字段;候选中 schema 不存在的 field_key 丢弃。
- [ ] 在 `ReextractionService.reextract` 中,候选校验通过、`field_candidates.json` 与 `reextract_runs/{run_id}.json` 写入之后、`reopen_review` 之前(或之后,按 `_overwrite_review_with_candidates` 是否需要 task 已处于 review 决定)调用 `_overwrite_review_with_candidates`,最后 `reopen_review`(若 task 当前是 done)。
- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_reextraction_service.py -q`,确认全绿。
- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests -q`,确认全绿。

## Task 3: 任务管理页批量导出 UI

**Files:**
- Modify: `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`
- Modify: `app/frontend/src/components/tasks/TaskList.tsx`
- Modify: `app/frontend/src/components/tasks/tasks.css`
- Modify: `app/frontend/src/api/export.ts`(仅在需要下载文件名辅助时)
- Test: `app/frontend/src/pages/tasks/TasksPage.test.tsx`

- [ ] 写失败测试:TasksPage 渲染后,review/done 任务行复选框可勾选;uploading/processing/failed 行复选框 disabled 并带 aria-label 说明原因。
- [ ] 写失败测试:勾选 0 个任务时,顶部「批量导出」按钮 disabled;勾选 1+ 个时可点击,且按钮文字随勾选数变化。
- [ ] 写失败测试:模拟 `exportTasksBatchZip` 成功,触发下载(用 `URL.createObjectURL` spy + `<a download>` click spy),展示摘要条「已导出 N 个任务 · YYYY/MM/DD HH:mm」。
- [ ] 写失败测试:模拟 `exportTasksBatchZip` 失败(MSW 返回 500),展示错误消息,任务列表不变。
- [ ] 写失败测试:关闭摘要条按钮清空 state。
- [ ] 写失败测试:`useSilentPolling` 触发刷新后,选择状态保持(用户勾选的 task 仍处于 selected)。
- [ ] 在 `TasksPlaceholder` 增加 `selectedTaskIds: Set<string>` state、`lastBatchExport: { task_ids, exported_at } | null` state、`batchExportError: string | null` state。
- [ ] 实现可勾选过滤函数 `selectableTasks = tasks.filter(t => t.status === 'review' || t.status === 'done')`,以及 `handleToggleSelected(taskId)` / `handleClearSelected()`。
- [ ] 改造 `TaskList` props,新增 `selectedTaskIds`、`onToggleSelected`、`batchExportError`,在每个 row 渲染 `<input type="checkbox">`,disabled 条件走 prop 传入。
- [ ] 在 `TasksPlaceholder` 顶部 toolbar 增加「批量导出」按钮和摘要条,调用 `exportTasksBatchZip([...selectedTaskIds])`;成功:设置 `lastBatchExport`、下载 zip;失败:setError 包装后端消息。
- [ ] 下载逻辑:用 `URL.createObjectURL(blob)` + 一个临时 `<a>` 元素 `.click()`。由于当前 `exportTasksBatchZip` 只返回 `Blob`,本阶段文件名固定为 `batch-review-export.zip`;不要在 UI 里假设可以读取 `Content-Disposition`。
- [ ] 在 `tasks.css` 增加 `.mock-table tr.selected` 高亮和 `.mock-check.disabled` 灰态。
- [ ] 跑 `cd app/frontend && npm test -- --reporter=basic`,确认新测试全绿且不破坏旧测试。
- [ ] 跑 `cd app/frontend && npm run typecheck`,确认无 TS 错误。

## Task 4: 审核页重抽取入口

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/review.css`(如需)
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] 写失败测试:`review` / `done` 任务的 ReviewPage 顶部操作区有「重新抽取」按钮;`uploading` / `processing` / `failed` 任务不显示。
- [ ] 写失败测试:点击「重新抽取」后,按钮进入 `isReextracting` 状态(disabled 且文案变化);调用 `reextractTaskFromOcr(taskId)`。
- [ ] 写失败测试:模拟 `reextractTaskFromOcr` 成功后,顶部出现运行元数据条:`run_id` / `schema_version` / `prompt_version` / `candidate_count`,且调用 `getReview` / `getTaskDetail` 刷新数据。
- [ ] 写失败测试:`done` 任务重抽取成功后,任务状态徽标变为 `review`。
- [ ] 写失败测试:模拟 `reextractTaskFromOcr` 失败(MSW 返回 4xx/5xx),展示错误消息,审核字段不变。
- [ ] 写失败测试:断言 ReviewPage 渲染结果中**不包含**「不重新 OCR」、「不重新处理图片」、「不覆盖人工」等免责文案字符串。
- [ ] 写失败测试:关闭运行元数据条按钮清空 state。
- [ ] 在 `ReviewPage` 增加 `isReextracting: boolean`、`reextractMeta: { run_id, schema_version?, prompt_version?, candidate_count, exported_at } | null`、`reextractError: string | null` state。
- [ ] 在 `review-header__actions` 区块(仅当 `effectiveStatus in {review, done}` 且 `canReview`)渲染「重新抽取」按钮,disabled 条件:`isReextracting || saveStatus === 'saving' || isCompleting`。
- [ ] 实现 `handleReextract()`:调用 `reextractTaskFromOcr(taskId)`,成功后并发调用 `getReview` / `getTaskDetail` 更新本地 state、设置 `reextractMeta`、按 `result.status` 更新 `status`;失败:`setMessage(error.message)`。
- [ ] 渲染运行元数据条(在 `review-header` 下方或 `message` 上方),格式:`已重新抽取 · run_id={run_id} · schema={schema_version} · prompt={prompt_version} · 候选 {candidate_count} 项 [×]`;关闭按钮清空 `reextractMeta`。
- [ ] 跑 `cd app/frontend && npm test -- --reporter=basic`,确认新测试全绿且不破坏旧测试。
- [ ] 跑 `cd app/frontend && npm run typecheck`,确认无 TS 错误。

## Task 5: 全量回归与文档收口

**Files:**
- Modify(可选):`docs/PRD文档/PRD任务清单.md`(如果实施时发现需要进一步标注)

- [ ] 跑 `conda run -n manzufei_ocr python -m pytest app/backend/tests -q`,全量后端测试全绿。
- [ ] 跑 `cd app/frontend && npm test -- --reporter=basic`,全量前端测试全绿。
- [ ] 跑 `cd app/frontend && npm run typecheck`,TS 类型检查通过。
- [ ] 跑 `cd app/frontend && npm run build`,前端 build 通过。
- [ ] 跑 `git diff --stat` 检查改动范围,确保不夹带无关文件。
- [ ] 检查 `app/frontend/src/api/` 没有遗漏的导出/任务 API。
- [ ] 跑 `git status --short` 检查未跟踪/未提交文件;不要删除用户已有的 HTML/图片/spec/plan 草稿,只确认本阶段提交包含计划内文件。
- [ ] 按 Git commit message 中文约定,分 2~3 个 commit 提交:
  1. `Excel 导出字段完整性:review 补齐 + 阻断逻辑调整 (BE-MVP-05-06)`
  2. `重抽取后端覆盖契约 + 前端入口 (BE-MVP-04-05 / FE-MVP-04-05)`
  3. `任务管理页批量导出 UI (FE-MVP-03-04)`
  4. (可选) `新增阶段 2 演示 HTML 与 spec/plan 文档`
- [ ] 验证:本地 `cd app/frontend && npm run dev` + 启动后端,手测 Excel 导出字段数(对比 schema);手测任务管理页多选导出 zip;手测审核页「重新抽取」流程,确认 UI 无免责文案且字段被覆盖。
