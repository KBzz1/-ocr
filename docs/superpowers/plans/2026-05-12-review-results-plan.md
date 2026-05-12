# BE-07 人工审核结果 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现审核结果读取、字段编辑保存和确认校验，让电脑端后续可基于人工最终值导出。

**Architecture:** 新增 `ReviewService` 负责从外部字段候选初始化 `review_result.json`、保存字段最终值和修改历史、执行确认前完整性校验。新增 `review_bp` 暴露 GET/PATCH/POST API；确认成功只通过现有 `TaskService.mark_confirmed()` 推进任务状态，并补充 `confirmed_at` 与 `review_summary`。不修改算法编排、不改候选字段契约、不实现导出或前端。

**Tech Stack:** Flask, pytest, JsonStore, existing `TaskService`, existing `SchemaService`, local JSON persistence

---

## Scope and Boundaries

- 权威依据：`docs/产品PRD.md` PR-BE-008、`docs/Shared/state-enums.md`、`docs/Shared/error-codes.md`、`docs/Backend/Backend_TDD/09-review-results.md`、`docs/Backend/Backend_BDD/review-persistence.md`。
- 只读取 `results/{task_id}/field_candidates.json`，不得覆盖或重写自动候选文件。
- 初始化时只复制外部候选字段；不得根据 schema、OCR 文本或页面内容补造缺失字段。
- 只允许 `ready_for_review` 任务编辑和确认；`confirmed` 任务允许读取；`failed/uploaded/processing` 等状态必须返回 `INVALID_TASK_TRANSITION`。
- 无来源字段计入 `missing_evidence_count`，不阻断确认；`unreviewed`、`suspicious`、未接受的 `empty` 和零字段必须阻断确认。
- 与 BE-09 并行时，本计划不引入日志事件点；BE-09 后续只能调用服务结果记录摘要，不反向修改 `review_result.json` 契约。

## Files

- Create: `app/backend/services/review_service.py`
- Create: `app/backend/routes/review.py`
- Create: `app/backend/tests/test_review_service.py`
- Create: `app/backend/tests/test_review_routes.py`
- Modify: `app/backend/__init__.py` register `ReviewService` and `review_bp`
- Modify: `app/backend/routes/__init__.py` add `_get_review_service()`
- Modify: `app/backend/services/task_service.py` add optional `confirmed_at` and `review_summary` handling in `mark_confirmed()`

## Parallel Merge Notes

- BE-09 may also modify `app/backend/__init__.py` to register local event log and maintenance services. Merge by preserving both sets of app config keys: `REVIEW_SERVICE`, `LOCAL_EVENT_LOG`, `OFFLINE_CHECK_SERVICE`, and `CLEANUP_SERVICE`.
- BE-09 may also modify `app/backend/services/task_service.py` to log processing events. Merge by keeping BE-07's `mark_confirmed(task_id, review_summary=None)` signature and BE-09's event calls in `_start_processing()`, `mark_failed()`, and `mark_ready()`; BE-09 must not write inside `mark_confirmed()` unless it only logs a summary after BE-07 is merged.
- BE-01 should not touch review files. If a merge conflict appears with BE-01, prefer BE-01 for `run.bat`/`stop.bat` and BE-07 for review service/routes.

---

### Task 0: Baseline

**Files:**
- Run only: backend test suite

- [ ] **Step 1: Run existing backend tests**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests -q
```

Expected: PASS. If the baseline fails before BE-07 edits, stop and report the failing tests.

---

### Task 1: ReviewService Initialization and Read

**Files:**
- Create: `app/backend/tests/test_review_service.py`
- Create: `app/backend/services/review_service.py`

- [ ] **Step 1: Write failing service tests**

Create `app/backend/tests/test_review_service.py`:

```python
import pytest

from app.backend.errors import AppError, ErrorCode
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


def make_review_service(tmp_path, schema=None):
    from app.backend.services.review_service import ReviewService

    store = JsonStore(str(tmp_path))
    task_service = TaskService(store)
    if schema is None:
        schema = {
            "version": "medical_record.v1",
            "document_type": "medical_record",
            "field_groups": [
                {
                    "group_key": "history",
                    "group_label": "病史",
                    "fields": [
                        {"field_key": "chief_complaint", "label": "主诉"},
                        {"field_key": "diagnosis", "label": "初步诊断"},
                    ],
                }
            ],
        }
    return ReviewService(store, task_service, schema_provider=lambda: schema), store


def write_task(store, task_id="task-001", status="ready_for_review"):
    store.write(
        f"tasks/{task_id}.json",
        {
            "task_id": task_id,
            "session_id": "session-001",
            "status": status,
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 2,
            "page_order": ["page-1", "page-2"],
            "source": "capture_session",
            "schema_version": "medical_record.v1",
            "document_type": "medical_record",
        },
    )


def write_candidates(store, task_id="task-001", candidates=None):
    if candidates is None:
        candidates = [
            {
                "field_key": "chief_complaint",
                "original_value": "头痛3天",
                "field_name": "主诉",
                "evidence": "第1页第2行",
                "page_no": 1,
                "confidence": 0.95,
            },
            {
                "field_key": "diagnosis",
                "original_value": "上呼吸道感染",
                "field_name": "初步诊断",
                "evidence": "第2页",
                "page_no": 2,
                "confidence": 0.8,
            },
        ]
    store.write(
        f"results/{task_id}/field_candidates.json",
        {"task_id": task_id, "stage": "field_extraction", "status": "success", "candidates": candidates},
    )


def find_field(review, field_key):
    return next(field for field in review["fields"] if field["field_key"] == field_key)


class TestReviewServiceRead:
    def test_first_read_initializes_review_result_from_candidates(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)

        review = service.get_or_init("task-001")

        assert review["task_id"] == "task-001"
        assert review["schema_version"] == "medical_record.v1"
        assert review["document_type"] == "medical_record"
        assert review["initialized_at"]
        assert review["updated_at"]
        assert [f["field_key"] for f in review["fields"]] == ["chief_complaint", "diagnosis"]

        field = find_field(review, "chief_complaint")
        assert field["field_name"] == "主诉"
        assert field["auto_value"] == "头痛3天"
        assert field["final_value"] == "头痛3天"
        assert field["status"] == "unreviewed"
        assert field["empty_accepted"] is False
        assert field["history"] == []

        assert review["summary"]["total_count"] == 2
        assert review["summary"]["unreviewed_count"] == 2
        assert review["summary"]["missing_evidence_count"] == 0

    def test_second_read_does_not_overwrite_manual_result(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        review = service.get_or_init("task-001")
        find_field(review, "chief_complaint")["final_value"] = "人工修正"
        find_field(review, "chief_complaint")["status"] = "modified"
        store.write("results/task-001/review_result.json", review)

        reopened = service.get_or_init("task-001")

        assert find_field(reopened, "chief_complaint")["final_value"] == "人工修正"
        assert find_field(reopened, "chief_complaint")["status"] == "modified"

    def test_auto_candidate_file_is_not_modified(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)

        service.get_or_init("task-001")

        candidates = store.read("results/task-001/field_candidates.json")
        assert candidates["candidates"][0]["original_value"] == "头痛3天"

    def test_missing_candidates_returns_review_validation_failed(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code

    def test_empty_candidates_returns_review_validation_failed(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store, candidates=[])

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code

    def test_non_reviewable_task_cannot_read(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store, status="failed")
        write_candidates(store)

        with pytest.raises(AppError) as exc_info:
            service.get_or_init("task-001")

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceRead -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.backend.services.review_service'`.

- [ ] **Step 3: Implement minimal ReviewService**

Create `app/backend/services/review_service.py`:

```python
from datetime import datetime, timezone
from typing import Callable

from ..enums import TaskStatus
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class ReviewService:
    def __init__(self, store: JsonStore, task_service, schema_provider: Callable[[], dict] | None = None):
        self._store = store
        self._task_service = task_service
        self._schema_provider = schema_provider

    def get_or_init(self, task_id: str) -> dict:
        existing = self._store.read(f"results/{task_id}/review_result.json")
        if existing is not None:
            return existing

        task = self._task_service.get_task(task_id)
        self._ensure_readable(task)
        wrapper = self._store.read(f"results/{task_id}/field_candidates.json")
        candidates = wrapper.get("candidates") if isinstance(wrapper, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise AppError(ErrorCode.REVIEW_VALIDATION_FAILED, message="字段候选缺失或为空，无法初始化审核")

        schema = self._schema_provider() if self._schema_provider else {}
        fields = self._build_fields(candidates, schema)
        now = self._now()
        review = {
            "task_id": task_id,
            "schema_version": schema.get("version") or task.get("schema_version"),
            "document_type": schema.get("document_type") or task.get("document_type"),
            "initialized_at": now,
            "updated_at": now,
            "fields": fields,
            "summary": self._build_summary(fields),
        }
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def _build_fields(self, candidates: list[dict], schema: dict) -> list[dict]:
        labels = {}
        order = {}
        index = 0
        for group in schema.get("field_groups", []):
            for field in group.get("fields", []):
                key = field["field_key"]
                labels[key] = field.get("label") or field.get("field_name") or key
                order[key] = index
                index += 1

        sorted_candidates = sorted(
            candidates,
            key=lambda c: order.get(c.get("field_key"), len(order)),
        )
        result = []
        for item in sorted_candidates:
            field_key = item["field_key"]
            auto_value = item.get("original_value", "")
            result.append(
                {
                    "field_key": field_key,
                    "field_name": labels.get(field_key) or item.get("field_name") or field_key,
                    "auto_value": auto_value,
                    "final_value": auto_value,
                    "evidence": item.get("evidence"),
                    "page_no": item.get("page_no"),
                    "confidence": item.get("confidence"),
                    "status": "unreviewed",
                    "empty_accepted": False,
                    "review_note": None,
                    "reviewed_at": None,
                    "updated_at": None,
                    "history": [],
                }
            )
        return result

    def _build_summary(self, fields: list[dict]) -> dict:
        return {
            "total_count": len(fields),
            "unreviewed_count": sum(1 for f in fields if f["status"] == "unreviewed"),
            "confirmed_count": sum(1 for f in fields if f["status"] == "confirmed"),
            "modified_count": sum(1 for f in fields if f["status"] == "modified"),
            "suspicious_count": sum(1 for f in fields if f["status"] == "suspicious"),
            "empty_count": sum(1 for f in fields if f["status"] == "empty"),
            "empty_unaccepted_count": sum(1 for f in fields if f["status"] == "empty" and not f["empty_accepted"]),
            "missing_evidence_count": sum(1 for f in fields if not f.get("evidence")),
        }

    def _ensure_readable(self, task: dict) -> None:
        if task["status"] not in (TaskStatus.READY_FOR_REVIEW.value, TaskStatus.CONFIRMED.value):
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许读取审核结果",
                details={"current": task["status"]},
            )

    def _ensure_writable(self, task: dict) -> None:
        if task["status"] != TaskStatus.READY_FOR_REVIEW.value:
            raise AppError(
                ErrorCode.INVALID_TASK_TRANSITION,
                message=f"任务状态 {task['status']} 不允许编辑审核结果",
                details={"current": task["status"]},
            )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceRead -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_review_service.py app/backend/services/review_service.py
git commit -m "feat: 初始化并读取人工审核结果"
```

---

### Task 2: Field Edit Actions and History

**Files:**
- Modify: `app/backend/tests/test_review_service.py`
- Modify: `app/backend/services/review_service.py`

- [ ] **Step 1: Append failing field action tests**

Append to `app/backend/tests/test_review_service.py`:

```python
class TestReviewServiceFieldActions:
    def test_confirm_keeps_current_value_when_final_value_omitted(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        review = service.update_field("task-001", "chief_complaint", {"action": "confirm"})

        field = find_field(review, "chief_complaint")
        assert field["status"] == "confirmed"
        assert field["final_value"] == "头痛3天"
        assert field["empty_accepted"] is False
        assert field["history"][0]["action"] == "confirm"

    def test_modify_updates_final_value_and_preserves_auto_value(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        review = service.update_field(
            "task-001",
            "chief_complaint",
            {"action": "modify", "final_value": "头痛3天，加重1天", "review_note": "按原文修正"},
        )

        field = find_field(review, "chief_complaint")
        assert field["status"] == "modified"
        assert field["auto_value"] == "头痛3天"
        assert field["final_value"] == "头痛3天，加重1天"
        assert field["review_note"] == "按原文修正"
        assert field["history"][0]["from_value"] == "头痛3天"
        assert field["history"][0]["to_value"] == "头痛3天，加重1天"

    def test_clear_then_accept_empty(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        cleared = service.update_field("task-001", "diagnosis", {"action": "clear"})
        assert find_field(cleared, "diagnosis")["status"] == "empty"
        assert find_field(cleared, "diagnosis")["final_value"] == ""
        assert find_field(cleared, "diagnosis")["empty_accepted"] is False

        accepted = service.update_field("task-001", "diagnosis", {"action": "accept_empty"})
        assert find_field(accepted, "diagnosis")["status"] == "empty"
        assert find_field(accepted, "diagnosis")["empty_accepted"] is True

    def test_mark_suspicious_keeps_value_and_note(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        review = service.update_field("task-001", "diagnosis", {"action": "mark_suspicious", "review_note": "来源不清"})

        field = find_field(review, "diagnosis")
        assert field["status"] == "suspicious"
        assert field["final_value"] == "上呼吸道感染"
        assert field["review_note"] == "来源不清"

    def test_multiple_changes_preserve_history_order(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        service.update_field("task-001", "chief_complaint", {"action": "modify", "final_value": "改1"})
        service.update_field("task-001", "chief_complaint", {"action": "modify", "final_value": "改2"})
        review = service.update_field("task-001", "chief_complaint", {"action": "confirm"})

        history = find_field(review, "chief_complaint")["history"]
        assert [h["action"] for h in history] == ["modify", "modify", "confirm"]
        assert history[0]["from_value"] == "头痛3天"
        assert history[1]["from_value"] == "改1"
        assert history[2]["to_value"] == "改2"

    def test_invalid_action_returns_invalid_request_params(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")

        with pytest.raises(AppError) as exc_info:
            service.update_field("task-001", "chief_complaint", {"action": "delete"})

        assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code

    def test_processing_task_cannot_update_review(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        write_task(store, status="processing")

        with pytest.raises(AppError) as exc_info:
            service.update_field("task-001", "chief_complaint", {"action": "confirm"})

        assert exc_info.value.code == ErrorCode.INVALID_TASK_TRANSITION.code
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceFieldActions -q
```

Expected: FAIL with `AttributeError: 'ReviewService' object has no attribute 'update_field'`.

- [ ] **Step 3: Implement update_field**

Append methods inside `ReviewService` in `app/backend/services/review_service.py`:

```python
    def update_field(self, task_id: str, field_key: str, payload: dict) -> dict:
        task = self._task_service.get_task(task_id)
        self._ensure_writable(task)
        review = self.get_or_init(task_id)

        action = payload.get("action")
        review_note = payload.get("review_note")
        if review_note is not None and not isinstance(review_note, str):
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="review_note 必须是字符串或 null")

        field = self._find_field(review, field_key)
        old_value = field["final_value"]
        now = self._now()

        if action == "confirm":
            if "final_value" in payload:
                if not isinstance(payload["final_value"], str):
                    raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="final_value 必须是字符串")
                field["final_value"] = payload["final_value"]
            field["status"] = "confirmed"
            field["empty_accepted"] = False
        elif action == "modify":
            if not isinstance(payload.get("final_value"), str):
                raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="modify 必须提供字符串 final_value")
            field["final_value"] = payload["final_value"]
            field["status"] = "modified"
            field["empty_accepted"] = False
        elif action == "clear":
            field["final_value"] = ""
            field["status"] = "empty"
            field["empty_accepted"] = False
        elif action == "accept_empty":
            if field["status"] != "empty" or field["final_value"] != "":
                raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="只有已清空字段可以接受空值")
            field["status"] = "empty"
            field["empty_accepted"] = True
        elif action == "mark_suspicious":
            field["status"] = "suspicious"
            field["empty_accepted"] = False
        else:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"未知审核动作: {action}")

        field["review_note"] = review_note
        field["reviewed_at"] = now
        field["updated_at"] = now
        field.setdefault("history", []).append(
            {
                "action": action,
                "from_value": old_value,
                "to_value": field["final_value"],
                "review_note": review_note,
                "changed_at": now,
            }
        )
        review["updated_at"] = now
        review["summary"] = self._build_summary(review["fields"])
        self._store.write(f"results/{task_id}/review_result.json", review)
        return review

    def _find_field(self, review: dict, field_key: str) -> dict:
        for field in review["fields"]:
            if field["field_key"] == field_key:
                return field
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message=f"字段 {field_key} 不在审核结果中")
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceFieldActions -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/test_review_service.py app/backend/services/review_service.py
git commit -m "feat: 保存字段审核动作和修改历史"
```

---

### Task 3: Confirmation Validation and Task Transition

**Files:**
- Modify: `app/backend/tests/test_review_service.py`
- Modify: `app/backend/services/review_service.py`
- Modify: `app/backend/services/task_service.py`

- [ ] **Step 1: Append failing confirmation tests**

Append to `app/backend/tests/test_review_service.py`:

```python
class TestReviewServiceConfirm:
    def test_confirm_blocks_unreviewed_fields(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})

        with pytest.raises(AppError) as exc_info:
            service.confirm("task-001")

        assert exc_info.value.code == ErrorCode.REVIEW_VALIDATION_FAILED.code
        assert exc_info.value.details["unreviewed"] == ["diagnosis"]

    def test_confirm_blocks_suspicious_fields(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})
        service.update_field("task-001", "diagnosis", {"action": "mark_suspicious"})

        with pytest.raises(AppError) as exc_info:
            service.confirm("task-001")

        assert exc_info.value.details["suspicious"] == ["diagnosis"]

    def test_confirm_blocks_unaccepted_empty_fields(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})
        service.update_field("task-001", "diagnosis", {"action": "clear"})

        with pytest.raises(AppError) as exc_info:
            service.confirm("task-001")

        assert exc_info.value.details["empty_unaccepted"] == ["diagnosis"]

    def test_confirm_all_confirmed_updates_task(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})
        service.update_field("task-001", "diagnosis", {"action": "modify", "final_value": "上感"})

        task = service.confirm("task-001")

        assert task["status"] == "confirmed"
        assert task["confirmed_at"]
        assert task["review_summary"]["unreviewed_count"] == 0
        assert task["review_summary"]["modified_count"] == 1

    def test_confirm_accepted_empty_passes(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(store)
        service.get_or_init("task-001")
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})
        service.update_field("task-001", "diagnosis", {"action": "clear"})
        service.update_field("task-001", "diagnosis", {"action": "accept_empty"})

        task = service.confirm("task-001")

        assert task["status"] == "confirmed"

    def test_missing_evidence_is_counted_but_not_blocking(self, tmp_path):
        service, store = make_review_service(tmp_path)
        write_task(store)
        write_candidates(
            store,
            candidates=[
                {"field_key": "chief_complaint", "original_value": "头痛", "evidence": "第1页", "confidence": 0.9},
                {"field_key": "diagnosis", "original_value": "上感", "confidence": 0.8},
            ],
        )
        review = service.get_or_init("task-001")
        assert review["summary"]["missing_evidence_count"] == 1
        service.update_field("task-001", "chief_complaint", {"action": "confirm"})
        service.update_field("task-001", "diagnosis", {"action": "confirm"})

        task = service.confirm("task-001")

        assert task["status"] == "confirmed"
        assert task["review_summary"]["missing_evidence_count"] == 1
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceConfirm -q
```

Expected: FAIL with `AttributeError: 'ReviewService' object has no attribute 'confirm'`.

- [ ] **Step 3: Extend TaskService.mark_confirmed**

Modify `app/backend/services/task_service.py`:

```python
    def mark_confirmed(self, task_id: str, review_summary: dict | None = None) -> dict:
        task = self._read_task(task_id)
        task = self._transition(task, TaskStatus.CONFIRMED.value, "审核确认")
        task["confirmed_at"] = self._now()
        if review_summary is not None:
            task["review_summary"] = review_summary
        self._write_task(task)
        return task
```

- [ ] **Step 4: Implement ReviewService.confirm**

Append inside `ReviewService`:

```python
    def confirm(self, task_id: str) -> dict:
        task = self._task_service.get_task(task_id)
        self._ensure_writable(task)
        review = self.get_or_init(task_id)
        summary = self._build_summary(review["fields"])

        unreviewed = [f["field_key"] for f in review["fields"] if f["status"] == "unreviewed"]
        suspicious = [f["field_key"] for f in review["fields"] if f["status"] == "suspicious"]
        empty_unaccepted = [
            f["field_key"]
            for f in review["fields"]
            if f["status"] == "empty" and not f["empty_accepted"]
        ]
        if not review["fields"] or unreviewed or suspicious or empty_unaccepted:
            raise AppError(
                ErrorCode.REVIEW_VALIDATION_FAILED,
                message="审核确认校验失败",
                details={
                    "unreviewed": unreviewed,
                    "suspicious": suspicious,
                    "empty_unaccepted": empty_unaccepted,
                    "missing_evidence_count": summary["missing_evidence_count"],
                },
            )
        return self._task_service.mark_confirmed(task_id, review_summary=summary)
```

- [ ] **Step 5: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py::TestReviewServiceConfirm -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/backend/tests/test_review_service.py app/backend/services/review_service.py app/backend/services/task_service.py
git commit -m "feat: 实现审核确认校验和任务确认状态"
```

---

### Task 4: Review API Routes and App Wiring

**Files:**
- Create: `app/backend/routes/review.py`
- Create: `app/backend/tests/test_review_routes.py`
- Modify: `app/backend/__init__.py`
- Modify: `app/backend/routes/__init__.py`

- [ ] **Step 1: Write failing route tests**

Create `app/backend/tests/test_review_routes.py`:

```python
import pytest

from app.backend import create_backend_app
from app.backend.storage.json_store import JsonStore


@pytest.fixture
def app(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path / 'data'}"
  log_dir: "{tmp_path / 'logs'}"
  storage_dir: "{tmp_path / 'data'}"
  export_dir: "{tmp_path / 'exports'}"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    flask_app = create_backend_app(config_dir=str(config_dir))
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def seed_reviewable_task(app, status="ready_for_review"):
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    store.write(
        "tasks/task-001.json",
        {
            "task_id": "task-001",
            "session_id": "session-001",
            "status": status,
            "created_at": "2026-05-12T10:00:00+00:00",
            "page_count": 1,
            "page_order": ["page-1"],
            "source": "capture_session",
            "schema_version": "medical_record.v1",
            "document_type": "medical_record",
        },
    )
    store.write(
        "results/task-001/field_candidates.json",
        {
            "task_id": "task-001",
            "stage": "field_extraction",
            "status": "success",
            "candidates": [
                {"field_key": "chief_complaint", "original_value": "头痛3天", "evidence": "第1页", "confidence": 0.95},
                {"field_key": "diagnosis", "original_value": "上感", "evidence": "第1页", "confidence": 0.8},
            ],
        },
    )


def field_from_response(resp, field_key):
    fields = resp.get_json()["data"]["review_result"]["fields"]
    return next(field for field in fields if field["field_key"] == field_key)


class TestReviewRoutes:
    def test_get_review_initializes_result(self, client, app):
        seed_reviewable_task(app)

        resp = client.get("/api/tasks/task-001/review")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["task_id"] == "task-001"
        assert data["status"] == "ready_for_review"
        assert data["review_result"]["summary"]["unreviewed_count"] == 2

    def test_patch_modify_field(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.patch(
            "/api/tasks/task-001/review/fields/chief_complaint",
            json={"action": "modify", "final_value": "修正值"},
        )

        assert resp.status_code == 200
        field = field_from_response(resp, "chief_complaint")
        assert field["status"] == "modified"
        assert field["final_value"] == "修正值"

    def test_patch_confirm_field_without_final_value(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.patch("/api/tasks/task-001/review/fields/chief_complaint", json={"action": "confirm"})

        assert resp.status_code == 200
        assert field_from_response(resp, "chief_complaint")["status"] == "confirmed"

    def test_confirm_incomplete_review_returns_review_validation_failed(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")

        resp = client.post("/api/tasks/task-001/review/confirm")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "REVIEW_VALIDATION_FAILED"
        assert resp.get_json()["error"]["details"]["unreviewed"] == ["chief_complaint", "diagnosis"]

    def test_confirm_complete_review_updates_task(self, client, app):
        seed_reviewable_task(app)
        client.get("/api/tasks/task-001/review")
        client.patch("/api/tasks/task-001/review/fields/chief_complaint", json={"action": "confirm"})
        client.patch("/api/tasks/task-001/review/fields/diagnosis", json={"action": "confirm"})

        resp = client.post("/api/tasks/task-001/review/confirm")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "confirmed"
        assert resp.get_json()["data"]["review_summary"]["unreviewed_count"] == 0

    def test_failed_task_cannot_enter_review_flow(self, client, app):
        seed_reviewable_task(app, status="failed")

        resp = client.get("/api/tasks/task-001/review")

        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_TASK_TRANSITION"
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_routes.py -q
```

Expected: FAIL with 404 responses because the review route is not registered.

- [ ] **Step 3: Add route helper**

Modify `app/backend/routes/__init__.py`:

```python
from flask import current_app


def _get_task_service():
    return current_app.config["TASK_SERVICE"]


def _get_session_service():
    return current_app.config["SESSION_SERVICE"]


def _get_page_service():
    return current_app.config["PAGE_SERVICE"]


def _get_schema_service():
    return current_app.config["SCHEMA_SERVICE"]


def _get_review_service():
    return current_app.config["REVIEW_SERVICE"]
```

Keep any existing helpers and only add `_get_review_service()` if the file already contains the others.

- [ ] **Step 4: Add review blueprint**

Create `app/backend/routes/review.py`:

```python
from flask import Blueprint, request

from ..responses import success
from . import _get_review_service, _get_task_service

review_bp = Blueprint("review", __name__)


@review_bp.route("/api/tasks/<task_id>/review", methods=["GET"])
def get_review(task_id):
    task = _get_task_service().get_task(task_id)
    review = _get_review_service().get_or_init(task_id)
    return success(data={"task_id": task_id, "status": task["status"], "review_result": review})


@review_bp.route("/api/tasks/<task_id>/review/fields/<field_key>", methods=["PATCH"])
def update_review_field(task_id, field_key):
    payload = request.get_json(silent=True) or {}
    review = _get_review_service().update_field(task_id, field_key, payload)
    return success(data={"task_id": task_id, "review_result": review})


@review_bp.route("/api/tasks/<task_id>/review/confirm", methods=["POST"])
def confirm_review(task_id):
    task = _get_review_service().confirm(task_id)
    return success(data=task)
```

- [ ] **Step 5: Wire service and blueprint**

Modify `app/backend/__init__.py` after `TASK_SERVICE` creation:

```python
    from .services.review_service import ReviewService

    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=app.config["TASK_SERVICE"],
        schema_provider=schema_service.get_current,
    )
```

Register blueprint near other routes:

```python
    from .routes.review import review_bp
    app.register_blueprint(review_bp)
```

- [ ] **Step 6: Run GREEN**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_routes.py -q
```

Expected: PASS.

- [ ] **Step 7: Run BE-07 regression**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests/test_review_service.py app/backend/tests/test_review_routes.py app/backend/tests/test_task_service.py app/backend/tests/test_task_routes.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/backend/routes/__init__.py app/backend/routes/review.py app/backend/__init__.py app/backend/tests/test_review_routes.py
git commit -m "feat: 暴露人工审核结果 API"
```

---

### Task 5: Final Verification

**Files:**
- Run only: backend tests and placeholder scan

- [ ] **Step 1: Run full backend tests**

Run:

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/be07-review-results-spec
python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 2: Review boundary compliance**

Read `app/backend/services/review_service.py` and `app/backend/routes/review.py` and confirm the implementation only copies external field candidates into `review_result.json`, then saves human review state. There must be no fallback field generation, no algorithm implementation, and no export behavior in this BE-07 change.

- [ ] **Step 3: Commit verification notes if any docs changed**

No commit is required if Step 1 and Step 2 only run commands and produce no file changes.
