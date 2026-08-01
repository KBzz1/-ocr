# 批量 Excel 导出（一键全部导出到同一张表）设计

## 背景

当前批量导出只有 JSON zip（`POST /api/tasks/export/batch-zip`，任务多选），单任务 Excel 只覆盖单个任务。医生的实际使用场景是：结果累积（可能上千条）后，希望一键把所有审核完成的记录导出到**同一张 Excel 表**里，按固定模板逐行排列，直接在表里人工整理操作。JSON 格式导出保持现状不动。

现状约束：

- 导出服务 `app/backend/services/export_service.py` 已具备单任务 JSON/Excel、批量 JSON zip；xlsx 写入为标准库原始 XML（无第三方依赖），按行追加即可支持千行级。
- 字段体系来自所选记录模板的 schema（`app/config/schemas/qwen_batch_admission_record.v2.yaml`），分组含 主诉 / 现病史 / 既往史 / 个人史 / 家族史 / 体格检查 / 辅助检查 / 诊断；姓名不在 schema 字段里，来自任务的患者元数据（`patient.name`）。
- 后续会新增其他记录模板，本次只做入院记录，但设计必须预留"导出时选择模板"。

### 现状核对结论（修改前核对）

- **字段确认逻辑**（`app/backend/enums.py`、`app/backend/services/_review_field_factory.py`）：字段状态只有 `UNREVIEWED` / `CONFIRMED` / `MODIFIED` 三种，没有独立 ACCEPTED 状态。已确认字段 = `status ∈ {CONFIRMED, MODIFIED}`；`UNREVIEWED` + 非空 `final_value` = 未确认但有值；`UNREVIEWED` + 空 `final_value` = 占位字段（无内容）。**现有模型可以区分已确认与未确认字段，无需发明新字段状态。**
- **阻断判定**（`is_field_blocking`）：仅 `UNREVIEWED` + 非空 `final_value` 视为未确认。批量导出不再用"存在未确认字段即跳过任务"的任务级判定，改为字段级规则（见"字段级导出规则"）。
- **错误码**（`app/backend/errors.py`）：复用 `INVALID_REQUEST_PARAMS`(400) / `EXPORT_VALIDATION_FAILED`(400) / `EXPORT_FAILED`(500)，不新增。
- **导出记录**（`task_service.record_export` / `_update_export_summary`）：按 format 更新 `export_summary.files`，同一 format 只保留最新 `relative_path`，不构成历史档案；文件不可变必须靠每次导出生成唯一路径保证。
- **任务模型排序字段**：`task_id` 为递增数字字符串（`_next_task_id` 生成），现有任务列表按 `int(task_id)` 升序排序（`task_service.py`）；`created_at` 为 ISO 时间。稳定排序复用 `int(task_id)` 升序，字段来自现有真实任务模型。
- **模板注册**：`DocumentProfile`（`app/backend/services/document_profiles.py`、`app/backend/__init__.py` 构造）目前只有 `document_type / label / schema / prompt_version / field_port / quality_rule_profile`，**没有导出能力标记**，需要新增显式启用批量 Excel 的字段。

## 范围

- 新增批量 Excel 导出：选择一个**显式启用批量 Excel 能力**的记录模板，把该模板全部 `review` / `done` 任务按字段级规则导出到同一个 xlsx 文件，一行一条记录，固定可见列模板。
- 新增前端入口：任务列表页"全部导出 Excel"按钮 → 单选模板弹窗（只列启用模板）→ 生成 → 下载。
- JSON 导出（单任务 JSON、批量 JSON zip）完全不动；单任务 Excel 导出完全不动。
- 不引入第三方 Excel 依赖，继续用标准库写 xlsx。

## 表格结构

固定可见 8 列（序号 + 7 模块），隐藏第 9 列"任务编号"，一行一条记录，所有记录在同一张 sheet：

| 序号 | 姓名 | 主诉 | 新病史 | 既往史 | 个人史 | 家族史 | 体格检查 | ~~任务编号~~ |
|---|---|---|---|---|---|---|---|---|
| 1 | 张三 | 反复咳嗽咳痰 | 初次发病情况：…\n后续发病情况：… | 高血压：…\n手术史：… | 吸烟史：… | 父亲慢阻肺 | 体温：36.5℃\n血压：… | 20260801-01 |

- **序号**：1, 2, 3… 按导出顺序编号（可见第 1 列）。
- **姓名**：任务的患者姓名（`patient.name`）；无患者名则单元格留空。
- **可见列名固定**：主诉 / 新病史 / 既往史 / 个人史 / 家族史 / 体格检查。其中"新病史"为医生习惯列名，内容取模板 schema 的 `history_of_present_illness` 分组（现病史）。
- **隐藏列"任务编号"**：可见列保持不变，在同一 sheet 末尾增加隐藏列（列宽 0 + hidden），单元格写入 `task_id`，用于结果回查；表头"任务编号"。
- **模块列映射固定**：`chief_complaint` / `history_of_present_illness` / `past_history` / `personal_history` / `family_history` / `physical_exam`；模板 schema 缺某分组时该列全部留空（多退少补，列结构不变）。
- 单元格启用自动换行（wrapText），保证多行内容在 Excel 中可见；设置合理列宽。

## 字段级导出规则

候选任务 = `status ∈ {review, done}` 且 `task.document_type == 所选模板`。不再做任务级"存在未确认字段即跳过"：

- **只写已确认字段**：模块单元格只写入 `status ∈ {CONFIRMED, MODIFIED}` 且 `final_value` 非空的字段。
  - 单字段组（主诉、家族史）：该字段已确认 → 直接写值（不重复标签，列头已是模块名）；未确认 → 该列留空。
  - 多字段组（新病史、既往史、个人史、体格检查）：已确认的非空字段每行一条 `标签：值`，单元格内换行分隔；未确认字段、占位字段（空值）一律不出现。
  - 子字段标签用 schema 中的 `label`（医生可读，无 field_key、无代码格式）。
- **跳过任务**：仅当**目标模块中没有任何字段完成确认**（即所有固定模块列都无内容可写）时跳过该任务，记录 `{task_id, reason}`，不影响其他行。部分模块有内容的任务正常导出，未确认模块列留空。
- 字段状态判断复用现有 `FieldStatus` 枚举与 `review_result.json` 中的 `status`，不发明新状态。

## 后端

### 接口

1. `POST /api/tasks/export/batch-excel`，body 必传 `{ document_type: string }`。
   - `document_type` 缺失/非法 → `INVALID_REQUEST_PARAMS`。
   - 模板未注册、未接入或**未显式启用批量 Excel** → `EXPORT_VALIDATION_FAILED`（"文书模板未注册或未完成接入，无法导出"）。
   - 该模板没有任何候选任务（`review` / `done` 且模板匹配）→ `EXPORT_VALIDATION_FAILED`（"没有可导出的记录"）。
   - 所有候选任务都被跳过（无一行可导出）→ `EXPORT_VALIDATION_FAILED`（"没有可导出的记录"）。
   - 成功 → 返回 JSON 报告（不直接返回文件），**文件通过下载接口获取**：
     ```json
     {
       "format": "batch_excel",
       "export_id": "…",
       "filename": "batch-<export_id>.xlsx",
       "download_url": "/api/tasks/export/batch-excel/<export_id>",
       "candidate_count": 1000,
       "exported_count": 998,
       "skipped_count": 2,
       "skipped": [{"task_id": "…", "reason": "…"}]
     }
     ```
2. `GET /api/tasks/export/batch-excel/<export_id>`：按 export_id 返回对应 xlsx 文件（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`）；export_id 未知 → 404。报告与下载分离，不在响应头携带 skipped 列表。
3. `GET /api/tasks/export/batch-excel/templates`：返回**显式启用批量 Excel** 的模板列表（`[{document_type, label}]`），供前端弹窗使用；未启用的模板不出现。

### 服务

`ExportService` 新增 `export_batch_excel(document_type)`：

1. 取所选模板 profile 并校验已启用批量 Excel（复用 `DocumentProfileRegistry.get_profile` + 新增启用标记）。
2. 遍历全部任务，筛出候选任务（`status ∈ {review, done}` 且模板匹配），按 `int(task_id)` 升序稳定排序。
3. 逐任务读 `results/{task_id}/review_result.json`，复用 `_build_export_model` / `_build_schema_view` 取字段（顺序与 schema 一致、占位字段不阻断）。
4. **字段级跳过**（见上节）：目标模块无任何确认字段 → 跳过并记 reason；单任务结果缺失 / JSON 损坏 / 契约非法（如模板未注册、review 结构非法）→ 跳过该任务并记原因，**不静默漏任务**。
5. 其余任务生成一行固定模板数据（含隐藏 task_id 列），追加写入 xlsx。
6. **唯一文件与原子写**：每次导出生成唯一 `export_id`（标准库 uuid hex）与唯一文件路径 `exports/batch/batch-<export_id>.xlsx`；先写同目录临时文件，全部写入成功后 `os.replace` 原子重命名；写入失败删除临时文件并抛 `EXPORT_FAILED`（不留下半成品、不产出部分文件）。**不再覆盖固定文件，旧文件保留。**
7. 返回 JSON 报告（candidate_count / exported_count / skipped_count / skipped / download_url），并对每个成功导出的任务 `record_export(format="batch_excel", relative_path="batch/batch-<export_id>.xlsx")`——路径指向本次不可变文件，历史记录不会指向被覆盖的内容。
8. 计数约束：`candidate_count == exported_count + skipped_count`。

### xlsx 写入

- 新增 `_write_batch_xlsx(path, rows)` 写入器，沿用现有标准库原始 XML 方式，单 sheet、逐行追加；千行级（1000 行 × 9 列）无内存压力。
- 为多行显示补充最小 `styles.xml`（wrapText 样式）与列宽定义；隐藏列通过 `<cols>` 定义（hidden + 宽度 0）；`[Content_Types].xml`、`_rels`、`workbook` 关系与现有写入器同构。
- 复用现有 `_serialize_evidence_for_excel` 等工具逻辑；单元格只写字符串。

### 模板启用机制

- `DocumentProfile` 新增显式启用标记（如 `batch_excel_enabled: bool = False`），入院记录 profile 构造时显式开启（`app/backend/__init__.py`）。
- `DocumentProfileRegistry` 新增"仅返回启用批量 Excel 的模板"的查询方法，供 `templates` 接口使用。
- 模板注册 ≠ 支持批量 Excel：未启用模板在生成接口报错、在前端模板列表不出现，避免未来新增模板后自动生成空表。

### 错误码

复用现有错误码，不新增：`INVALID_REQUEST_PARAMS`、`EXPORT_VALIDATION_FAILED`、`EXPORT_FAILED`。错误码文档 `docs/Shared/error-codes.md` 如有对应描述缺口，同步补充。

## 前端

任务列表页（`app/frontend/src/pages/tasks/`）：

1. 工具栏新增"全部导出 Excel"按钮（与现有批量 zip 导出并排）。
2. 点击 → 弹窗：单选记录模板，列表来自 `GET /api/tasks/export/batch-excel/templates`（目前唯一启用项"入院记录"，默认选中），确认 / 取消。
3. 确认 → 调 `POST /api/tasks/export/batch-excel {document_type}` → 拿 JSON 报告 → 再按 `download_url` 下载 xlsx。
4. 成功提示："已导出 N 条，跳过 M 条"；M > 0 时展示跳过明细，每条为"任务编号 + 跳过原因"（直接取自报告 `skipped`，不额外请求）；M = 0 时不展示明细。
5. 失败提示：按错误码展示后端消息（模板未接入 / 没有可导出的记录 / 导出失败）。
6. 请求期间按钮禁用，防止重复导出。

API client 新增 `fetchBatchExcelTemplates()`、`exportTasksBatchExcel(documentType)`、`downloadBatchExcel(exportId)`（`app/frontend/src/api/export.ts`）。

## 测试

### 后端单测（`app/backend/tests/test_export_service.py`）

- 固定可见列 + 序号列 + 隐藏"任务编号"列：表头与列顺序正确；隐藏列存在（cols 定义 hidden）且单元格内容为 `task_id`。
- 字段级规则：
  - 同一任务同时包含已确认和未确认字段 → 只写已确认字段（未确认有值字段不出现），任务不跳过；
  - 单字段组未确认 → 该列留空、任务不跳过；
  - 所有固定模块均无确认字段 → 任务跳过且报告 reason；
  - 空字段不出行、整模块无内容单元格留空。
- 模块内容：多字段组"标签：值"换行、单字段组只写值、姓名来自患者元数据、无患者名留空。
- 跳过与异常：单任务结果缺失 / JSON 损坏 / 契约非法 → 跳过并带 reason，其余任务正常导出；**所有候选任务都被跳过** → `EXPORT_VALIDATION_FAILED`；文件写入失败 → `EXPORT_FAILED` 且不产出部分文件。
- 模板与计数：只导出所选模板任务；模板未注册 / 未启用 batch_excel → `EXPORT_VALIDATION_FAILED`；`candidate_count == exported_count + skipped_count`。
- 排序与唯一性：按 `int(task_id)` 升序稳定（同批数据重复导出顺序一致）；**两次导出生成不同 export_id 与文件路径，互不覆盖，两文件均可独立解析**。
- xlsx 结构可解析：zipfile 校验包结构与单元格 XML 文本断言（含换行、隐藏列定义）。
- 千行冒烟：构造 1000 个可导出任务，导出成功且行数、计数正确。
- 现有 JSON zip / 单任务导出行为不变（现有测试保持通过）。

### 契约测试（`app/backend/tests/test_api_contracts.py`）

- 生成接口：参数校验（缺 document_type）、模板未注册 / 未启用错误码、全跳过错误码、成功返回 JSON 报告（含 download_url）。
- **下载接口**：按报告 download_url 可下载且文件头正确；未知 export_id → 404。
- 模板列表接口：只返回启用批量 Excel 的模板。

### 前端测试（`app/frontend/tests/`）

- 组件测试：按钮 → 弹窗（模板列表只含启用项）→ 生成请求 → 按 download_url 下载；成功提示；跳过明细展示（M>0）；失败提示；请求中禁用。
- 现有任务页测试保持通过（多选批量 zip 入口不受影响）。

## 边界（不做）

- 不做多模板混合导出（一张表只导一个模板）。
- 不做导出前复杂质控流程 / 完整性预警面板（PRD 后置项）。
- 不引入独立 `exported` 状态；不发明新字段状态。
- 不引入第三方 Excel 依赖，不在前端拼 Excel。
- 不改 JSON 导出、单任务 Excel 导出、批量 zip 行为。
- 模块列映射（group_key → 列名）当前为固定配置，不随模板动态增减列。
- 旧导出文件不自动清理（历史导出记录可能引用），由后续维护策略处理。
