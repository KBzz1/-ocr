# 后端 TDD — 患者中心记录归档

> 错误码与状态机见 `docs/Shared/error-codes.md` 和 `docs/Shared/state-enums.md`

## 测试目标

为患者档案、任务归属、记录类型重新处理和逻辑删除提供单元与 API 契约测试。

## 单元 / 服务测试

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-PAT-U-001 | 单元 | `PatientService.create` 生成 `P-` + 8 位大写十六进制并支持重名 | ID 格式漂移或重名冲突 |
| BE-PAT-U-002 | 单元 | 患者编号在 10 字节 hex 空间发生碰撞时自动重试 | 编号冲突导致写入失败 |
| BE-PAT-U-003 | 单元 | `PatientService.list` 隐藏已删除患者；查询空字符串返回全部未删除 | 显示已删除患者 |
| BE-PAT-U-004 | 单元 | `PatientService.rename` 追加 name_history 记录 | 改名不记录历史 |
| BE-PAT-U-005 | 单元 | `PatientService.get_bindable` 对已删除患者抛 PATIENT_DELETED | 已删除患者被误绑 |
| BE-PAT-U-006 | 单元 | `PatientService.to_public` 过滤 `name_history` 字段 | 姓名历史通过公共接口泄露 |
| BE-PAT-U-007 | 单元 | `TaskService.create_uploading_task` 必须接收 `patient_id/document_type/record_date/record_time`，校验日期时间格式，绑定 `patient_snapshot` | 旧接口允许无患者创建 |
| BE-PAT-U-008 | 单元 | 任务 ID 使用所有数字任务 ID（含已逻辑删除）最大值加一，生成后校验文件不存在 | 任务 ID 复用或冲突 |
| BE-PAT-U-009 | 单元 | 日期 `2026-13-45`、`2026-02-30` 与时间 `24:00`、`23:60` 全部拒绝 | 日期时间格式校验不严 |
| BE-PAT-U-010 | 单元 | `TaskService.update_metadata` 在 `processing` 状态抛 INVALID_TASK_TRANSITION | 改绑到 processing 任务 |
| BE-PAT-U-011 | 单元 | `review`/`done` 修改患者或记录时间不修改图片、OCR、审核结果 | 改绑触发重抽 |
| BE-PAT-U-012 | 单元 | `review`/`done` 修改 `document_type` 时进入 processing 且只重抽字段 | 改 document_type 跑 OCR |
| BE-PAT-U-013 | 单元 | 缺少成功 `document_result.json` 时拒绝修改 `document_type` | 改 document_type 但无 OCR 文本 |
| BE-PAT-U-014 | 单元 | `ReextractJobRegistry` 存在 in-flight job 时拒绝修改 `document_type` | 与重抽取并发 |
| BE-PAT-U-015 | 单元 | 修改记录类型前归档 `review_result.json` 到 `record_type_change_archive/{change_id}.json` | 旧 Schema 字段混入新审核 |
| BE-PAT-U-016 | 单元 | `metadata_history` 每项严格等于 `{field, from_value, to_value, changed_at}`，不通过普通任务 API 返回 | 内部字段泄露 |
| BE-PAT-U-017 | 单元 | `TaskService.delete_task` 标记 `deleted_at` 并保留 JSON；不再调用 `CleanupService.cleanup_task` | 物理清理副作用 |
| BE-PAT-U-018 | 单元 | `TaskService.delete_task` 拒绝 `processing` 状态 | processing 任务被误删 |
| BE-PAT-U-019 | 单元 | `_read_task` 默认拒绝已逻辑删除任务；`include_deleted=True` 显式可读 | 已删除任务被普通 API 返回 |
| BE-PAT-U-020 | 单元 | 删除患者时只对 `patient_id` 仍指向该患者且 `deleted_at` 为空的任务刷新 `patient_snapshot` | 误刷新已改绑任务 |
| BE-PAT-U-021 | 单元 | `PatientQueryService.get_detail` 按 `document_type` 分组，按记录日期倒序，同日有时间记录在仅日期记录之前 | 排序错乱 |
| BE-PAT-U-022 | 单元 | `TaskService.list_for_patient` 返回所有未删除任务，不受 `_should_list_task` 隐藏空 `uploading` 规则影响 | 患者详情缺任务 |
| BE-PAT-U-023 | 单元 | `ExportService._build_export_model` 返回 `patient` 与 `record` 元数据 | 导出缺患者元数据 |
| BE-PAT-U-024 | 单元 | Excel 导出固定包含独立"任务信息" sheet，写入患者和记录元数据 | Excel 导出缺元数据 |
| BE-PAT-U-025 | 单元 | 删除患者或任务的事件日志只含 `patient_id`/`task_id`/`error_code`，不记录姓名/OCR/字段值 | 日志泄露患者数据 |

## 路由 / API 契约测试

| ID | 层次 | 行为 | RED 失败点 |
|----|------|------|------------|
| BE-PAT-A-001 | API | `POST /api/patients` 接受 `{name}` 返回 201 与 `patient_id` | 患者创建失败 |
| BE-PAT-A-002 | API | `GET /api/patients?query=` 支持编号精确匹配与姓名包含匹配 | 搜索功能缺失 |
| BE-PAT-A-003 | API | `GET /api/patients/{patient_id}` 返回未删除患者；已删除返回 PATIENT_NOT_FOUND | 删除后仍返回 |
| BE-PAT-A-004 | API | `PATCH /api/patients/{patient_id}` 修改姓名并刷新任务快照 | 改名不传播 |
| BE-PAT-A-005 | API | `DELETE /api/patients/{patient_id}?delete_tasks=false` 保留任务且 GET 任务仍可见并标记患者已删除 | 任务被隐藏 |
| BE-PAT-A-006 | API | `DELETE /api/patients/{patient_id}?delete_tasks=true` 隐藏任务，文件仍存在 | 物理删除副作用 |
| BE-PAT-A-007 | API | `DELETE /api/patients/{patient_id}` 重复删除返回 PATIENT_NOT_FOUND | 重复删除产生副作用 |
| BE-PAT-A-008 | API | `POST /api/tasks` 缺患者/记录类型/记录日期返回 INVALID_REQUEST_PARAMS | 缺参数创建 |
| BE-PAT-A-009 | API | `POST /api/tasks` 对已删除患者返回 PATIENT_DELETED | 已删除患者被创建 |
| BE-PAT-A-010 | API | `PATCH /api/tasks/{task_id}/metadata` 在 `processing` 返回 INVALID_TASK_TRANSITION | 改绑到 processing |
| BE-PAT-A-011 | API | `PATCH /api/tasks/{task_id}/metadata` 修改 `document_type` 触发字段重抽（`doc_port.parse` 调用 0 次，`field_port.extract` 调用 1 次） | 重抽触发 OCR |
| BE-PAT-A-012 | API | 任务列表/详情响应不包含 `metadata_history` | 内部字段泄露 |
| BE-PAT-A-013 | API | 任务管理/审核/导出接口对已逻辑删除任务返回 TASK_NOT_FOUND | 已删除任务被暴露 |
| BE-PAT-A-014 | API | `DELETE /api/tasks/{task_id}` 标记 `deleted_at` 不调用 CleanupService | 物理清理副作用 |
| BE-PAT-A-015 | API | 导出 JSON/Excel/批量 zip 包含 `patient` 与 `record` 字段 | 导出元数据缺失 |
| BE-PAT-A-016 | API | `PATCH /api/mobile-upload/{task_id}/document-type` 返回 404 | 旧路由未下线 |

## Fixture

- 复用 `app/backend/tests/fixtures/client.py::make_client`
- 新增 `app/backend/tests/conftest.py` 提供 `store`、`patient_service`、`task_service`、`write_task`、`seeded_patient_task`、`seeded_processing_patient_task` fixture
- `write_task(task_id="1", status="uploading", **overrides)` 只服务本轮新增测试，不强制重构旧测试
- 患者姓名统一使用"测试用例"等虚构字符串，OCR/字段值同样使用占位文本；不导入真实患者数据

## 隐私约束

- 事件日志禁止写入患者姓名、OCR 原文、结构化字段值或含上述内容的对象
- 导出文件不写入 `name_history`、`metadata_history`
- 测试断言禁止引用真实患者姓名
