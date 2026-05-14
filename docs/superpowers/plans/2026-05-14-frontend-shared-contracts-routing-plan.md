# Frontend Shared Contracts And Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This plan covers the serial S1/S2 slice from `docs/superpowers/specs/2026-05-14-frontend-next-stage-orchestration-design.md`; do not dispatch parallel page work until this plan is merged.

## Goal

Create the shared frontend contract layer and stable route skeleton needed before FE-02 to FE-05 page work starts.

This plan intentionally does not implement mobile capture UI, task list UI, review UI, or export UI. It only provides typed API boundaries, shared state labels, fixtures, and route placeholders so later tasks can build on stable contracts.

## Files

- `app/frontend/src/api/client.ts`: keep existing request/response parser; add download helper only if tests require it.
- `app/frontend/src/api/captureSessions.ts`: extend with load session, upload page metadata, finish session types/functions.
- `app/frontend/src/api/tasks.ts`: extend with task detail, retry/process types/functions.
- `app/frontend/src/api/review.ts`: new review result/read/save/confirm API functions.
- `app/frontend/src/api/export.ts`: new JSON/Excel export API functions returning `Blob`.
- `app/frontend/src/api/errors.ts`: new user-facing error normalization.
- `app/frontend/src/styles/status.ts`: extend shared status maps for task, session, field, export.
- `app/frontend/src/app/routes.tsx`: define stable route constants and route metadata.
- `app/frontend/src/app/App.tsx`: keep current workstation rendering; no router dependency yet unless route tests require it.
- `app/frontend/src/pages/mobile-capture/MobileCapturePlaceholder.tsx`: route placeholder only.
- `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`: route placeholder only.
- `app/frontend/src/pages/review/ReviewPlaceholder.tsx`: route placeholder only.
- `app/frontend/src/pages/export/ExportPlaceholder.tsx`: route placeholder only.
- `app/frontend/tests/fixtures/sessions.ts`: add upload/finish fixtures.
- `app/frontend/tests/fixtures/tasks.ts`: add task detail/retry fixtures.
- `app/frontend/tests/fixtures/review.ts`: new review fixtures.
- `app/frontend/tests/fixtures/export.ts`: new export fixtures.
- `app/frontend/src/api/shared-contracts.test.ts`: new API/status contract tests.
- `app/frontend/src/app/routes.test.ts`: new route skeleton tests.
- `app/frontend/README.md`: document route and contract layer status.
- `docs/PRD任务清单.md`: update only if S1/S2 completes and validation passes.

## Task 1: Add Shared Contract Tests

- [x] **Step 1: Create `app/frontend/src/api/shared-contracts.test.ts`**

Add tests that assert the next-stage contract surface without building pages:

```ts
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import {
  finishCaptureSession,
  getCaptureSession,
  uploadCapturePage
} from './captureSessions';
import { exportTaskExcel, exportTaskJson } from './export';
import { normalizeApiError } from './errors';
import {
  confirmReview,
  getReviewResult,
  saveReviewField
} from './review';
import { getTaskDetail, retryTaskProcessing } from './tasks';
import {
  fieldStatusMeta,
  sessionStatusMeta,
  taskStatusMeta
} from '../styles/status';
import { server } from '../../tests/setupTests';

describe('shared frontend contracts', () => {
  it('maps task, session and field states to Chinese labels', () => {
    expect(taskStatusMeta.ready_for_review.label).toBe('待审核');
    expect(taskStatusMeta.processing.label).toBe('处理中');
    expect(taskStatusMeta.failed.label).toBe('处理失败');
    expect(sessionStatusMeta.active.label).toBe('采集中');
    expect(sessionStatusMeta.locked.label).toBe('已完成采集');
    expect(fieldStatusMeta.unreviewed.label).toBe('未审核');
    expect(fieldStatusMeta.suspicious.label).toBe('存疑');
  });

  it('loads capture session, uploads page metadata and finishes capture', async () => {
    server.use(
      http.get('*/api/capture-sessions/sess_001', () =>
        HttpResponse.json({
          success: true,
          data: {
            session_id: 'sess_001',
            status: 'active',
            created_at: '2026-05-14T10:00:00+08:00',
            expires_at: '2026-05-14T10:30:00+08:00',
            qr_code_url: 'http://192.168.1.5:8081/mobile/sess_001',
            page_count: 1
          }
        })
      ),
      http.post('*/api/capture-sessions/sess_001/pages', async ({ request }) => {
        const formData = await request.formData();
        expect(formData.get('width')).toBe('1200');
        expect(formData.get('height')).toBe('1600');
        expect(formData.get('quad_points')).toBe('[{\"x\":0,\"y\":0},{\"x\":1200,\"y\":0},{\"x\":1200,\"y\":1600},{\"x\":0,\"y\":1600}]');
        return HttpResponse.json({
          success: true,
          data: {
            page_id: 'page_001',
            page_index: 1,
            status: 'uploaded'
          }
        });
      }),
      http.post('*/api/capture-sessions/sess_001/finish', () =>
        HttpResponse.json({
          success: true,
          data: {
            session_id: 'sess_001',
            status: 'locked',
            task_id: 'task_001'
          }
        })
      )
    );

    await expect(getCaptureSession('sess_001')).resolves.toMatchObject({ session_id: 'sess_001' });
    await expect(
      uploadCapturePage('sess_001', {
        file: new File(['image'], 'page.jpg', { type: 'image/jpeg' }),
        width: 1200,
        height: 1600,
        quad_points: [
          { x: 0, y: 0 },
          { x: 1200, y: 0 },
          { x: 1200, y: 1600 },
          { x: 0, y: 1600 }
        ]
      })
    ).resolves.toMatchObject({ page_id: 'page_001' });
    await expect(finishCaptureSession('sess_001')).resolves.toMatchObject({ task_id: 'task_001' });
  });

  it('loads task detail and retries failed processing', async () => {
    server.use(
      http.get('*/api/tasks/task_failed', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            session_id: 'sess_failed',
            status: 'failed',
            created_at: '2026-05-14T10:00:00+08:00',
            page_count: 2,
            error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
            error_message: '图像处理模块未配置'
          }
        })
      ),
      http.post('*/api/tasks/task_failed/retry', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            status: 'processing'
          }
        })
      )
    );

    await expect(getTaskDetail('task_failed')).resolves.toMatchObject({ status: 'failed' });
    await expect(retryTaskProcessing('task_failed')).resolves.toMatchObject({ status: 'processing' });
  });

  it('loads review result, saves a field and confirms review', async () => {
    server.use(
      http.get('*/api/tasks/task_ready/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_ready',
            fields: [
              {
                field_key: 'chief_complaint',
                label: '主诉',
                candidate_value: '头痛三天',
                final_value: '',
                status: 'unreviewed',
                evidence: []
              }
            ],
            summary: { unreviewed: 1, suspicious: 0, empty: 0, confirmed: 0 }
          }
        })
      ),
      http.put('*/api/tasks/task_ready/review/fields/chief_complaint', async ({ request }) => {
        await expect(request.json()).resolves.toMatchObject({
          final_value: '头痛三天',
          status: 'confirmed'
        });
        return HttpResponse.json({
          success: true,
          data: {
            field_key: 'chief_complaint',
            final_value: '头痛三天',
            status: 'confirmed'
          }
        });
      }),
      http.post('*/api/tasks/task_ready/review/confirm', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_ready',
            status: 'confirmed'
          }
        })
      )
    );

    await expect(getReviewResult('task_ready')).resolves.toMatchObject({ task_id: 'task_ready' });
    await expect(
      saveReviewField('task_ready', 'chief_complaint', {
        final_value: '头痛三天',
        status: 'confirmed'
      })
    ).resolves.toMatchObject({ status: 'confirmed' });
    await expect(confirmReview('task_ready')).resolves.toMatchObject({ status: 'confirmed' });
  });

  it('normalizes API errors without leaking technical details', () => {
    const message = normalizeApiError({
      code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
      message: 'Traceback: /secret/path',
      details: { raw_text: '完整病历原文' }
    });
    expect(message).toBe('处理模块未配置，请检查本地服务配置后重试。');
    expect(message).not.toContain('Traceback');
    expect(message).not.toContain('完整病历原文');
  });

  it('exports JSON and Excel through backend download endpoints', async () => {
    server.use(
      http.get('*/api/tasks/task_confirmed/export/json', () =>
        new HttpResponse(new Blob(['{}'], { type: 'application/json' }), {
          headers: { 'content-type': 'application/json' }
        })
      ),
      http.get('*/api/tasks/task_confirmed/export/excel', () =>
        new HttpResponse(new Blob(['excel'], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), {
          headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
        })
      )
    );

    await expect(exportTaskJson('task_confirmed')).resolves.toBeInstanceOf(Blob);
    await expect(exportTaskExcel('task_confirmed')).resolves.toBeInstanceOf(Blob);
  });
});
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/api/shared-contracts.test.ts
```

Expected: fails because `review.ts`, `export.ts`, `errors.ts`, extended capture session APIs, extended task APIs, and extended status maps do not exist yet.

## Task 2: Implement Shared API And Status Contracts

- [x] **Step 1: Extend `app/frontend/src/styles/status.ts`**

Define `taskStatusMeta`, `sessionStatusMeta`, `fieldStatusMeta`, and `exportStatusMeta`. Keep existing exports used by FE-01.

- [x] **Step 2: Extend `app/frontend/src/api/captureSessions.ts`**

Add:

- `getCaptureSession(sessionId: string)`
- `uploadCapturePage(sessionId: string, input: CapturePageUploadInput)`
- `finishCaptureSession(sessionId: string)`

Use `FormData` for uploads. Serialize `quad_points` exactly with `JSON.stringify(input.quad_points)`.

- [x] **Step 3: Extend `app/frontend/src/api/tasks.ts`**

Add:

- `getTaskDetail(taskId: string)`
- `retryTaskProcessing(taskId: string)`

Do not invent task states outside `TaskStatus`.

- [x] **Step 4: Add `app/frontend/src/api/review.ts`**

Add:

- `getReviewResult(taskId: string)`
- `saveReviewField(taskId: string, fieldKey: string, input: SaveReviewFieldInput)`
- `confirmReview(taskId: string)`

The types must preserve candidate value and final value separately.

- [x] **Step 5: Add `app/frontend/src/api/export.ts`**

Add:

- `exportTaskJson(taskId: string): Promise<Blob>`
- `exportTaskExcel(taskId: string): Promise<Blob>`

Use `fetch` directly or a new client helper because existing `apiRequest` expects JSON. Do not create Excel content in the frontend.

- [x] **Step 6: Add `app/frontend/src/api/errors.ts`**

Add `normalizeApiError(error)` that maps known codes to safe Chinese messages and never returns stack traces, raw OCR text, image base64, or model output.

- [x] **Step 7: Run the focused test and verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/api/shared-contracts.test.ts
```

Expected: `shared-contracts.test.ts` passes.

## Task 3: Add Route Skeleton Tests

- [x] **Step 1: Create `app/frontend/src/app/routes.test.ts`**

Add:

```ts
import { describe, expect, it } from 'vitest';

import {
  appRoutes,
  buildMobileSessionPath,
  buildReviewPath,
  buildTaskExportPath
} from './routes';

describe('frontend route skeleton', () => {
  it('defines stable top-level routes for next-stage pages', () => {
    expect(appRoutes.workstation.path).toBe('/');
    expect(appRoutes.mobileCapture.path).toBe('/mobile/sessions/:sessionId');
    expect(appRoutes.tasks.path).toBe('/tasks');
    expect(appRoutes.review.path).toBe('/tasks/:taskId/review');
    expect(appRoutes.export.path).toBe('/tasks/:taskId/export');
  });

  it('builds encoded paths for dynamic routes', () => {
    expect(buildMobileSessionPath('sess 001')).toBe('/mobile/sessions/sess%20001');
    expect(buildReviewPath('task/001')).toBe('/tasks/task%2F001/review');
    expect(buildTaskExportPath('task/001')).toBe('/tasks/task%2F001/export');
  });
});
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd app/frontend
npm run test -- src/app/routes.test.ts
```

Expected: fails because these route exports do not exist yet.

## Task 4: Implement Route Skeleton

- [x] **Step 1: Update `app/frontend/src/app/routes.tsx`**

Add route metadata and path builders for:

- `/`
- `/mobile/sessions/:sessionId`
- `/tasks`
- `/tasks/:taskId/review`
- `/tasks/:taskId/export`

- [x] **Step 2: Add placeholder pages**

Create:

- `app/frontend/src/pages/mobile-capture/MobileCapturePlaceholder.tsx`
- `app/frontend/src/pages/tasks/TasksPlaceholder.tsx`
- `app/frontend/src/pages/review/ReviewPlaceholder.tsx`
- `app/frontend/src/pages/export/ExportPlaceholder.tsx`

Each placeholder must be plain and non-business:

```tsx
export function MobileCapturePlaceholder() {
  return <main aria-label="手机采集页">手机采集功能待实现</main>;
}
```

Use matching labels/text for each page. Do not add real UI workflows.

- [x] **Step 3: Run route tests and verify GREEN**

Run:

```bash
cd app/frontend
npm run test -- src/app/routes.test.ts
```

Expected: route skeleton tests pass.

## Task 5: Update Fixtures And README

- [x] **Step 1: Add fixture files**

Create or extend:

- `app/frontend/tests/fixtures/review.ts`
- `app/frontend/tests/fixtures/export.ts`
- `app/frontend/tests/fixtures/sessions.ts`
- `app/frontend/tests/fixtures/tasks.ts`

Fixtures must use synthetic data only. Do not include full medical record text, ID numbers, image base64, raw model output, or real patient data.

- [x] **Step 2: Update `app/frontend/README.md`**

Add a short “下一阶段契约层” section:

```md
## 下一阶段契约层

- `src/api/` 已预留手机采集、任务、审核和导出 API 边界。
- `src/app/routes.tsx` 固定工作台、手机采集、任务列表、审核、导出路由。
- 页面实现仍按 FE-02 到 FE-05 分阶段推进；契约层不实现 OCR、图像处理、字段推断或前端 Excel 生成。
```

- [x] **Step 3: Run full component test suite**

Run:

```bash
cd app/frontend
npm run test
```

Expected: all Vitest tests pass.

## Task 6: Final Verification And Commit

- [x] **Step 1: Run quality gates**

Run:

```bash
cd app/frontend
npm run test
npm run typecheck
npm run build
```

Expected:

- Vitest passes.
- TypeScript emits no errors.
- Vite build completes.

- [x] **Step 2: Run static offline scan**

Run:

```bash
cd /home/kbzz1/manzufei_ocr
rg -n "https?://|cdn|unpkg|telemetry|analytics|fonts.googleapis|fonts.gstatic" app/frontend/src app/frontend/index.html app/frontend/README.md app/frontend/package.json app/frontend/vite.config.ts
```

Expected: only local test/config loopback URLs, if any. No CDN, remote font, telemetry, analytics, or public API URL.

- [x] **Step 3: Record E2E status**

Run:

```bash
cd app/frontend
timeout 30s npm run test:e2e
```

Expected in current Codex sandbox: exit code `124` with no Playwright test output. If it passes in a different environment, update README and PRD task notes with the exact result.

- [x] **Step 4: Commit**

Run:

```bash
git add app/frontend/src/api app/frontend/src/app app/frontend/src/pages app/frontend/src/styles app/frontend/tests app/frontend/README.md docs/superpowers/plans/2026-05-14-frontend-shared-contracts-routing-plan.md
git commit -m "完善前端共享契约和路由骨架"
```

Do not add `node_modules/`, `dist/`, `data/`, `exports/`, `logs/`, or unrelated design assets.

## Self-Review

- This plan covers S1 shared frontend contract layer and S2 route skeleton from the orchestration spec.
- This plan intentionally leaves P1 to P5 page implementation for later plans.
- The planned API functions do not implement OCR, LLM extraction, image processing, frontend field inference, or frontend Excel generation.
- Every implementation task has a focused RED/GREEN test path.
