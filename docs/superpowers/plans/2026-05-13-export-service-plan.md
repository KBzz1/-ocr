# BE-08 导出服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 BE-08 导出前检查、JSON 导出、Excel 导出和任务导出状态记录，让已确认的人工审核结果可以本地下载，且导出内容只来自 `review_result.fields[].final_value`。

**Architecture:** 新增 `ExportService` 负责读取 task/review/schema、构建统一导出模型、写入 `exports/{task_id}/`；新增 `routes/export.py` 暴露三个只读下载/检查 endpoint；扩展 `TaskService.mark_exported()` 记录 `export_summary`，保持现有调用兼容。

**Tech Stack:** Flask、标准库 `json`/`zipfile`/`xml.sax.saxutils`、现有 `JsonStore`、`SchemaService`、`TaskService`、pytest。不得新增依赖，不得联网安装 Excel 库。

---

## Task 0: 基线和依赖确认

- [ ] 阅读 `AGENTS.md`、`docs/AGENTS.md`、本 spec、`docs/Backend/Backend_TDD/10-export-service.md`、`docs/Backend/Backend_BDD/export.md`。
- [ ] 运行基线：

```bash
python -m pytest app/backend/tests -q
python -c "import importlib.util; print(importlib.util.find_spec('openpyxl'))"
```

预期：全量测试通过；第二条只打印依赖探测结果，无论是否安装都不得在实现中依赖 `openpyxl`。

提交：无。

## Task 1: ExportService 校验和导出模型

Files:

- `app/backend/services/export_service.py` NEW
- `app/backend/tests/test_export_service.py` NEW

RED:

- [ ] 新增测试：
  - `test_check_confirmed_task_can_export`
  - `test_check_rejects_ready_for_review_task`
  - `test_check_rejects_missing_review_result`
  - `test_check_blocks_unreviewed_suspicious_and_empty_unaccepted_fields`
  - `test_export_model_uses_final_value_not_auto_value_and_keeps_order`

测试数据直接写入 `tasks/{task_id}.json` 和 `results/{task_id}/review_result.json`。字段至少包含 `auto_value="auto"`、`final_value="manual"`，断言导出模型只含 `manual`。

运行 RED：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

GREEN:

- [ ] 实现 `ExportService.__init__(store, export_dir, task_service, schema_provider=None)`。
- [ ] 实现 `check(task_id)`：
  - 任务不存在抛 `TASK_NOT_FOUND`。
  - 任务状态不是 `confirmed` 或 `exported` 抛 `EXPORT_VALIDATION_FAILED`。
  - review_result 缺失或 `fields` 为空抛 `EXPORT_VALIDATION_FAILED`。
  - 统计 `unreviewed`、`suspicious`、`empty_unaccepted`、`empty`、`missing_evidence`。
- [ ] 实现私有 `_build_export_model(task_id)`，按 review_result 字段顺序构建模型，schema 只用于补 `field_name`/`group_key`/`group_label`。
- [ ] 不在导出模型中读取或回退 `auto_value`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

提交：

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat: 增加导出服务校验模型"
```

## Task 2: JSON 导出和失败不污染状态

Files:

- `app/backend/services/export_service.py`
- `app/backend/tests/test_export_service.py`

RED:

- [ ] 新增测试：
  - `test_export_json_writes_task_scoped_file`
  - `test_export_json_returns_relative_path_and_download_name`
  - `test_export_json_write_failure_keeps_task_confirmed_and_review_unchanged`

运行 RED：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

GREEN:

- [ ] 实现 `export_json(task_id)`：
  - 调用 `_build_export_model()`。
  - 写入 `exports/{task_id}/{task_id}.review.json`。
  - 返回 `{"format": "json", "path": absolute_path, "relative_path": f"{task_id}/{task_id}.review.json", "filename": ...}`。
  - 成功后调用 `task_service.mark_exported(task_id, format="json", relative_path=...)`。
- [ ] 捕获文件写入异常并抛 `EXPORT_FAILED`，details 只包含 `format` 和简短 `reason`。
- [ ] 不修改 `review_result.json`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

提交：

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat: 实现人工审核 JSON 导出"
```

## Task 3: Excel 导出，不新增依赖

Files:

- `app/backend/services/export_service.py`
- `app/backend/tests/test_export_service.py`

RED:

- [ ] 新增测试：
  - `test_export_excel_writes_valid_xlsx_zip`
  - `test_export_excel_groups_fields_by_schema_group`
  - `test_export_excel_contains_final_value_not_auto_value`

测试用 `zipfile.ZipFile` 读取 xlsx，断言存在：

- `[Content_Types].xml`
- `xl/workbook.xml`
- `xl/worksheets/sheet1.xml`
- `xl/_rels/workbook.xml.rels`

并断言 XML 内容包含组名 sheet、表头、`manual`，不包含 `auto`。

运行 RED：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

GREEN:

- [ ] 在 `ExportService` 内实现私有 `_write_xlsx(path, export_model)`。
- [ ] 使用 `zipfile` 生成最小 xlsx，字符串通过 `xml.sax.saxutils.escape()` 转义。
- [ ] sheet 名限制 31 字符，替换 `[]:*?/\\` 为 `_`；重复组名追加序号。
- [ ] 每行列固定为：字段 key、字段名、final_value、状态、来源页、来源证据。
- [ ] 实现 `export_excel(task_id)`，成功后调用 `mark_exported(format="excel", relative_path=...)`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_export_service.py -q
```

提交：

```bash
git add app/backend/services/export_service.py app/backend/tests/test_export_service.py
git commit -m "feat: 实现人工审核 Excel 导出"
```

## Task 4: TaskService 导出状态摘要

Files:

- `app/backend/services/task_service.py`
- `app/backend/tests/test_task_service.py`

RED:

- [ ] 新增测试：
  - `test_mark_exported_records_export_summary_file`
  - `test_mark_exported_keeps_existing_call_compatible`
  - `test_mark_exported_deduplicates_format_on_repeat_export`

运行 RED：

```bash
python -m pytest app/backend/tests/test_task_service.py -q
```

GREEN:

- [ ] 扩展 `mark_exported(self, task_id, format=None, relative_path=None, task=None)`，所有新增参数有默认值。
- [ ] 允许 `confirmed -> exported`；`exported` 再次调用保持 `exported`。
- [ ] `export_summary.last_exported_at` 更新为当前时间。
- [ ] `formats` 去重追加；`files` 按 format 更新或追加，路径必须是相对 exports 的路径。
- [ ] 不修改 processing、review、cleanup 相关逻辑。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_task_service.py app/backend/tests/test_export_service.py -q
```

提交：

```bash
git add app/backend/services/task_service.py app/backend/tests/test_task_service.py
git commit -m "feat: 记录任务导出摘要"
```

## Task 5: Export API 路由和应用注册

Files:

- `app/backend/routes/export.py` NEW
- `app/backend/routes/__init__.py`
- `app/backend/__init__.py`
- `app/backend/tests/test_export_routes.py` NEW

RED:

- [ ] 新增测试：
  - `test_export_check_route_success`
  - `test_export_check_route_rejects_unconfirmed_task`
  - `test_export_json_route_returns_download_headers`
  - `test_export_excel_route_returns_xlsx_download_headers`
  - `test_export_route_missing_task_returns_task_not_found`

运行 RED：

```bash
python -m pytest app/backend/tests/test_export_routes.py -q
```

GREEN:

- [ ] 在 `routes/__init__.py` 增加 `_get_export_service()`。
- [ ] 在 `create_backend_app()` 创建 `ExportService(store, config["export_dir"], task_service, schema_service.get_current)` 并注册 `export_bp`。
- [ ] `GET /api/tasks/<task_id>/export/check` 返回 `success(data=service.check(task_id))`。
- [ ] JSON/Excel endpoint 调用 service 后用 `send_file(..., as_attachment=True, download_name=...)` 返回文件。
- [ ] Content-Type 分别为 `application/json` 和 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_export_routes.py app/backend/tests/test_export_service.py -q
```

提交：

```bash
git add app/backend/routes/export.py app/backend/routes/__init__.py app/backend/__init__.py app/backend/tests/test_export_routes.py
git commit -m "feat: 暴露人工审核导出 API"
```

## Task 6: 回归和边界检查

- [ ] 运行：

```bash
python -m pytest app/backend/tests -q
rg -n "openpyxl|pip install|requests|http://|https://|auto_value.*final_value" app/backend/services/export_service.py app/backend/routes/export.py app/backend/tests/test_export_service.py app/backend/tests/test_export_routes.py
```

预期：

- pytest 全部通过。
- `openpyxl`、`pip install`、外网请求无命中。
- `auto_value.*final_value` 若命中，只能出现在断言“不要使用 auto_value”的测试语义中。

提交：

```bash
git status --short
```

若有遗漏的测试修正，提交信息用 `test: 补充导出回归验证`。
