# MVP 导出完整性 + 批量/重抽取 UI 设计

## 背景

`2026-05-29-batch-export-reextract-design.md` 与 `2026-05-29-backend-batch-export-reextract-p2-design.md` 已搭好三个能力的后端框架和前端 API client:

- 批量 JSON zip 导出
- 基于已保存 OCR 文本重抽取
- 默认 `section_groups` prompt OCR 风险提示和任务级 `document_type`

但当前 MVP 还有 4 个未收口问题:

1. 单任务 Excel 导出只能看到少数字段(PRD 明确记录的硬缺陷)。导出的字段集合来自 `results/{task_id}/review_result.json["fields"]`,而该列表是在 `ReviewService.get_or_init` 当下按当时 schema 初始化出来的;schema 增加字段后,旧的 review_result.json 不会被补齐,导致 Excel 实际只看到初始化时已经存在的字段。
2. 任务管理页已有 `exportTasksBatchZip(taskIds)` API client,但缺多选 UI、批量按钮、失败提示、下载反馈和导出摘要展示。
3. 审核页已有 `reextractTaskFromOcr(taskId)` API client,但缺触发入口和成功后的元数据展示。
4. **新契约**:重抽取入口不再向用户提示"不重新 OCR / 不重新处理图片 / 不覆盖人工最终值"等免责文案,也不再做"重抽取结果对比与采用";重抽取直接覆盖人工已修改的最终值。

第三项是产品边界修正,本 spec 一并对齐;后端行为和前端文案都要相应收敛。

## 范围

### 单任务 Excel 字段完整性修复 (BE-MVP-05-06)

- 拉齐 Excel 与 JSON 导出模型,使其字段集合、字段顺序、字段分组完全一致。
- review_result.json 必须按当前 schema 完整包含每个 schema 字段,缺失字段以空 final_value + `unreviewed` 占位,但占位字段不阻断导出(因为空值字段没有"未确认"风险,只产生完整性统计)。
- 已有非空 final_value 的字段仍按当前规则:状态为 `unreviewed` 时阻断导出,`confirmed` / `modified` 时允许导出。
- 不改动 `document_type` 行为、错误码或导出文件路径。
- 不修当前 Excel 文件格式与样式,只修字段完整性和顺序。

### 批量导出 UI (FE-MVP-03-04)

- 任务管理页 `app/frontend/src/pages/tasks/` 支持勾选多个任务。
- 顶部出现"批量导出"按钮,只在至少勾选 1 个 `review` / `done` 任务时可点击。
- 不可导出的任务不可勾选(多选框禁用 + tooltip 说明原因)。
- 点击后调用 `exportTasksBatchZip(taskIds)`,成功触发 zip 下载,失败展示后端错误消息。
- 导出后顶部出现摘要条:"已导出 N 个任务:YYYY/MM/DD HH:mm",带"关闭"按钮;24h 内重复点击会覆盖摘要。
- 不在前端拼 Excel,Excel 仍由后端单任务生成,批量 zip 维持当前 JSON-only 范围。

### OCR 文本重抽取入口 (FE-MVP-04-05,沿用并收敛契约)

- 审核页 `app/frontend/src/pages/review/` 顶部"操作区"加一个"重新抽取"按钮,只在 `review` / `done` 状态下可点击。
- 点击后调用 `reextractTaskFromOcr(taskId)`,成功后:
  - 刷新审核页数据(`getReview` + `getTaskDetail`)
  - 在顶部展示一条运行元数据条:`run_id` / `schema_version` / `prompt_version` / `candidate_count`,可关闭
  - 任务若为 `done`,会回退到 `review`,状态徽标自动更新
- 失败展示后端错误,审核数据不动。
- **不显示任何关于"不重新 OCR / 不重新处理图片 / 不覆盖人工最终值"的免责文案**;重抽取的语义(不重跑 OCR / 复用 OCR 文本)体现在后端行为,不在 UI 解释。
- **不做重抽取结果对比与采用 UI**;新结果直接覆盖审核页当前字段(见后端重抽取行为变更)。

### 重抽取后端行为变更 (BE-MVP-04-05,契约修订)

旧契约(`2026-05-29-batch-export-reextract-design.md`、`2026-05-29-backend-batch-export-reextract-p2-design.md`):

- 重抽取只把新候选写入 `field_candidates.json` 与 `reextract_runs/{run_id}.json`,**不覆盖** `review_result.json` 中的人工最终值;前端需在对比采用页里决定是否采用。

新契约(本 spec 取代):

- 重抽取直接把新候选覆盖到 `review_result.json["fields"]`,包括:
  - `final_value`、`auto_value`
  - `evidence`、`page_no`、`confidence`
  - `source_hint`、`source_text`、`source_group_id`、`source_section`
  - `extraction_status`、`verification_status`、`quality_flags`、`ocr_correction`
- 字段状态重置为 `unreviewed`(因为值变了,需要重新人工确认)。
- 重置 `empty_accepted` 为 `false`;不抹掉 `review_note`(保留用户备注)与 `history`(追加一条 `reextract` 记录,记录来源 run_id、覆盖前 final_value、覆盖时间)。
- `field_candidates.json` 和 `reextract_runs/{run_id}.json` 仍按现行实现写入,作为审计线索。
- 任务为 `done` 时,重抽取后回退到 `review`(`task_service.reopen_review`),行为不变。
- 缺少 OCR 文本、字段端口未配置、schema 缺失/非法、候选为空、候选契约非法时,仍返回 `REEXTRACTION_VALIDATION_FAILED`,不修改 `review_result.json`,不调用 `reopen_review`。

## 非目标

- 不动 Excel 文件格式、样式、字体、列宽。
- 不做批量 Excel / 汇总 Excel。
- 不动导出阻塞逻辑在非空字段上的判定;只对"空 final_value 占位字段"放开。
- 不动重抽取的 schema/prompt/规则选择逻辑(沿用任务 `document_type`)。
- 不动重抽取的版本元数据契约(`run_id` / `schema_version` / `prompt_version` / `source` / `created_at` / `candidate_count`)。
- 不实现重抽取结果对比、采用、保留 UI;不做逐字段 diff。
- 不修改老的 spec/plan/契约文档中"不重新 OCR / 不重新处理图片 / 不覆盖人工最终值"等已经存在的措辞;本 spec 是新行为的权威来源,旧文档中冲突的措辞视为已废弃,不再追溯修订。
- 不实现新 schema 字段出现时的字段方案/schema 管理入口(那是后置能力)。
- 不实现 `FE-MVP-04-06`(重抽取结果对比与采用);该任务项从 PRD 任务清单移除(见 PRD 任务清单的同步更新)。

## 后端设计

### 1. 单任务 Excel / JSON 字段完整性

- 修复点位于 `app/backend/services/review_service.py` 的 `ReviewService.get_or_init`:
  - 读取 `results/{task_id}/review_result.json` 之后,按当前 schema(`schema_provider()` 或 `document_profiles.get_profile(task["document_type"]).schema`)做字段补齐。
  - 对每个 schema 字段,若 review 中不存在同 `field_key`,插入占位字段:
    ```json
    {
      "field_key": "...",
      "field_name": "schema.label 或 key",
      "auto_value": "",
      "final_value": "",
      "evidence": null,
      "page_no": null,
      "confidence": null,
      "source_hint": null,
      "source_text": null,
      "source_group_id": null,
      "source_section": null,
      "extraction_status": "not_found",
      "verification_status": "not_checked",
      "quality_flags": [],
      "ocr_correction": null,
      "status": "unreviewed",
      "empty_accepted": false,
      "review_note": null,
      "reviewed_at": null,
      "updated_at": null,
      "history": []
    }
    ```
  - 补齐后**写回** `results/{task_id}/review_result.json`,这样后续 `get_or_init` 不再重复补齐。
  - summary 中的 `total_count` 同步更新为补齐后的字段数。
- 修改 `ExportService._compute_blocking_fields` 行为:
  - 只有 `final_value` 非空且 `status == unreviewed` 的字段才阻断导出。
  - 占位字段(`final_value` 为空)即使 `status == unreviewed` 也不阻断。
  - 不修改 `_ensure_no_blocking_fields` 的对外行为;占位字段不在阻断列表中。
- 不影响:
  - `ExportService._build_export_model` 已经在按 schema 顺序填 `group_key` / `group_label` / `field_name`,字段集合补齐后顺序、分组、字段数都和 schema 一致。
  - 批量 zip 沿用 `_build_export_model`,同样获得全字段视图。
  - 导出文件路径、`record_export` 行为、错误码都不动。
- 兼容性:旧的 review_result.json 在下次 `get_or_init` 时被补齐;不需要单独迁移脚本。

### 2. 重抽取覆盖 `review_result.json`

- 修改 `app/backend/services/reextraction_service.py` 的 `ReextractionService.reextract`:
  - 现有候选校验、`field_candidates.json` 写入、`reextract_runs/{run_id}.json` 写入、`reopen_review`(仅 done)逻辑保留。
  - 新增步骤:用新候选重建 `results/{task_id}/review_result.json["fields"]`。
  - 重建规则:
    1. 读取当前 review_result.json(若不存在,先按当前 schema 构造空 review,见 review_service 的"空 review 初始化"路径,作为兜底;但通常 reextract 时 review_result.json 已存在)。
    2. 收集当前 review 中所有字段 `field_key → field`。
    3. 按当前 schema 的 `field_groups` 顺序遍历;对每个 schema 字段:
       - 若新候选中存在同 `field_key`,用候选覆盖到 review 字段:
         - `auto_value` = `original_value`
         - `final_value` = `original_value`
         - `evidence` / `page_no` / `confidence` / `source_hint` / `source_text` / `source_group_id` / `source_section` / `extraction_status` / `verification_status` / `quality_flags` / `ocr_correction` = 候选值
         - `status` = `unreviewed`
         - `empty_accepted` = `false`
         - 保留 `review_note` 原值
         - `history` 追加一条:
           ```json
           {
             "action": "reextract",
             "from_value": "<覆盖前 final_value>",
             "to_value": "<新 original_value>",
             "run_id": "<run_id>",
             "changed_at": "<now>"
           }
           ```
         - `reviewed_at` = `None`,`updated_at` = `<now>`
       - 若新候选中不存在该 schema 字段,但 review 中已有该字段(可能是用户手工补字段,或之前 schema 删字段),保留原 review 字段(因为没有新数据可覆盖),不强行重置。
    4. 若新候选中有 schema 不存在的 `field_key`,丢弃(避免污染)。
  - 重建后写回 `results/{task_id}/review_result.json`,更新 `updated_at` 和 `summary`。
- 仍然:
  - 任务在 `done` 时,字段写回前先 `reopen_review`(避免 done + 未审核字段的脏状态)。
  - 失败路径(校验失败、缺少 OCR 文本等)不修改 `review_result.json`,行为不变。
- 兼容性:`test_reextraction_service.py::test_reextract_uses_saved_document_text_and_records_versions` 当前断言"final_value == '人工改过'",新契约下应断言"final_value == 新候选 original_value",且 `status == 'unreviewed'`,`history` 末项 `action == 'reextract'`,需要更新该断言。

## 前端设计

### 1. 任务管理页批量导出

- `app/frontend/src/pages/tasks/TasksPlaceholder.tsx` 改名为 `TasksPage` 实现,加多选:
  - 在 `TaskList`(`app/frontend/src/components/tasks/TaskList.tsx`)的行首增加复选框,disabled 条件:`status` 不在 `{review, done}` 中。
  - 顶部 header 区域加"批量导出"按钮:`disabled` 当 `selectedTaskIds.length === 0`。
  - `selectedTaskIds` 受控在 `TasksPage` 组件状态中,与现有 `tasks`、`activeFilter` 并列。
  - 行级 disabled 复选框右侧加 `aria-label` 提示原因(导出仅支持待审核/已完成)。
  - 已选行高亮(沿用现有 `tasks.css` 中的高亮风格)。
- 批量导出按钮 `onClick`:
  - 调用 `exportTasksBatchZip(selectedTaskIds)`。
  - 拿到 blob 后通过 `URL.createObjectURL` + `<a download>` 触发下载,文件名取后端返回的相对路径(若不可得则固定 `batch-review-export.zip`)。
  - 成功时把 `lastBatchExport = { task_ids, exported_at }` 写入 state,顶部展示摘要条:
    ```text
    [i] 已导出 N 个任务 · YYYY/MM/DD HH:mm  [×]
    ```
  - 24 小时内再点会刷新摘要时间,关闭按钮清空。
  - 失败时 `setError(getErrorMessage(error, '批量导出失败: ...'))`。
- 复用 `useSilentPolling` 不动;选择状态在轮询刷新时不清空(用户可能正在勾选)。

### 2. 审核页重抽取入口

- `app/frontend/src/pages/review/ReviewPage.tsx`:
  - 在 `review-header__actions` 区块内,当 `effectiveStatus in {review, done}` 且 `canReview` 时,加一个"重新抽取"按钮(放在"保存修改"右侧)。
  - 增加 `isReextracting` state;按钮 disabled 当 `isReextracting || saveStatus === 'saving' || isCompleting`。
  - `onClick` 调用 `reextractTaskFromOcr(taskId)`。
  - 成功后:
    - 重新调用 `getReview(taskId)` 和 `getTaskDetail(taskId)`,更新 `review` / `fields` / `status` / `taskDetail`。
    - 顶部展示运行元数据条:
      ```text
      [i] 已重新抽取:run_id=reextract_20260605T101530Z · schema=copd.v1 · prompt=copd.prompt.v1 · 候选 12 项  [×]
      ```
    - 摘要条 24 小时内可重复触发覆盖。
  - 失败时 `setMessage(<后端错误>)`,不动审核数据。
- **不写任何"不重新 OCR / 不重新处理图片 / 不覆盖人工最终值"提示文案**;不弹确认对话框。
- `reextractTaskFromOcr` API client 已在 `app/frontend/src/api/tasks.ts` 暴露,直接复用;若返回的 `status` 与现有 `effectiveStatus` 不一致,以服务端返回值为准更新本地 state。

## 测试策略

后端测试先行,覆盖下列用例(用 `pytest -q app/backend/tests` 验证):

1. `test_review_service.py` (新增或补强)
   - review_result.json 缺少 schema 字段时,`get_or_init` 补齐占位字段并写回;`summary.total_count` 与 schema 字段数一致。
   - 占位字段的 `final_value` 为空,`status == 'unreviewed'`,`extraction_status == 'not_found'`。

2. `test_export_service.py` (新增或补强)
   - review_result.json 只有部分 schema 字段时,Excel 导出 sheet1 包含全部 schema 字段,且按 schema 顺序排列。
   - 同步验证 JSON 导出 model 字段集合与 schema 一致。
   - 占位字段不进入 `blocking_fields.unreviewed`,不阻断导出。
   - 非空 final_value 且 status=unreviewed 的字段仍然阻断导出(沿用现有断言)。

3. `test_reextraction_service.py` (修订)
   - 现有 `test_reextract_uses_saved_document_text_and_records_versions` 改为断言:覆盖后 `final_value` 等于新候选 `original_value`,`status == 'unreviewed'`,`history` 末项 `action == 'reextract'`,`from_value` 是覆盖前的人工值,`run_id` 等于本次 run。
   - 新增测试:`reextract` 缺 schema 字段的 review(老 review 初始化场景)也能正确覆盖,新字段值来自候选,缺 schema 字段但新候选有的字段被补齐。
   - 新增测试:任务在 `done` 时,重抽取后 `review_result.json` 已被覆盖,且任务 `status == 'review'`。
   - 失败路径测试(已有)保持不变。

4. `test_api_contracts.py` / `test_export_routes.py` (回归)
   - 单任务 Excel 路由响应头、Content-Type、文件结构不变。
   - 批量 zip 路由响应不变。

前端测试:

5. `TasksPage.test.tsx` (新增或补强)
   - `review` / `done` 任务行复选框可勾选;`uploading` / `processing` / `failed` 行复选框禁用并带说明。
   - 勾选 0 个任务时批量导出按钮 disabled;勾选 1+ 时可点击。
   - 模拟 `exportTasksBatchZip` 成功,触发下载且摘要条出现。
   - 模拟 `exportTasksBatchZip` 失败(返回 4xx/5xx),展示错误消息,审核数据/任务列表不变。
   - 关闭摘要条后清空 state。

6. `ReviewPage.test.tsx` (新增或补强)
   - `review` / `done` 任务顶部"重新抽取"按钮可见,`uploading` / `processing` / `failed` 任务不显示。
   - 点击后调用 `reextractTaskFromOcr`,成功后刷新 review 字段,展示运行元数据条。
   - 点击后失败时,展示错误消息,审核字段不变。
   - **断言**:`ReviewPage` 渲染结果中不包含"不重新 OCR"、"不重新处理图片"、"不覆盖人工"等文案。

## 验收标准

- 后端测试 `conda run -n manzufei_ocr python -m pytest app/backend/tests -q` 全绿。
- 手动验证(开发环境):
  - 创建一个 `copd_admission_record` 任务,完成上传、字段抽取、人工审核若干字段为 `confirmed`。
  - 改 schema 增 2 个新字段(可在 `app/config/` 临时加),重新 `getReview` 后 `review.fields` 数量增加 2,新增字段 `final_value` 为空,`status == 'unreviewed'`。
  - 导出 JSON 和 Excel,两者字段数、顺序、分组一致;占位字段出现在 sheet1 和对应分组 sheet 中,值为空。
  - 把占位字段的 `final_value` 留空,导出仍然成功(不被 `EXPORT_VALIDATION_FAILED` 阻断)。
  - 改一个 `confirmed` 字段的值(模拟用户人工改值),调用重抽取,该字段 `final_value` 变成新候选值,`status == 'unreviewed'`,`history` 出现一条 `reextract` 记录。
  - 任务管理页勾选 2 个 `review` 任务,点批量导出,zip 下载,摘要条出现;勾选 1 个 `failed` 任务时复选框禁用。
  - 审核页"重新抽取"按钮点击后,展示运行元数据条;渲染结果不含免责文案。
- 文档:
  - 本 spec 是新行为权威来源;`docs/PRD文档/PRD任务清单.md` 中 `BE-MVP-04-05`、`FE-MVP-04-05`、新增的 `BE-MVP-05-06` 状态、边界同步更新;`FE-MVP-04-06`(重抽取结果对比与采用)从清单移除。
  - 旧 spec/plan(`2026-05-29-batch-export-reextract-design.md`、`2026-05-29-backend-batch-export-reextract-p2-design.md`)中"不重新 OCR / 不重新处理图片 / 不覆盖人工最终值"等措辞视为已废弃,不再追溯修订;后续引用以本 spec 为准。
  - 后端测试断言(尤其是 `test_reextract_uses_saved_document_text_and_records_versions`)更新为新契约。
