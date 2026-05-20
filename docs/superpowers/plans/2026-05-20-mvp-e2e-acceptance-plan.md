# MVP E2E Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用模拟处理结果打通 MVP 成功/失败端到端验收，不依赖真实本地算法实现。

**Architecture:** 后端测试使用极薄的 simulated processing test double 写入候选结果或失败状态，不接入真实 OCR/LLM。前端 Playwright 使用 API route mock 验证用户可观察流程、失败态和网络 gate。实现范围只覆盖 E2E-MVP-01/02，运行包、容器化方案、采集会话、quad 和复杂字段状态全部排除。

**Tech Stack:** Flask test client + pytest + JsonStore；React + TypeScript + Playwright route mock；本地 fixtures，无云 API、无 CDN、无运行时模型下载。

---

## Reference Context

- Spec: `docs/superpowers/specs/2026-05-20-mvp-e2e-acceptance-design.md`
- PRD index: `docs/PRD任务清单.md`
- Product PRD: `docs/产品PRD.md`
- State contract: `docs/Shared/state-enums.md`
- Error contract: `docs/Shared/error-codes.md`
- Backend boundaries: `app/backend/README.md`
- Frontend boundaries: `app/frontend/README.md`

## File Structure

### Backend

- Create: `app/backend/tests/fixtures/processing.py`
  - Owns simulated processing success/failure helpers for E2E tests.
  - Writes only test storage in `tmp_path`.
  - Does not import or call `app/backend/services/algorithm_ports/fixtures.py`.
- Modify: `app/backend/tests/test_backend_e2e.py`
  - Replace algorithm port fixture usage with simulated processing helpers.
  - Expand success flow to 3 uploaded images and JSON/Excel export assertions.
  - Add simulated algorithm exception and invalid contract failure coverage.
- Reuse: `app/backend/tests/fixtures/client.py`
  - Keep task creation and upload helpers.

### Frontend

- Create: `app/frontend/tests/e2e/helpers/mvpApi.ts`
  - Owns Playwright route helpers for success and failed task scenarios.
  - Keeps `current-workflows.spec.ts` readable.
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`
  - Use helper routes.
  - Keep success workflow.
  - Add failed task list and direct review URL workflow.

### Docs

- Modify after all verification passes: `docs/PRD任务清单.md`
  - Mark `E2E-MVP-01` and `E2E-MVP-02` as done only if backend tests, frontend tests, and frontend E2E pass.
  - Keep `REL-MVP-01/02` delayed.

---

## Task 1: Backend Simulated Processing Fixture

**Files:**
- Create: `app/backend/tests/fixtures/processing.py`
- Modify: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Write failing import usage in backend E2E**

Modify the imports at the top of `app/backend/tests/test_backend_e2e.py` to remove algorithm port fixture imports and use the new helper:

```python
"""后端 E2E 契约测试：MVP 任务上传、处理、审核、完成、导出。"""
import json
import os

from app.backend.errors import ErrorCode
from app.backend.tests.fixtures.client import make_client, setup_task_with_images, upload_task_image
from app.backend.tests.fixtures.processing import install_simulated_processing
```

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.backend.tests.fixtures.processing'`.

- [ ] **Step 2: Create simulated processing helper**

Create `app/backend/tests/fixtures/processing.py`:

```python
"""Simulated processing helpers for MVP E2E tests.

These helpers model external algorithm results for tests only. They do not
implement OCR, document parsing, field extraction, image processing, or rules.
"""

from app.backend.errors import ErrorCode
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore


class SimulatedProcessing:
    def __init__(self, store: JsonStore, mode: str = "success"):
        self._store = store
        self._mode = mode

    def run(self, task: dict, task_service: TaskService, schema: dict | None = None) -> dict:
        task_id = task["task_id"]
        if self._mode == "success":
            self._write_success_results(task_id, task, schema=schema)
            return task_service.mark_ready(task_id)
        if self._mode == "module_failed":
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_MODULE_FAILED.code,
                "模拟算法异常",
                stage="field_extraction",
                details={"reason": "simulated_module_failure"},
            )
        if self._mode == "empty_fields":
            self._store.write(
                f"results/{task_id}/field_candidates.json",
                {"task_id": task_id, "stage": "field_extraction", "status": "success", "candidates": []},
            )
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "模拟结构化字段为空",
                stage="field_extraction",
                details={"reason": "empty_candidates"},
            )
        if self._mode == "invalid_contract":
            self._store.write(
                f"results/{task_id}/field_candidates.json",
                {"task_id": task_id, "stage": "field_extraction", "status": "success", "candidates": [{"field_key": ""}]},
            )
            return task_service.mark_failed(
                task_id,
                ErrorCode.ALGORITHM_CONTRACT_INVALID.code,
                "模拟结构化字段契约非法",
                stage="field_extraction",
                details={"reason": "invalid_candidate_contract"},
            )
        raise AssertionError(f"unknown simulated processing mode: {self._mode}")

    def _write_success_results(self, task_id: str, task: dict, schema: dict | None) -> None:
        images = task.get("images") or []
        pages = [
            {
                "page_id": image["page_id"],
                "page_no": image["page_no"],
                "parsed_text": f"第{image['page_no']}页模拟 OCR 文本",
            }
            for image in images
        ]
        self._store.write(
            f"results/{task_id}/document.json",
            {
                "task_id": task_id,
                "stage": "document_parsing",
                "status": "success",
                "pages": pages,
                "merged_text": "模拟 OCR 合并文本",
            },
        )
        self._store.write(
            f"results/{task_id}/field_candidates.json",
            {
                "task_id": task_id,
                "stage": "field_extraction",
                "status": "success",
                "schema_version": (schema or {}).get("version"),
                "candidates": [
                    {
                        "field_key": "chief_complaint",
                        "field_name": "主诉",
                        "original_value": "模拟外部算法返回的主诉",
                        "evidence": "fixture evidence",
                        "page_no": 1,
                        "confidence": "medium",
                    }
                ],
            },
        )


def install_simulated_processing(app, mode: str = "success") -> TaskService:
    store = JsonStore(app.config["BACKEND_CONFIG"]["storage_dir"])
    task_service = TaskService(
        store=store,
        orchestrator=SimulatedProcessing(store, mode=mode),
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    app.config["TASK_SERVICE"] = task_service
    app.config["REVIEW_SERVICE"] = ReviewService(
        store=store,
        task_service=task_service,
        schema_provider=app.config["SCHEMA_SERVICE"].get_current,
    )
    return task_service
```

- [ ] **Step 3: Remove old helper from backend E2E**

Delete the old `install_fixture_task_service()` function and remove these imports from `app/backend/tests/test_backend_e2e.py`:

```python
from app.backend.services.algorithm_ports.fixtures import FixtureDocPort, FixtureFieldPort, FixtureImagePort
from app.backend.services.algorithm_ports.orchestrator import ProcessingOrchestrator
from app.backend.services.review_service import ReviewService
from app.backend.services.task_service import TaskService
from app.backend.storage.json_store import JsonStore
```

- [ ] **Step 4: Run backend E2E to see remaining failures**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py -q
```

Expected: FAIL because tests still call `install_fixture_task_service()` or reference `FixtureFieldPort`.

- [ ] **Step 5: Keep the failing state uncommitted**

Do not commit after Task 1. Task 1 intentionally leaves backend E2E failing because it only introduces the helper and removes old imports. Commit after Task 2 makes the backend E2E pass.

---

## Task 2: Backend Success And Failure E2E

**Files:**
- Modify: `app/backend/tests/test_backend_e2e.py`

- [ ] **Step 1: Update success flow test to use simulated processing and 3 images**

Replace `test_mvp_success_flow_create_upload_process_review_done_export()` with:

```python
def test_mvp_success_flow_create_upload_process_review_done_export(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="success")
    created = client.post("/api/tasks").get_json()["data"]

    for index in range(3):
        upload = upload_task_image(client, created, filename=f"page-{index + 1}.jpg")
        assert upload.status_code == 201
        assert upload.get_json()["data"]["page_no"] == index + 1

    finished = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")
    assert finished.status_code == 200
    assert finished.get_json()["data"]["status"] == "review"

    task_after_finish = client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]
    assert task_after_finish["page_count"] == 3

    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 200
    fields = review.get_json()["data"]["review_result"]["fields"]
    assert fields[0]["field_key"] == "chief_complaint"
    assert fields[0]["auto_value"] == "模拟外部算法返回的主诉"
    assert fields[0]["status"] == "unreviewed"

    saved = client.put(
        f"/api/tasks/{created['task_id']}/review",
        json={"fields": [{"field_key": "chief_complaint", "value": "人工审核后的主诉", "status": "modified"}]},
    )
    assert saved.status_code == 200
    saved_field = saved.get_json()["data"]["review_result"]["fields"][0]
    assert saved_field["auto_value"] == "模拟外部算法返回的主诉"
    assert saved_field["final_value"] == "人工审核后的主诉"

    completed = client.post(f"/api/tasks/{created['task_id']}/complete")
    assert completed.status_code == 200
    assert completed.get_json()["data"]["status"] == "done"

    exported_json = client.get(f"/api/tasks/{created['task_id']}/export/json")
    assert exported_json.status_code == 200
    assert "人工审核后的主诉" in exported_json.get_data(as_text=True)

    exported_excel = client.get(f"/api/tasks/{created['task_id']}/export/excel")
    assert exported_excel.status_code == 200

    assert client.get(f"/api/tasks/{created['task_id']}").get_json()["data"]["status"] == "done"
```

- [ ] **Step 2: Update existing failure tests**

Replace the empty field test with:

```python
def test_mvp_empty_field_candidates_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="empty_fields")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    review = client.get(f"/api/tasks/{created['task_id']}/review")
    assert review.status_code == 400
    assert review.get_json()["error"]["code"] == ErrorCode.INVALID_TASK_TRANSITION.code
```

- [ ] **Step 3: Add simulated module failure test**

Append:

```python
def test_mvp_simulated_algorithm_exception_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="module_failed")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_MODULE_FAILED.code
    assert data["failed_at"]
```

- [ ] **Step 4: Add invalid contract test**

Append:

```python
def test_mvp_invalid_field_contract_goes_failed(tmp_path, monkeypatch):
    client, app = make_client(tmp_path, monkeypatch)
    install_simulated_processing(app, mode="invalid_contract")
    created = setup_task_with_images(client)

    response = client.post(f"/api/mobile-upload/{created['task_id']}/finish?token={created['upload_token']}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "failed"
    assert data["error_code"] == ErrorCode.ALGORITHM_CONTRACT_INVALID.code
    assert data["failed_at"]
```

- [ ] **Step 5: Update log test to use simulated processing**

In `test_e2e_logs_do_not_include_sensitive_payloads()`, replace:

```python
install_fixture_task_service(app)
```

with:

```python
install_simulated_processing(app, mode="success")
```

- [ ] **Step 6: Run backend E2E**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_backend_e2e.py -q
```

Expected: PASS.

- [ ] **Step 7: Run backend full tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 8: Commit backend E2E**

```bash
git add app/backend/tests/fixtures/processing.py app/backend/tests/test_backend_e2e.py
git commit -m "补齐MVP后端E2E模拟验收"
```

---

## Task 3: Frontend E2E Route Mock Helpers

**Files:**
- Create: `app/frontend/tests/e2e/helpers/mvpApi.ts`
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`

- [ ] **Step 1: Create helper directory and route helper file**

Create `app/frontend/tests/e2e/helpers/mvpApi.ts`:

```ts
import { expect, type Page, type Route } from '@playwright/test';

export const localApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\//;

export async function installNetworkGate(page: Page) {
  const unmockedApiRequests: string[] = [];

  await page.route(localApi, async (route) => {
    unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });

  await page.exposeFunction('__assertE2eNetworkGate', () => {
    expect(unmockedApiRequests).toEqual([]);
  });
}

export async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, json: { success: true, data } });
}

export async function fulfillError(route: Route, code: string, message: string, status = 400, details = {}) {
  await route.fulfill({ status, json: { error: { code, message, details } } });
}

export async function mockSystemStatus(page: Page) {
  await page.route('**/api/system/status', async (route) => {
    await fulfillJson(route, {
      status: 'running',
      version: 'test',
      started_at: '2026-05-20T10:00:00+08:00',
      lan_addresses: []
    });
  });
}
```

- [ ] **Step 2: Import helpers in current workflows spec**

At the top of `app/frontend/tests/e2e/current-workflows.spec.ts`, replace local helper imports and definitions with:

```ts
import { expect, test } from '@playwright/test';

import {
  fulfillError,
  fulfillJson,
  installNetworkGate,
  mockSystemStatus
} from './helpers/mvpApi';
```

Keep:

```ts
const imageFixture = 'src/assets/logos/xinqiao-hospital-logo.jpg';
```

Delete local `localApi`, `installNetworkGate()`, and `fulfillJson()`.

- [ ] **Step 3: Update beforeEach to use shared helper**

Keep:

```ts
test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
});
```

- [ ] **Step 4: Run frontend E2E to catch import issues**

Run:

```bash
npm --prefix app/frontend run test:e2e
```

Expected: PASS or fail only on workflow assertions, not TypeScript import errors.

- [ ] **Step 5: Commit helper extraction**

```bash
git add app/frontend/tests/e2e/current-workflows.spec.ts app/frontend/tests/e2e/helpers/mvpApi.ts
git commit -m "抽取MVP前端E2E接口模拟"
```

---

## Task 4: Frontend Success Workflow Assertions

**Files:**
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`

- [ ] **Step 1: Use shared system status mock**

Inside the existing success test, replace the inline `/api/system/status` route with:

```ts
await mockSystemStatus(page);
```

- [ ] **Step 2: Make review mock explicitly represent simulated external output**

In the `GET **/api/tasks/task_001/review` branch, use this response:

```ts
await fulfillJson(route, {
  task_id: 'task_001',
  status: 'review',
  review_result: {
    ocr_text: '模拟 OCR 文本：姓名 张三',
    fields: [
      {
        field_key: 'patient_name',
        label: '姓名',
        value: '张三',
        candidate_value: '张三',
        auto_value: '张三',
        final_value: '张三',
        status: 'unreviewed',
        evidence: [{ page_no: 1, text: 'fixture evidence' }]
      }
    ],
    pages: [{ page_id: 'page_1', page_no: 1, preview_url: '/api/tasks/task_001/pages/page_1/image' }]
  }
});
```

- [ ] **Step 3: Assert no unmocked API calls**

At the end of the success test, add:

```ts
await page.evaluate(() => window.__assertE2eNetworkGate());
```

- [ ] **Step 4: Run success workflow E2E**

Run:

```bash
npm --prefix app/frontend run test:e2e -- --grep "MVP flow"
```

If `scripts/run-playwright.mjs` does not pass through `--grep`, run:

```bash
npm --prefix app/frontend run test:e2e
```

Expected: PASS.

- [ ] **Step 5: Commit success workflow hardening**

```bash
git add app/frontend/tests/e2e/current-workflows.spec.ts
git commit -m "完善MVP前端成功流程E2E"
```

---

## Task 5: Frontend Failure Workflow E2E

**Files:**
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`

- [ ] **Step 1: Add failed task management test**

Append this test before the `declare global` block:

```ts
test('MVP failed flow: failed task shows reason and no manual fallback', async ({ page }) => {
  await mockSystemStatus(page);
  await page.route('**/api/tasks', async (route) => {
    await fulfillJson(route, {
      tasks: [
        {
          task_id: 'task_failed',
          status: 'failed',
          created_at: '2026-05-20T10:00:00+08:00',
          updated_at: '2026-05-20T10:01:00+08:00',
          page_count: 2,
          error_code: 'ALGORITHM_CONTRACT_INVALID',
          error_message: '模拟结构化字段为空',
          review_summary: null,
          export_summary: { last_exported_at: null, formats: [], files: [] }
        }
      ]
    });
  });
  await page.route('**/api/tasks/task_failed/process', async (route) => {
    await fulfillJson(route, {
      task_id: 'task_failed',
      status: 'processing',
      created_at: '2026-05-20T10:00:00+08:00',
      page_count: 2
    });
  });

  await page.goto('/tasks');

  const table = page.getByRole('table', { name: '任务列表' });
  await expect(table.getByText('task_failed')).toBeVisible();
  await expect(table.getByText('失败')).toBeVisible();
  await expect(table.getByText('模拟结构化字段为空')).toBeVisible();
  await expect(table.getByRole('link', { name: '进入审核' })).toHaveCount(0);
  await expect(page.getByText('人工降级')).toHaveCount(0);
  await expect(page.getByText('人工补字段')).toHaveCount(0);
  await expect(page.getByText('查看日志')).toHaveCount(0);

  await table.getByRole('button', { name: '重新处理' }).click();
  await expect(table.getByText('处理中')).toBeVisible();
  await page.evaluate(() => window.__assertE2eNetworkGate());
});
```

- [ ] **Step 2: Add direct review URL failure test**

Append:

```ts
test('MVP failed flow: direct review URL does not render editable fallback fields', async ({ page }) => {
  await mockSystemStatus(page);
  await page.route('**/api/tasks/task_failed/review', async (route) => {
    await fulfillError(
      route,
      'INVALID_TASK_TRANSITION',
      '任务状态 failed 不允许读取审核结果',
      400,
      { current: 'failed' }
    );
  });

  await page.goto('/tasks/task_failed/review');

  await expect(page.getByRole('alert')).toContainText('审核数据加载失败');
  await expect(page.getByRole('textbox')).toHaveCount(0);
  await expect(page.getByRole('button', { name: '保存审核结果' })).toHaveCount(0);
  await expect(page.getByText('人工补字段')).toHaveCount(0);
  await page.evaluate(() => window.__assertE2eNetworkGate());
});
```

- [ ] **Step 3: Run frontend E2E**

Run:

```bash
npm --prefix app/frontend run test:e2e
```

Expected: PASS.

- [ ] **Step 4: Run frontend unit tests**

Run:

```bash
npm --prefix app/frontend test
```

Expected: PASS.

- [ ] **Step 5: Commit failure E2E**

```bash
git add app/frontend/tests/e2e/current-workflows.spec.ts app/frontend/tests/e2e/helpers/mvpApi.ts
git commit -m "补齐MVP前端失败流程E2E"
```

---

## Task 6: Final Verification And PRD Status

**Files:**
- Modify: `docs/PRD任务清单.md`

- [ ] **Step 1: Run backend full tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend unit tests**

Run:

```bash
npm --prefix app/frontend test
```

Expected: PASS.

- [ ] **Step 3: Run frontend E2E**

Run:

```bash
npm --prefix app/frontend run test:e2e
```

Expected: PASS.

- [ ] **Step 4: Update PRD task status only after all tests pass**

In `docs/PRD任务清单.md`, change:

```markdown
- [~] **E2E-MVP-01 成功主流程**
```

to:

```markdown
- [x] **E2E-MVP-01 成功主流程**
```

Change:

```markdown
- [~] **E2E-MVP-02 失败主流程**
```

to:

```markdown
- [x] **E2E-MVP-02 失败主流程**
```

Do not change `REL-MVP-01` or `REL-MVP-02`; they remain delayed.

- [ ] **Step 5: Run documentation diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Commit PRD status update**

```bash
git add docs/PRD任务清单.md
git commit -m "标记MVP端到端验收完成"
```

---

## Fast MVP Review

This plan fits rapid MVP implementation because:

- It does not implement OCR, LLM, document parsing, image processing, crop, perspective correction, or rule extraction.
- It does not require real local algorithm modules to exist.
- It uses simulated processing outputs only in tests and route mocks.
- It does not restore `CaptureSession`, `/api/capture-sessions*`, `/api/mobile/{session_id}/*`, quad, old task states, or complex field states.
- It does not spend time on Windows packaging, container orchestration, installer, or offline deployment scripts.
- It prioritizes the two highest-value acceptance paths: user-visible success flow and user-visible failure flow.

Risk controls:

- Backend E2E remains authoritative for API contracts and persistence.
- Frontend E2E remains mock-based so failures are UI/contract failures, not environment setup failures.
- PRD status is updated only after backend tests, frontend unit tests, and frontend E2E pass.
- Every simulated field value is labeled as external output, preventing accidental schema/OCR inference logic.

## Self-Review

Spec coverage:

- Success flow: covered by Task 2 and Task 4.
- Failure flow: covered by Task 2 and Task 5.
- No real algorithm dependency: covered by Task 1 and Task 2.
- No old session/quad/old statuses: covered by assertions in Task 5 and review criteria.
- No running package/Docker work: excluded from all tasks.
- PRD update: covered by Task 6.

Placeholder scan:

- No placeholder markers or deferred implementation notes are used.
- Each code-changing task includes exact file paths, snippets, commands, and expected outcomes.

Type consistency:

- Backend helper uses existing `TaskService`, `ReviewService`, `JsonStore`, and `ErrorCode`.
- Frontend helpers use Playwright `Page` and `Route`.
- E2E status values remain `uploading / processing / review / done / failed`.
- Field statuses remain `unreviewed / confirmed / modified`.
