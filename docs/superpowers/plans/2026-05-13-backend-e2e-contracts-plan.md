# BE-10 后端 E2E 契约测试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前后端主流程建立 E2E 和 API 契约回归测试，覆盖采集、上传、finish、算法 fixture 处理、审核确认、失败处理、日志隐私和离线检查；默认不新增业务功能。

**Architecture:** 新增 `test_backend_e2e.py` 和 `test_api_contracts.py`；新增测试专用图片 bytes helper；复用现有 `app.backend.services.algorithm_ports.fixtures` 和 `ProcessingOrchestrator` 注入测试 app 的 `TASK_SERVICE`。如暴露真实 bug，先提交失败测试，再做最小修复。

**Tech Stack:** Flask test client、pytest、现有 `JsonStore`、`ProcessingOrchestrator`、算法 fixture ports。不得访问外网，不实现 BE-03 上传补偿、BE-08 导出、前端、OCR/LLM/图像处理。

---

## Task 0: 基线和边界确认

- [ ] 阅读 `AGENTS.md`、`docs/AGENTS.md`、本 spec、`docs/Backend/Backend_TDD/12-api-contracts.md`、`docs/Backend/Backend_TDD/14-fixtures.md`、`docs/Backend/Backend_BDD/task-lifecycle.md`、`docs/Backend/Backend_BDD/review-persistence.md`。
- [ ] 运行：

```bash
python -m pytest app/backend/tests -q
```

提交：无。

## Task 1: 测试 fixtures 和 app factory helper

Files:

- `app/backend/tests/fixtures/__init__.py` NEW
- `app/backend/tests/fixtures/images.py` NEW
- `app/backend/tests/test_backend_e2e.py` NEW

RED:

- [ ] 在 `test_backend_e2e.py` 写一个最小 helper 测试 `test_fixture_client_starts_with_system_status`，调用 helper 创建 app/client 后 `GET /api/system/status` 返回 `{success: true}`。
- [ ] 新增 `images.py`：

```python
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 128
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
PDF_BYTES = b"%PDF-1.4 not image"
```

运行 RED：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

GREEN:

- [ ] 在测试文件内实现 `_write_config(tmp_path)` 和 `_make_client(tmp_path)`，不要改现有测试。
- [ ] helper 使用 `create_backend_app(str(config_dir))`，配置 `data/logs/exports/models` 均指向 `tmp_path`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

提交：

```bash
git add app/backend/tests/fixtures app/backend/tests/test_backend_e2e.py
git commit -m "test: 增加后端 E2E 测试基座"
```

## Task 2: 成功主流程 E2E 到 confirmed

Files:

- `app/backend/tests/test_backend_e2e.py`

RED:

- [ ] 新增 `test_capture_process_review_confirm_success_flow`：
  - `POST /api/capture-sessions`
  - 上传两页 JPEG。
  - `POST /api/mobile/{session_id}/finish` 得到 `task_id`。
  - 注入带成功 fixture ports 的 `TaskService`。
  - `POST /api/tasks/{task_id}/process`。
  - `GET /api/tasks/{task_id}/review`。
  - `PATCH /api/tasks/{task_id}/review/fields/chief_complaint` 修改 `final_value`。
  - `POST /api/tasks/{task_id}/review/confirm`。

运行 RED：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

GREEN:

- [ ] 复用：

```python
from app.backend.services.algorithm_ports.fixtures import FixtureDocPort, FixtureFieldPort, FixtureImagePort
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.services.task_service import TaskService
```

- [ ] 在测试 helper `_install_fixture_task_service(app, *, field_port=None, image_port=None, doc_port=None)` 中重建 `TASK_SERVICE`，并把现有 `REVIEW_SERVICE` 也指向新 task service 或重新创建 `ReviewService`。
- [ ] 成功断言：
  - session 变 `locked`。
  - task 依次可观察到 `uploaded`、处理后 `ready_for_review`、确认后 `confirmed`。
  - review_result 字段来自 fixture port。
  - 修改后的 `final_value` 持久化。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

提交：

```bash
git add app/backend/tests/test_backend_e2e.py
git commit -m "test: 覆盖后端成功主流程"
```

## Task 3: 算法失败主流程 E2E

Files:

- `app/backend/tests/test_backend_e2e.py`

RED:

- [ ] 新增测试：
  - `test_process_without_algorithm_marks_failed_and_review_is_rejected`
  - `test_process_empty_field_candidates_marks_failed`
  - `test_process_bad_field_candidate_contract_marks_failed`

运行 RED：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

GREEN:

- [ ] 未配置算法用 app 默认 `TASK_SERVICE`，预期 `ALGORITHM_MODULE_NOT_CONFIGURED`。
- [ ] 空字段用 `FixtureFieldPort(return_empty=True)`，预期 `ALGORITHM_CONTRACT_INVALID`。
- [ ] 非法字段结构用 `FixtureFieldPort(return_bad_structure=True)`，预期 `ALGORITHM_CONTRACT_INVALID`。
- [ ] 每个失败测试断言：
  - `GET /api/tasks/{task_id}` 为 `failed`。
  - 有 `error_code`、`error_message`、`failed_at`。
  - `GET /api/tasks/{task_id}/review` 返回错误，不能初始化 review_result。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py -q
```

提交：

```bash
git add app/backend/tests/test_backend_e2e.py
git commit -m "test: 覆盖后端失败主流程"
```

## Task 4: API 契约测试

Files:

- `app/backend/tests/test_api_contracts.py` NEW

RED:

- [ ] 新增测试：
  - `test_success_responses_use_success_data_shape`
  - `test_error_responses_use_error_shape_without_traceback`
  - `test_missing_session_and_task_return_standard_errors`
  - `test_upload_missing_image_returns_invalid_request_params`
  - `test_upload_non_image_returns_unsupported_file_type`
  - `test_finish_same_session_is_idempotent`
  - `test_reorder_unknown_page_id_rejects_whole_request`
  - `test_offline_check_returns_local_check_shape`

运行 RED：

```bash
python -m pytest app/backend/tests/test_api_contracts.py -q
```

GREEN:

- [ ] 使用测试文件内 app/client helper，避免修改业务代码。
- [ ] 不测试 BE-08 导出 endpoint。
- [ ] 如果发现某 endpoint 与权威文档明显不一致，先保留失败测试；最小修复要单独提交，且不得落入 BE-03/BE-08 责任边界。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_api_contracts.py -q
```

提交：

```bash
git add app/backend/tests/test_api_contracts.py
git commit -m "test: 增加后端 API 契约回归"
```

## Task 5: 日志隐私和离线约束回归

Files:

- `app/backend/tests/test_backend_e2e.py`
- `app/backend/tests/test_api_contracts.py`

RED:

- [ ] 新增断言：
  - E2E 后读取 `logs/backend-events.jsonl`，至少确认存在 `system_started` 和当前代码已写入的业务事件；不要为了测试新增日志事件。
  - 日志不包含 `JPEG_BYTES` 表示、base64 长串、身份证号模式、fixture merged text 全文。
  - `/api/maintenance/offline-check` 不发起网络访问；可 monkeypatch `socket.socket.connect` 计数，预期该 endpoint 不调用外部 connect。

运行 RED：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py app/backend/tests/test_api_contracts.py -q
```

GREEN:

- [ ] 优先通过测试 helper/断言完成；不新增日志事件、不修改脱敏白名单。
- [ ] 如果现有日志事件名少于预期，以 `docs/Backend/Backend_TDD/11-logging-privacy.md` 和当前代码为准，测试只断言已实现事件及隐私不泄漏。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_backend_e2e.py app/backend/tests/test_api_contracts.py -q
```

提交：

```bash
git add app/backend/tests/test_backend_e2e.py app/backend/tests/test_api_contracts.py
git commit -m "test: 增加日志隐私和离线契约回归"
```

## Task 6: 全量回归和边界扫描

- [ ] 运行：

```bash
python -m pytest app/backend/tests -q
git diff --name-only master...HEAD
rg -n "export_service|remove_unuploaded_page|openpyxl|requests|http://|https://|OCR|LLM|规则抽取" app/backend/tests
```

预期：

- pytest 全部通过。
- diff 主要为 `app/backend/tests/test_backend_e2e.py`、`app/backend/tests/test_api_contracts.py`、`app/backend/tests/fixtures/*`。
- 不出现 BE-08 导出实现、BE-03 上传补偿实现、新联网依赖或算法实现。

提交：

```bash
git status --short
```

若只补测试稳定性，提交信息用 `test: 收口后端 E2E 回归验证`。
