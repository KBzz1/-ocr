# 后端批量导出与重抽取 P2 设计

## 背景

`2026-05-29-batch-export-reextract-design.md` 已完成批量 JSON zip 导出和基于已保存 OCR 文本重抽取的后端框架，前端也已有对应 API client。下一阶段先补后端能力，再接前端 UI：

- 批量 zip 需要可审计的导出清单，便于离线验收和现场排障。
- OCR 文本重抽取需要给前端返回足够的运行元数据，支持后续确认入口和结果对比。
- 当前默认 `section_groups` 抽取策略的 prompt 已有 OCR 风险提示，但相比字段批量 prompt 缺少部分高风险项，需要补齐，避免默认策略下对单位符号、表格错位、冒号/空格丢失、常见错别字、药名纠偏、矛盾数值等风险提示不足。

本阶段按“后端先行”推进。前端完整多选、下载反馈和重抽取确认入口在后端契约稳定后接入。

## 目标

1. 批量 zip 根目录增加 `manifest.json`，记录导出摘要、成功任务清单和失败任务清单。
2. 批量导出保持当前原子性：任一任务不可导出时整体失败，不生成部分成功 zip，不修改审核数据。
3. 重抽取接口保持 `ocr_text_only` 语义，不重新跑 OCR，不重新处理图片，不覆盖人工最终值。
4. `section_groups` prompt 补齐 OCR 风险提示和硬约束，与默认运行策略承担的风险相匹配。
5. 为后续前端 UI 提供稳定字段：批量导出可下载 zip；重抽取可展示 `schema_version`、`prompt_version`、`source`、`run_id`、`candidate_count`。

## 非目标

- 不做批量 Excel 或汇总 Excel。
- 不引入独立 `exported` 状态。
- 不做部分成功下载；本阶段 manifest 中的失败清单用于失败前校验报告和未来扩展，不改变整体失败语义。
- 不做前端字段推断、OCR 文本解析或 schema 侧字段补造。
- 不做重抽取结果逐字段采用；该能力后续单独设计。
- 不扩展为通用医学规则引擎。

## 后端设计

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

## 前端后续接入边界

后端本阶段完成后，前端按现有 API client 接入：

- 任务页只允许选择 `review` 和 `done` 任务进行批量导出。
- 非可导出任务不可选，不由前端重算可导出字段完整性。
- 批量导出成功后下载 zip；失败时展示后端错误消息。
- 审核页重抽取入口必须有确认提示：只复用已保存 OCR 文本，不重新识别图片，不覆盖人工最终值。
- 重抽取成功后展示 `schema_version`、`prompt_version`、`run_id`、`candidate_count`，并引导人工回到审核页确认。

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

## 验收标准

- 批量导出成功 zip 内包含 `manifest.json`，且 manifest 与实际 JSON 文件一致。
- 批量导出遇到不可导出任务时整体失败，错误响应能定位失败任务和原因。
- 成功批量导出只记录 `batch_zip` 导出摘要，不改变任务状态。
- `section_groups` prompt 覆盖本 spec 的 OCR 风险提示和硬约束。
- 重抽取仍不调用 OCR/图片处理端口，不覆盖人工审核结果，返回和审计版本元数据。
