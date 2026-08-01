# 批量 Excel 导出（一键全部导出到同一张表）设计

## 背景

当前批量导出只有 JSON zip（`POST /api/tasks/export/batch-zip`，任务多选），单任务 Excel 只覆盖单个任务。医生的实际使用场景是：结果累积（可能上千条）后，希望一键把所有审核完成的记录导出到**同一个 Excel 表**里，按固定模板逐行排列，直接在表里人工整理操作。JSON 格式导出保持现状不动。

现状约束：

- 导出服务 `app/backend/services/export_service.py` 已具备单任务 JSON/Excel、批量 JSON zip；xlsx 写入为标准库原始 XML（无第三方依赖），按行追加即可支持千行级。
- 字段体系来自所选记录模板的 schema（`app/config/schemas/qwen_batch_admission_record.v2.yaml`），分组含 主诉 / 现病史 / 既往史 / 个人史 / 家族史 / 体格检查 / 辅助检查 / 诊断；姓名不在 schema 字段里，来自任务的患者元数据（`patient.name`）。
- 后续会新增其他记录模板，本次只做入院记录，但设计必须预留"导出时选择模板"。

## 范围

- 新增批量 Excel 导出：选择一个记录模板，把该模板全部 `review` / `done` 任务导出到同一个 xlsx 文件，一行一条记录，固定 7 列模板。
- 新增前端入口：任务列表页"全部导出 Excel"按钮 → 单选模板弹窗 → 下载与结果提示。
- JSON 导出（单任务 JSON、批量 JSON zip）完全不动。
- 单任务 Excel 导出完全不动。
- 不引入第三方 Excel 依赖，继续用标准库写 xlsx。

## 表格结构

固定 7 列（加序号 8 列），一行一条记录，所有记录在同一张表（sheet）：

| 序号 | 姓名 | 主诉 | 新病史 | 既往史 | 个人史 | 家族史 | 体格检查 |
|---|---|---|---|---|---|---|---|
| 1 | 张三 | 反复咳嗽咳痰 | 初次发病情况：…\n后续发病情况：… | 高血压：…\n手术史：… | 吸烟史：… | 父亲慢阻肺 | 体温：36.5℃\n血压：… |

- **序号**：1, 2, 3… 按导出顺序编号。
- **姓名**：任务的患者姓名（`patient.name`）；无患者名则单元格留空。
- **列名固定**：主诉 / 新病史 / 既往史 / 个人史 / 家族史 / 体格检查。其中"新病史"为医生习惯列名，内容取模板 schema 的 `history_of_present_illness` 分组（现病史）。
- **模块内容**：按固定 group_key 映射取该模块子字段（`chief_complaint`、`history_of_present_illness`、`past_history`、`personal_history`、`family_history`、`physical_exam`），取人工审核后的 `final_value`：
  - 单字段组（主诉、家族史）：直接写值，不重复标签（列头已是模块名）。
  - 多字段组（新病史、既往史、个人史、体格检查）：`final_value` 非空的子字段每行一条 `标签：值`，单元格内换行分隔。
  - 空字段（无 final_value）不出现；整个模块无内容时单元格留空。
  - 子字段标签用 schema 中的 `label`（医生可读，无 field_key、无代码格式）。
- **模板缺失分组**：所选模板 schema 缺某个固定分组时，该列全部留空（多退少补，列结构不变）。
- 单元格启用自动换行（wrapText），保证多行内容在 Excel 中可见；设置合理列宽。

## 后端

### 接口

`POST /api/tasks/export/batch-excel`，body 必传 `{ document_type: string }`。

- `document_type` 缺失/非法 → `INVALID_REQUEST_PARAMS`。
- 模板未注册或未接入 → `EXPORT_VALIDATION_FAILED`（提示"文书模板未注册或未完成接入"）。
- 该模板没有任何 `review` / `done` 任务 → `EXPORT_VALIDATION_FAILED`（提示"没有可导出的记录"）。
- 成功 → 返回 xlsx 文件（`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`），文件名 `batch-review-export.xlsx`。
- 失败不影响审核数据。

### 服务

`ExportService` 新增 `export_batch_excel(document_type)`：

1. 取所选模板 schema（复用 `DocumentProfileRegistry.get_profile`）。
2. 遍历全部任务，筛出 `status ∈ {review, done}` 且 `task.document_type == 所选模板`。
3. 每任务读 `results/{task_id}/review_result.json`，复用 `_build_export_model` / `_build_schema_view` 取字段（顺序与 schema 一致、占位字段不阻断）。
4. **跳过规则**：任务存在未确认字段（`is_field_blocking`）→ 跳过该任务，记录 `{task_id, reason: "存在未确认字段，未通过导出检查"}`，不影响其他行。
5. 其余任务生成一行固定模板数据，追加写入 xlsx。
6. 文件固定写 `exports/batch/batch-review-export.xlsx`，**覆盖式**（多次导出是同一个表）；文件目录与现有 batch zip 一致（`exports/batch/`）。
7. 返回 `{ filename, relative_path, row_count, skipped: [{task_id, reason}] }`；对每个成功导出的任务 `record_export(format="batch_excel", relative_path=...)`，与 batch-zip 的逐任务记录方式对齐。

### xlsx 写入

- 新增 `_write_batch_xlsx(path, rows)` 写入器，沿用现有标准库原始 XML 方式，单 sheet、逐行追加；千行级（1000 行 × 8 列）无内存压力。
- 为多行显示补充最小 `styles.xml`（wrapText 样式）与列宽定义；`[Content_Types].xml`、`_rels`、`workbook` 关系与现有写入器同构。
- 复用现有 `_serialize_evidence_for_excel` 等工具逻辑；单元格只写字符串。

### 错误码

复用现有错误码，不新增：`INVALID_REQUEST_PARAMS`、`EXPORT_VALIDATION_FAILED`、`EXPORT_FAILED`。错误码文档 `docs/Shared/error-codes.md` 如有对应描述缺口，同步补充。

## 前端

任务列表页（`app/frontend/src/pages/tasks/`）：

1. 工具栏新增"全部导出 Excel"按钮（与现有批量 zip 导出并排）。
2. 点击 → 弹窗：单选记录模板（列表来自现有可用模板接口，目前唯一选项"入院记录"，默认选中），确认 / 取消。
3. 确认 → 调 `POST /api/tasks/export/batch-excel {document_type}` → 浏览器下载 xlsx。
4. 成功提示："已导出 N 条，跳过 M 条"；M > 0 时展示跳过明细，每条为"任务编号 + 跳过原因"（如"任务 20260801-03：存在未确认字段，未通过导出检查"）；M = 0 时不展示明细。跳过明细直接取自后端报告，不额外请求。
5. 失败提示：按错误码展示后端消息（模板未接入 / 没有可导出的记录 / 导出失败）。
6. 请求期间按钮禁用，防止重复导出。

API client 新增 `exportTasksBatchExcel(documentType)`（`app/frontend/src/api/export.ts`），返回 blob 与导出报告。

## 测试

### 后端单测（`app/backend/tests/test_export_service.py`）

- 固定 7 列 + 序号列，表头与列顺序正确。
- 模块内容：多字段组"标签：值"换行、单字段组只写值、空字段不出行、整模块无内容单元格留空。
- 姓名来自患者元数据，无患者名留空。
- 跳过规则：存在未确认字段的任务被跳过且报告 reason，其余任务正常导出。
- 模板筛选：只导出所选模板任务；模板未注册报错；模板无 review/done 任务报错。
- xlsx 结构可解析：zipfile 校验包结构与单元格 XML 文本断言（含换行）。
- 千行冒烟：构造 1000 个可导出任务，导出成功且行数正确。
- JSON zip / 单任务导出行为不变（现有测试保持通过）。

### 契约测试（`app/backend/tests/test_api_contracts.py`）

- batch-excel 接口：参数校验（缺 document_type）、错误码映射、成功下载与文件头。

### 前端测试（`app/frontend/tests/`）

- 组件测试：按钮 → 弹窗 → 单选模板 → 请求 → 下载触发；成功提示；跳过明细展示（M>0）；失败提示；请求中禁用。

## 边界（不做）

- 不做多模板混合导出（一张表只导一个模板）。
- 不做导出前复杂质控流程 / 完整性预警面板（PRD 后置项）。
- 不引入独立 `exported` 状态。
- 不引入第三方 Excel 依赖，不在前端拼 Excel。
- 不改 JSON 导出、单任务 Excel 导出、批量 zip 行为。
- 模块列映射（group_key → 列名）当前为固定配置，不随模板动态增减列。
