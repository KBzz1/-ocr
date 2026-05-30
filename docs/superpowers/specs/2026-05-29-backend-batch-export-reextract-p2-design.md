# 批量导出、重抽取与文书模板 P2 设计

## 背景

`2026-05-29-batch-export-reextract-design.md` 已完成批量 JSON zip 导出和基于已保存 OCR 文本重抽取的后端框架，前端也已有对应 API client。下一阶段补齐批量导出审计、重抽取元数据、默认抽取策略风险提示，并为多文书类型抽取建立任务级模板选择基础：

- 批量 zip 需要可审计的导出清单，便于离线验收和现场排障。
- OCR 文本重抽取需要给前端返回足够的运行元数据，支持后续确认入口和结果对比。
- 当前默认 `section_groups` 抽取策略的 prompt 已有 OCR 风险提示，但相比字段批量 prompt 缺少部分高风险项，需要补齐，避免默认策略下对单位符号、表格错位、冒号/空格丢失、常见错别字、药名纠偏、矛盾数值等风险提示不足。
- 系统后续会支持多种文书类型，例如慢阻肺/呼吸系统入院记录、病程记录等。每个任务只对应一种文书模板，字段抽取必须按任务的 `document_type` 选择 schema、prompt 和抽取规则。
- 电脑端新建任务仍保持一键创建，不增加模板选择；手机端上传页负责选择当前任务模板，并把选择保存到后端。

本阶段不做同一任务内多文书混合拆分，也不做 OCR 自动判断文书类型。

## 目标

1. 批量 zip 根目录增加 `manifest.json`，记录导出摘要、成功任务清单和失败任务清单。
2. 批量导出保持当前原子性：任一任务不可导出时整体失败，不生成部分成功 zip，不修改审核数据。
3. 重抽取接口保持 `ocr_text_only` 语义，不重新跑 OCR，不重新处理图片，不覆盖人工最终值。
4. `section_groups` prompt 补齐 OCR 风险提示和硬约束，与默认运行策略承担的风险相匹配。
5. 为后续前端 UI 提供稳定字段：批量导出可下载 zip；重抽取可展示 `schema_version`、`prompt_version`、`source`、`run_id`、`candidate_count`。
6. 每个任务持久化 `document_type`，任务处理和重抽取按 `document_type` 选择 schema、prompt 和抽取规则。
7. 手机端上传页提供文书模板选择，选择结果写回当前任务；电脑端新建任务弹窗不提供模板选择。
8. 新任务默认模板来自后端保存的 `last_document_type`；如果没有历史值，则默认 `copd_admission_record`。
9. 模板在任务进入 `processing` 后锁定，避免处理中的 schema/prompt/rule 被切换。

## 非目标

- 不做批量 Excel 或汇总 Excel。
- 不引入独立 `exported` 状态。
- 不做部分成功下载；本阶段 manifest 中的失败清单用于失败前校验报告和未来扩展，不改变整体失败语义。
- 不做前端字段推断、OCR 文本解析或 schema 侧字段补造。
- 不做重抽取结果逐字段采用；该能力后续单独设计。
- 不扩展为通用医学规则引擎。
- 不在电脑端新建任务弹窗增加模板选择。
- 不从 OCR 文本、图片内容或文件名自动判断文书类型。
- 不支持同一任务中混合多种文书模板分别抽取。
- 本阶段只把文书类型作为任务级模板选择；病程记录等新模板的完整字段 schema、prompt 和规则可后续逐个接入。

## 后端设计

### 文书模板与 document_type

任务记录必须稳定包含：

- `document_type`：任务级文书模板类型，例如 `copd_admission_record`。
- `schema_version`：本任务处理使用的 schema 版本。
- `prompt_version`：本任务字段抽取使用的 prompt 版本。若当前 task 结构暂不记录，也必须在字段候选 metadata、重抽取 run 和导出 manifest 中可追溯。
- `extraction_profile`：可选，表示后端选择的抽取 profile；第一版可与 `document_type` 同名。

创建任务时，后端读取本地设置 `last_document_type` 作为默认 `document_type`。如果设置缺失或值不在可用模板列表中，默认使用 `copd_admission_record`。电脑端新建任务 API 不要求传入模板。

手机端选择模板成功后，后端更新：

- 当前任务的 `document_type`。
- 当前任务对应的 `schema_version` 预览值。
- 本地设置 `last_document_type`，作为下一次新建任务默认模板。

任务状态不是 `uploading` 时，后端拒绝修改 `document_type`，返回 `INVALID_TASK_TRANSITION` 或专用校验错误。已经上传图片但仍处于 `uploading` 时可以修改模板，因为尚未进入字段抽取。

### 文书模板 registry

后端新增文书模板 profile registry。每个 profile 至少包含：

```json
{
  "document_type": "copd_admission_record",
  "label": "入院记录",
  "schema_version": "copd_admission_record.v1",
  "prompt_version": "copd_extraction_prompt.v1",
  "schema": {},
  "field_port": "copd",
  "quality_rule_profile": "copd_admission_record"
}
```

第一版 registry 只必须注册当前已实现的 `copd_admission_record`。后续新增病程记录时，通过新增 profile、schema、prompt builder 和抽取器接入，不改任务生命周期主流程。手机端可用模板列表只能暴露已经完成注册且具备 schema/prompt/field port 的 profile；未接入抽取能力的模板不得出现在可选项中。

`SchemaService` 需要从“只返回当前 schema”扩展为按 `document_type` 取 schema：

- `get_schema(document_type)`：返回指定文书类型 schema。
- `get_available_document_types()`：返回手机端可展示的模板列表，包含 `document_type`、`label`、`schema_version`。
- `get_default_document_type()`：返回 `last_document_type` 或兜底默认值。

字段抽取编排时，`ProcessingOrchestrator` 不再直接使用全局当前 schema，而是读取任务上的 `document_type`，通过 registry 选择 profile，并构造输入：

```python
{
    "task_id": task_id,
    "document_type": task["document_type"],
    "document_result": doc_result,
    "schema": schema,
    "prompt_version": profile.prompt_version,
}
```

字段抽取端口必须按 `document_type` 选择实现。当前 `copd_admission_record` 仍走现有 COPD extractor；其它未注册文书类型必须失败，任务进入 `failed`，错误原因不能被伪装成空字段成功。

### 手机端模板选择 API

手机端上传页需要两个后端能力：

1. 获取可用模板列表和当前任务模板：

```http
GET /api/mobile-upload/{task_id}?token=...
```

响应在现有上传状态基础上增加：

```json
{
  "task_id": "task_001",
  "status": "uploading",
  "document_type": "copd_admission_record",
  "document_type_label": "入院记录",
  "available_document_types": [
    {
      "document_type": "copd_admission_record",
      "label": "入院记录",
      "schema_version": "copd_admission_record.v1"
    },
    {
      "document_type": "progress_note",
      "label": "病程记录",
      "schema_version": "progress_note.v1"
    }
  ],
  "page_count": 0,
  "images": []
}
```

2. 修改当前任务模板：

```http
PATCH /api/mobile-upload/{task_id}/document-type?token=...
Content-Type: application/json

{
  "document_type": "progress_note"
}
```

成功响应返回更新后的任务模板摘要：

```json
{
  "task_id": "task_001",
  "document_type": "progress_note",
  "document_type_label": "病程记录",
  "schema_version": "progress_note.v1"
}
```

约束：

- 必须校验上传 token。
- 只有 `uploading` 状态允许修改。
- `document_type` 必须来自 registry。
- registry 只返回具备完整 schema、prompt 和抽取端口的模板；未完成接入的模板不展示、不允许选择。
- 修改成功后更新 `last_document_type`。
- 手机端只传用户选择，不根据图片或 OCR 推断模板。

### 批量导出 manifest

`ExportService.export_batch_zip(task_ids)` 在所有任务预校验通过后生成 zip。zip 内容：

- `{task_id}/{task_id}.review.json`：沿用单任务 JSON 导出模型。
- `manifest.json`：批量导出清单。

`manifest.json` 结构：

```json
{
  "format": "batch_zip",
  "generated_at": "2026-05-29T10:00:00+00:00",
  "task_count": 2,
  "success_count": 2,
  "failed_count": 0,
  "success_tasks": [
    {
      "task_id": "task_001",
      "status": "review",
      "json_path": "task_001/task_001.review.json",
      "field_count": 72,
      "schema_version": "1.0.0",
      "document_type": "copd_admission_record"
    }
  ],
  "failed_tasks": []
}
```

当前导出仍是全成功才写 zip，因此成功 zip 内 `failed_tasks` 默认为空。服务内部仍应先构建校验摘要，便于失败时在 `EXPORT_VALIDATION_FAILED` 的 `details` 中返回不可导出任务原因；路由继续返回错误响应，不写 zip。

失败 details 建议包含：

```json
{
  "format": "batch_zip",
  "task_count": 2,
  "failed_tasks": [
    {
      "task_id": "task_002",
      "error_code": "EXPORT_VALIDATION_FAILED",
      "reason": "只有待审核或已完成任务可以导出",
      "status": "processing"
    }
  ]
}
```

### 导出记录

批量 zip 生成成功后，继续对每个成功任务调用 `TaskService.record_export(task_id, format="batch_zip", relative_path=relative_path)`。失败时不记录导出，不修改任务状态，不修改审核结果。

### 重抽取元数据

`POST /api/tasks/{task_id}/reextract` 当前返回：

- `task_id`
- `status`
- `run_id`
- `source`
- `schema_version`
- `prompt_version`
- `candidate_count`

本阶段不改变字段候选保存语义。服务继续写入：

- `results/{task_id}/field_candidates.json`
- `results/{task_id}/reextract_runs/{run_id}.json`

审计记录中应至少包含上述返回字段、`created_at` 和候选数量。不得保存完整模型输出到日志事件。

重抽取必须使用任务当前 `document_type` 对应的 schema、prompt 和抽取规则。若任务缺少 `document_type`，按兼容策略视为 `copd_admission_record` 并回写任务记录；若 `document_type` 未注册，返回 `REEXTRACTION_VALIDATION_FAILED`，不得回退到 COPD prompt。

### section_groups prompt OCR 风险提示

默认 `COPDFieldExtractionPort` 使用 `section_groups` 策略。该策略的 prompt 必须显式包含以下风险提示和约束：

- 字符混淆：`1/I/l`、`0/O/o`、`BHI/BMI`、`cT/CT/Ct`。
- 血气项目名混淆：`P62/P02/PC02/PCO2/PO2/PaO2/PaCO2`。
- 药名和医学词近形、同音、缺字错读，例如噻托溴铵、二羟丙茶碱等常见风险。
- 单位断裂和单位符号错读，例如 `+10^9/L` 可能是 `×10^9/L`。
- 表格错位、项目和值跨行、冒号和空格丢失。
- 小数点、逗号异常和常见错别字。
- 前后矛盾数值，例如同段脉搏/心率冲突时不得静默选值。

硬约束：

- 不得静默修正 OCR。
- 不得改写数值。
- 不得医学换算。
- 不得把否定或不确定表达改成确定阳性。
- 发生 OCR 纠偏时必须输出 `ocr_correction.applied=true`、`raw`、`normalized`、`reason`；没有把握时应降低置信度，并让后续复核和质量规则产生可疑结果。

`section_groups` prompt 仍只要求输出轻量字段：`field_key`、`original_value`、`source_hint`、`evidence_phrase`、`confidence`、`ocr_correction`。不在 prompt 层要求模型输出 `quality_flags`，质量标记仍由后端复核和薄规则生成。

## 前端接入边界

### 任务页和审核页

- 任务页只允许选择 `review` 和 `done` 任务进行批量导出。
- 非可导出任务不可选，不由前端重算可导出字段完整性。
- 批量导出成功后下载 zip；失败时展示后端错误消息。
- 审核页重抽取入口必须有确认提示：只复用已保存 OCR 文本，不重新识别图片，不覆盖人工最终值。
- 重抽取成功后展示 `schema_version`、`prompt_version`、`run_id`、`candidate_count`，并引导人工回到审核页确认。

### 手机端上传页

手机端上传页增加文书模板选择控件：

- 展示当前任务模板。
- 选项来自后端 `available_document_types`。
- 上传完成前可切换模板；进入 `processing` 或完成上传后控件禁用。
- 切换失败时展示后端错误；不自行生成或隐藏模板。
- 上传图片和完成上传流程保持不变。

电脑端工作台的新建任务弹窗不增加模板选择。它只展示二维码；任务默认模板由后端决定。

## 测试策略

后端测试先行：

1. `test_export_service.py`
   - 批量 zip 包含每个任务 JSON 和根目录 `manifest.json`。
   - manifest 记录任务数、成功任务、字段数、schema/document 元数据和 JSON 路径。
   - 非 `review/done` 任务导致整体失败，错误 details 包含失败任务摘要，且不写 zip、不记录导出。

2. `test_export_routes.py`
   - 批量 zip 下载响应仍为 `application/zip`，压缩包内可读取 manifest。
   - 空 `task_ids` 和非法 `task_ids` 继续返回参数错误。

3. `test_copd_prompts.py`
   - `build_section_group_extraction_prompt()` 包含完整 OCR 风险提示关键词。
   - prompt 明确要求 OCR 纠偏审计，并包含前后矛盾数值不得静默选值的约束。

4. `test_reextraction_service.py`
   - 重抽取 run 审计记录保存 `source=ocr_text_only`、`schema_version`、`prompt_version`、`run_id`、`candidate_count`。
   - 缺少 OCR 文本仍返回 `REEXTRACTION_VALIDATION_FAILED`。

5. `test_schema_service.py` / 新增 profile registry 测试
   - 可按 `document_type` 返回 schema。
   - 可列出手机端模板选项。
   - 未注册 `document_type` 返回校验错误。

6. `test_mobile_upload_routes.py`
   - 上传状态响应包含当前 `document_type` 和可用模板列表。
   - `PATCH /api/mobile-upload/{task_id}/document-type` 校验 token，允许 `uploading` 任务修改模板。
   - 非 `uploading` 任务拒绝修改模板。
   - 修改成功后更新后端 `last_document_type`。

7. `test_orchestrator.py` / `test_copd_field_port.py`
   - 字段抽取输入包含任务 `document_type`。
   - registry 根据 `document_type` 选择 schema、prompt 和 field port。
   - 未注册文书类型进入 `failed`，不回退到 COPD extractor。

8. 前端手机端组件测试
   - 手机上传页加载并展示模板选择。
   - 切换模板调用后端接口并更新当前显示。
   - 上传完成后模板选择禁用。

## 验收标准

- 批量导出成功 zip 内包含 `manifest.json`，且 manifest 与实际 JSON 文件一致。
- 批量导出遇到不可导出任务时整体失败，错误响应能定位失败任务和原因。
- 成功批量导出只记录 `batch_zip` 导出摘要，不改变任务状态。
- `section_groups` prompt 覆盖本 spec 的 OCR 风险提示和硬约束。
- 重抽取仍不调用 OCR/图片处理端口，不覆盖人工审核结果，返回和审计版本元数据。
- 新建任务默认使用后端 `last_document_type`，无历史值时使用 `copd_admission_record`。
- 手机端上传页可选择任务模板，选择结果保存到任务 `document_type`，并更新下一任务默认模板。
- 任务进入 `processing` 后模板锁定，不能再修改。
- 字段抽取和重抽取按任务 `document_type` 选择 schema、prompt 和抽取规则；未注册文书类型不能静默回退。
- 电脑端新建任务弹窗不出现模板选择控件。
