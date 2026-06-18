# 批量导出、重抽取与文书模板 P2 设计

## 背景

`2026-05-29-batch-export-reextract-design.md` 已完成批量 JSON zip 导出和基于已保存 OCR 文本重抽取的后端框架，前端也已有对应 API client。下一阶段补齐批量导出审计、重抽取元数据、默认抽取策略风险提示，并为多记录类型抽取建立任务级 `document_type` 基础：

- 批量 zip 需要可审计的导出清单，便于离线验收和现场排障。
- OCR 文本重抽取需要给前端返回足够的运行元数据，支持审核页展示本次运行信息。
- 当前默认 `section_groups` 抽取策略的 prompt 已有 OCR 风险提示，但相比字段批量 prompt 缺少部分高风险项，需要补齐，避免默认策略下对单位符号、表格错位、冒号/空格丢失、常见错别字、药名纠偏、矛盾数值等风险提示不足。
- 系统后续会支持多种记录类型，例如慢阻肺/呼吸系统入院记录、病程记录等。每个任务只对应一种记录类型，字段抽取必须按任务的 `document_type` 选择 schema、prompt 和抽取规则。
- 患者中心落地后，电脑端新建任务弹窗负责选择患者、记录类型、记录日期和可选时间；手机端只负责上传图片并只读展示记录类型。

本阶段不做同一任务内多文书混合拆分，也不做 OCR 自动判断文书类型。

## 目标

1. 批量 zip 根目录增加 `manifest.json`，记录导出摘要、成功任务清单和失败任务清单。
2. 批量导出保持当前原子性：任一任务不可导出时整体失败，不生成部分成功 zip，不修改审核数据。
3. 重抽取接口保持 `ocr_text_only` 语义，不重新跑 OCR，不重新处理图片；成功时直接覆盖审核字段并将字段状态重置为 `unreviewed`。
4. `section_groups` prompt 补齐 OCR 风险提示和硬约束，与默认运行策略承担的风险相匹配。
5. 为后续前端 UI 提供稳定字段：批量导出可下载 zip；重抽取可展示 `schema_version`、`prompt_version`、`source`、`run_id`、`candidate_count`。
6. 每个任务持久化 `document_type`，任务处理和重抽取按 `document_type` 选择 schema、prompt 和抽取规则。
7. 电脑端新建任务必须提交 `patient_id`、`document_type`、`record_date` 和可选 `record_time`；手机端不允许修改记录类型。
8. 任务进入 `processing` 后，患者、记录类型和记录时间修改必须受任务状态与重抽取并发保护约束。

## 非目标

- 不做批量 Excel 或汇总 Excel。
- 不引入独立 `exported` 状态。
- 不做部分成功下载；本阶段 manifest 中的失败清单用于失败前校验报告和未来扩展，不改变整体失败语义。
- 不做前端字段推断、OCR 文本解析或 schema 侧字段补造。
- 不做重抽取结果逐字段采用、保留或 diff UI。
- 不扩展为通用医学规则引擎。
- 不从 OCR 文本、图片内容或文件名自动判断文书类型。
- 不支持同一任务中混合多种文书模板分别抽取。
- 病程记录等新模板的完整字段 schema、prompt 和规则可后续逐个接入。

## 后端设计

### 文书模板与 document_type

任务记录必须稳定包含：

- `document_type`：任务级文书模板类型，例如 `copd_admission_record`。
- `schema_version`：本任务处理使用的 schema 版本。
- `prompt_version`：本任务字段抽取使用的 prompt 版本。若当前 task 结构暂不记录，也必须在字段候选 metadata、重抽取 run 和导出 manifest 中可追溯。
- `extraction_profile`：可选，表示后端选择的抽取 profile；第一版可与 `document_type` 同名。

创建任务时，后端必须接收并校验 `patient_id`、`document_type`、`record_date` 和可选 `record_time`。`document_type` 必须来自已注册 profile；任务保存 `document_type_label`、`schema_version`、`prompt_version` 和 `extraction_profile` 摘要。

`uploading` 阶段允许通过任务元数据接口修改 `document_type`。任务进入 `processing` 后不允许修改患者、记录类型或记录时间。`review` / `done` 阶段修改 `document_type` 时，后端复用已保存 OCR 文本重新执行字段抽取，不重新跑 OCR；缺少成功 `document_result.json`、目标类型未注册或存在进行中的重抽取任务时拒绝修改。

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

第一版 registry 只必须注册当前已实现的 `copd_admission_record`。后续新增病程记录时，通过新增 profile、schema、prompt builder 和抽取器接入，不改任务生命周期主流程。电脑端可选记录类型只能暴露已经完成注册且具备 schema/prompt/field port 的 profile；未接入抽取能力的模板不得出现在可选项中。

`SchemaService` 需要从“只返回当前 schema”扩展为按 `document_type` 取 schema：

- `get_schema(document_type)`：返回指定文书类型 schema。
- `get_available_document_types()`：返回电脑端新建任务弹窗可展示的记录类型列表，包含 `document_type`、`label`、`schema_version`。
- `get_default_document_type()`：返回后端兜底默认值，仅用于开发兼容；正式创建任务仍要求前端提交 `document_type`。

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

### 手机端上传状态 API

手机端上传页需要一个只读后端能力：

1. 获取当前任务上传状态和记录类型摘要：

```http
GET /api/mobile-upload/{task_id}?token=...
```

响应在现有上传状态基础上包含任务记录类型摘要：

```json
{
  "task_id": "task_001",
  "status": "uploading",
  "document_type": "copd_admission_record",
  "document_type_label": "入院记录",
  "page_count": 0,
  "images": []
}
```

约束：

- 必须校验上传 token。
- 手机端不提供修改记录类型的 API；`PATCH /api/mobile-upload/{task_id}/document-type` 返回 404。
- 手机端只读展示 `document_type_label`，不根据图片、文件名或 OCR 推断模板。

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

服务继续写入审计文件：

- `results/{task_id}/field_candidates.json`
- `results/{task_id}/reextract_runs/{run_id}.json`

审计记录中应至少包含上述返回字段、`created_at` 和候选数量。不得保存完整模型输出到日志事件。

重抽取必须使用任务当前 `document_type` 对应的 schema、prompt 和抽取规则。若任务缺少 `document_type`，按兼容策略视为 `copd_admission_record` 并回写任务记录；若 `document_type` 未注册，返回 `REEXTRACTION_VALIDATION_FAILED`，不得回退到 COPD prompt。

重抽取成功后，新候选直接覆盖 `review_result.json["fields"]` 中对应 schema 字段，字段状态重置为 `unreviewed`，字段 `history` 追加 `reextract` 记录。任务为 `done` 时回退到 `review`。缺少 OCR 文本、候选为空、候选契约非法或字段端口失败时不修改审核结果。

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
- 审核页重抽取入口直接触发后端重抽取；界面不展示免责文案，不做结果对比与采用 UI。
- 重抽取成功后展示 `schema_version`、`prompt_version`、`run_id`、`candidate_count`，并引导人工回到审核页确认。

### 手机端上传页

手机端上传页只读展示任务记录类型：

- 展示当前任务的 `document_type_label`。
- 不展示模板选择控件。
- 不调用 `PATCH /api/mobile-upload/{task_id}/document-type`。
- 上传图片和完成上传流程保持不变。

电脑端工作台的新建任务弹窗负责选择患者、记录类型、记录日期和可选时间，提交后才展示二维码。

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
   - 上传状态响应包含当前 `document_type`、`document_type_label` 和 `schema_version`。
   - `PATCH /api/mobile-upload/{task_id}/document-type` 返回 404。
   - 手机端上传状态只读展示 `document_type_label`。

7. `test_orchestrator.py` / `test_copd_field_port.py`
   - 字段抽取输入包含任务 `document_type`。
   - registry 根据 `document_type` 选择 schema、prompt 和 field port。
   - 未注册文书类型进入 `failed`，不回退到 COPD extractor。

8. 前端手机端组件测试
   - 手机上传页加载并只读展示记录类型。
   - 手机端不渲染模板选择控件。
   - 手机端上传和完成上传流程保持不变。

## 验收标准

- 批量导出成功 zip 内包含 `manifest.json`，且 manifest 与实际 JSON 文件一致。
- 批量导出遇到不可导出任务时整体失败，错误响应能定位失败任务和原因。
- 成功批量导出只记录 `batch_zip` 导出摘要，不改变任务状态。
- `section_groups` prompt 覆盖本 spec 的 OCR 风险提示和硬约束。
- 重抽取仍不调用 OCR/图片处理端口；成功后直接覆盖审核字段并返回、审计版本元数据。
- 新建任务由电脑端提交患者、记录类型、记录日期和可选时间。
- 手机端上传页只读展示任务记录类型，不能修改 `document_type`。
- 任务进入 `processing` 后记录类型锁定；`review` / `done` 修改记录类型必须复用已保存 OCR 文本重新抽取并受并发保护。
- 字段抽取和重抽取按任务 `document_type` 选择 schema、prompt 和抽取规则；未注册文书类型不能静默回退。
