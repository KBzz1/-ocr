# 批量导出与 OCR 文本重抽取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建批量 zip 导出和复用 OCR 文本重抽取的后端框架，并暴露轻量前端 API。

**Architecture:** 批量导出复用 `ExportService` 单任务 JSON 导出模型生成 zip。重抽取新增独立服务，复用当前 field extraction port、schema provider 和 schema validator，只读取持久化 OCR 文本。

**Tech Stack:** Flask、JsonStore、pytest、React/TypeScript API client。

---

### Task 1: 批量 Zip 导出

**Files:**
- Modify: `app/backend/services/export_service.py`
- Modify: `app/backend/routes/export.py`
- Test: `app/backend/tests/test_export_service.py`
- Test: `app/backend/tests/test_export_routes.py`

- [ ] 写失败测试：多个 `review/done` 任务导出为 zip，zip 内包含每个任务 JSON。
- [ ] 写失败测试：批量导出拒绝 `uploading/processing/failed` 任务。
- [ ] 实现 `ExportService.export_batch_zip(task_ids)`。
- [ ] 实现 `POST /api/tasks/export/batch-zip`。
- [ ] 跑导出服务和路由测试。

### Task 2: OCR 文本重抽取服务

**Files:**
- Create: `app/backend/services/reextraction_service.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/routes/task.py`
- Modify: `app/backend/errors.py`
- Modify: `docs/Shared/error-codes.md`
- Modify: `app/backend/services/copd_extraction/prompts.py`
- Test: `app/backend/tests/test_reextraction_service.py`
- Test: `app/backend/tests/test_task_routes.py`

- [ ] 写失败测试：服务从 `document_result.json` 读取 OCR 文本并调用字段抽取端口。
- [ ] 写失败测试：服务保存 field candidates、run 审计和 schema/prompt 版本。
- [ ] 写失败测试：缺少 OCR 文本时返回 `REEXTRACTION_VALIDATION_FAILED`。
- [ ] 实现服务和路由 `POST /api/tasks/{task_id}/reextract`。
- [ ] 跑重抽取相关测试。

### Task 3: 前端轻量 API

**Files:**
- Modify: `app/frontend/src/api/export.ts`
- Modify: `app/frontend/src/api/tasks.ts`
- Test: `app/frontend/src/api/shared-contracts.test.ts`

- [ ] 增加 `exportTasksBatchZip(taskIds)`。
- [ ] 增加 `reextractTaskFromOcr(taskId)`。
- [ ] 只补 API 契约测试，不做完整任务页多选 UI。

