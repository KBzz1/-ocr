# BE-03-08 上传失败补偿 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复手机上传失败后留下空 page 或半成品文件的问题，确保失败上传不能被 finish 固化进任务，并且不影响同一 session 已成功上传页面。

**Architecture:** `mobile.upload_page` 仍先创建 page，再调用 `PageService.save()`；新增 `SessionService.remove_unuploaded_page()` 只撤销 upload_ref 为空的 page；`PageService.save()` 负责删除本次已写出的图片/元数据文件；路由层在保存失败后统一撤销 page 并继续返回原始错误。

**Tech Stack:** Flask、现有 `SessionService`/`PageService`/`JsonStore`/`FileValidator`、pytest。不得新增依赖，不做图像处理、OCR、LLM、日志结构改造或前端改动。

---

## Task 0: 基线阅读和测试

- [ ] 阅读 `AGENTS.md`、`docs/AGENTS.md`、本 spec、`docs/Backend/Backend_TDD/05-file-upload.md`、`docs/Backend/Backend_BDD/file-upload.md`。
- [ ] 运行：

```bash
python -m pytest app/backend/tests/test_session_service.py app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py -q
python -m pytest app/backend/tests -q
```

提交：无。

## Task 1: SessionService 精确撤销空上传页

Files:

- `app/backend/services/session_service.py`
- `app/backend/tests/test_session_service.py`

RED:

- [ ] 新增测试：
  - `test_remove_unuploaded_page_removes_only_empty_page`
  - `test_remove_unuploaded_page_is_idempotent_for_missing_page`
  - `test_remove_unuploaded_page_rejects_page_with_upload_ref`
  - `test_remove_unuploaded_page_respects_expired_and_locked_guards`

关键断言：

- 移除 page 后 `page_count` 和 `page_no` 重排正确。
- 有 `upload_ref` 的 page 抛 `INVALID_REQUEST_PARAMS`，不会被删除。
- locked/expired session 保持现有 `SESSION_LOCKED`/`SESSION_EXPIRED` 行为。

运行 RED：

```bash
python -m pytest app/backend/tests/test_session_service.py -q
```

GREEN:

- [ ] 实现：

```python
def remove_unuploaded_page(self, session_id: str, page_id: str) -> dict:
    session = self.get(session_id)
    self._ensure_editable(session)
    target = next((p for p in session["pages"] if p["page_id"] == page_id), None)
    if target is None:
        return session
    if target.get("upload_ref"):
        raise AppError(
            ErrorCode.INVALID_REQUEST_PARAMS,
            message="页面已有上传引用，不能按失败上传撤销",
        )
    session["pages"] = self._renumber_pages([p for p in session["pages"] if p["page_id"] != page_id])
    session["page_count"] = len(session["pages"])
    return self._persist_session(session)
```

- [ ] 不改变 `delete_page()` 语义。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_session_service.py -q
```

提交：

```bash
git add app/backend/services/session_service.py app/backend/tests/test_session_service.py
git commit -m "feat: 增加失败上传页面撤销能力"
```

## Task 2: PageService 清理本次半成品文件

Files:

- `app/backend/services/page_service.py`
- `app/backend/tests/test_page_service.py`

RED:

- [ ] 新增测试：
  - `test_save_invalid_file_type_writes_no_files`
  - `test_save_invalid_quad_writes_no_files`
  - `test_save_metadata_write_failure_removes_image`
  - `test_save_attach_failure_removes_image_and_metadata`
  - `test_save_cleanup_does_not_remove_other_page_files`

测试方式：

- 用 monkeypatch 让 `store.write()` 在 metadata 写入时抛 `OSError("disk full")`。
- 用 monkeypatch 让 `session_service.attach_page_upload()` 抛 `AppError(ErrorCode.SESSION_NOT_FOUND)`。
- 断言只删除当前 `page_id` 对应文件，不删除同 session 其他 page 文件。

运行 RED：

```bash
python -m pytest app/backend/tests/test_page_service.py -q
```

GREEN:

- [ ] 在 `PageService.save()` 内记录本次写出的 `image_path`、`metadata_path`。
- [ ] 写图片成功后，任何后续异常都尝试删除图片。
- [ ] 写 metadata 成功后，attach 失败同时删除 metadata 和图片。
- [ ] 删除 helper 必须确认真实路径位于 `storage_dir` 内；删除失败不吞主异常。
- [ ] `PageService.save()` 不调用 `remove_unuploaded_page()`。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_page_service.py -q
```

提交：

```bash
git add app/backend/services/page_service.py app/backend/tests/test_page_service.py
git commit -m "fix: 清理失败上传半成品文件"
```

## Task 3: Mobile API 上传失败撤销 page

Files:

- `app/backend/routes/mobile.py`
- `app/backend/tests/test_mobile_pages.py`

RED:

- [ ] 新增测试：
  - `test_failed_upload_non_image_does_not_leave_empty_page`
  - `test_failed_upload_oversized_file_does_not_leave_empty_page`
  - `test_failed_upload_invalid_quad_does_not_leave_empty_page`
  - `test_failed_upload_after_success_keeps_successful_page`
  - `test_failed_upload_save_exception_does_not_leave_empty_page`

关键断言：

- 失败响应错误码保持原错误码。
- `GET /api/capture-sessions/{session_id}` 中没有本次失败 page。
- 一个成功页面后再失败，成功页面仍有 `upload_ref`，`finish` 能返回 200。

运行 RED：

```bash
python -m pytest app/backend/tests/test_mobile_pages.py -q
```

GREEN:

- [ ] 在 `mobile.upload_page` 中仅包住 `PageService.save()`：

```python
created_page_id = page["page_id"]
try:
    page_meta = _page_service().save(...)
except Exception:
    try:
        _service().remove_unuploaded_page(session_id, created_page_id)
    except Exception:
        pass
    raise
```

- [ ] 不改变缺少 image / 缺少尺寸的路径，这些错误发生在创建 page 前。
- [ ] 不改变正常上传响应结构。

运行 GREEN：

```bash
python -m pytest app/backend/tests/test_mobile_pages.py -q
```

提交：

```bash
git add app/backend/routes/mobile.py app/backend/tests/test_mobile_pages.py
git commit -m "fix: 上传失败时撤销空页面"
```

## Task 4: 回归和并行边界检查

- [ ] 运行：

```bash
python -m pytest app/backend/tests/test_session_service.py app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py -q
python -m pytest app/backend/tests -q
rg -n "review_service|export_service|local_event_log|run\\.bat|stop\\.bat" app/backend/services/session_service.py app/backend/services/page_service.py app/backend/routes/mobile.py app/backend/tests/test_session_service.py app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py
```

预期：

- pytest 全部通过。
- `rg` 不应显示本任务改动跨入 review/export/log/bat 边界；若测试注释命中，确认不是业务引用。

提交：

```bash
git status --short
```

若只补测试或小修，提交信息用 `test: 补充上传失败补偿回归`。
