# Workstation Mobile Completion Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining PRD/BDD gaps in the computer workstation homepage and mobile capture page without expanding into task review or export workflows.

**Architecture:** Backend extends capture session detail responses with safe page metadata for saved quad replay. Frontend adds real pointer-based quad dragging, initializes uploaded pages from saved metadata, and adds workstation retry/help/placeholder controls through existing React state and component boundaries.

**Tech Stack:** Flask, local JSON storage, pytest, React 18, TypeScript, Vitest, React Testing Library, MSW, CSS.

---

## File Structure

Backend:

- Modify: `app/backend/services/session_service.py`
  - Merge safe upload metadata into `GET /api/capture-sessions/{session_id}` session pages.
- Test: `app/backend/tests/test_capture_session.py`
  - Add session detail tests for page metadata, missing metadata tolerance, and path privacy.

Frontend mobile:

- Modify: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`
  - Add pointer drag interaction and coordinate clamping.
- Create: `app/frontend/src/components/mobile-capture/QuadSelector.test.tsx`
  - Unit/interaction tests for dragging and clamping.
- Modify: `app/frontend/src/api/captureSessions.ts`
  - Add optional `image_width`, `image_height`, `quad_points` to session page type.
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
  - Initialize uploaded pages from saved page metadata.
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
  - Add saved quad replay test.
- Modify: `app/frontend/tests/fixtures/sessions.ts`
  - Allow session page fixtures with optional metadata.

Frontend workstation:

- Modify: `app/frontend/src/app/App.tsx`
  - Extract reload function, add retry state, pass LAN addresses and retry handler.
- Modify: `app/frontend/src/pages/workstation/workstation.types.ts`
  - Add workstation LAN address and optional manual QR state types only if needed by props.
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
  - Pass retry, LAN address, and end-session placeholder props.
- Modify: `app/frontend/src/components/workstation/WorkstationHero.tsx`
  - Render retry and end-session placeholder.
- Modify: `app/frontend/src/components/workstation/CaptureQrDialog.tsx`
  - Add LAN address choices and editable URL override.
- Modify: `app/frontend/src/app/App.test.tsx`
  - Add workstation retry/help/end-session tests.

Validation:

- Backend focused: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py app/backend/tests/test_api_contracts.py -q`
- Frontend focused: `npm run test -- QuadSelector.test.tsx MobileCapturePage.test.tsx App.test.tsx`
- Frontend full: `npm run test`, `npm run typecheck`, `npm run build`
- Repo: `git diff --check`

---

### Task 1: Backend Session Page Metadata Replay

**Files:**
- Modify: `app/backend/services/session_service.py`
- Test: `app/backend/tests/test_capture_session.py`

- [ ] **Step 1: Write failing test for page metadata in session detail**

Append this test to `app/backend/tests/test_capture_session.py`:

```python
def test_get_session_includes_safe_page_quad_metadata(client):
    created = create_session(client)
    sid = created["session_id"]
    upload = client.post(
        f"/api/mobile/{sid}/pages",
        data={
            "image": (io.BytesIO(b"\xff\xd8\xff\xe0" + b"\x00" * 100), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
            "quad_points": json.dumps([
                {"x": 100, "y": 100},
                {"x": 1800, "y": 100},
                {"x": 1800, "y": 900},
                {"x": 100, "y": 900},
            ]),
        },
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    resp = client.get(f"/api/capture-sessions/{sid}")

    assert resp.status_code == 200
    page = resp.get_json()["data"]["pages"][0]
    assert page["image_width"] == 1920
    assert page["image_height"] == 1080
    assert page["quad_points"] == [
        {"x": 100, "y": 100},
        {"x": 1800, "y": 100},
        {"x": 1800, "y": 900},
        {"x": 100, "y": 900},
    ]
    assert "original_image_path" not in page
```

If `io` or `json` are not already present in this test file, add them at the top. Use the existing `create_session(client)` helper from `test_capture_session.py`; it returns the full session data dict.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py::test_get_session_includes_safe_page_quad_metadata -q
```

Expected: FAIL because session pages currently omit `image_width`, `image_height`, and `quad_points`.

- [ ] **Step 3: Implement safe metadata merge**

In `app/backend/services/session_service.py`, locate the method used by `GET /api/capture-sessions/{session_id}` to return a session dict. Add a helper inside `SessionService`:

```python
    def _with_safe_page_metadata(self, session: dict) -> dict:
        pages = []
        for page in session.get("pages", []):
            enriched = dict(page)
            upload_ref = page.get("upload_ref")
            if upload_ref:
                meta = self._store.read(upload_ref)
                if isinstance(meta, dict):
                    if "image_width" in meta:
                        enriched["image_width"] = meta["image_width"]
                    if "image_height" in meta:
                        enriched["image_height"] = meta["image_height"]
                    if "quad_points" in meta:
                        enriched["quad_points"] = meta["quad_points"]
            pages.append(enriched)
        return {**session, "pages": pages}
```

Then update the public `get()` response path to return `self._with_safe_page_metadata(session)` after existing expiration/status handling. Do not include `original_image_path`, `processed_image_path`, or absolute file paths in the enriched page response.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py::test_get_session_includes_safe_page_quad_metadata -q
```

Expected: PASS.

- [ ] **Step 5: Add missing metadata tolerance test**

Append:

```python
def test_get_session_tolerates_missing_page_metadata(client):
    created_session = create_session(client)
    sid = created_session["session_id"]
    created = client.post(f"/api/capture-sessions/{sid}/pages")
    assert created.status_code == 200

    resp = client.get(f"/api/capture-sessions/{sid}")

    assert resp.status_code == 200
    page = resp.get_json()["data"]["pages"][0]
    assert page["page_id"]
    assert "image_width" not in page
    assert "original_image_path" not in page
```

- [ ] **Step 6: Run backend session tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py -q
```

Expected: all tests in `test_capture_session.py` pass.

- [ ] **Step 7: Commit**

```bash
git add app/backend/services/session_service.py app/backend/tests/test_capture_session.py
git commit -m "补齐采集会话页面框选元数据"
```

---

### Task 2: QuadSelector Pointer Drag

**Files:**
- Modify: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`
- Create: `app/frontend/src/components/mobile-capture/QuadSelector.test.tsx`

- [ ] **Step 1: Write failing drag test**

Create `app/frontend/src/components/mobile-capture/QuadSelector.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { createDefaultQuad, QuadSelector, type QuadPointsByCorner } from './QuadSelector';

function setSvgRect(element: Element) {
  Object.defineProperty(element, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({
      left: 0,
      top: 0,
      width: 100,
      height: 140,
      right: 100,
      bottom: 140,
      x: 0,
      y: 0,
      toJSON: () => {}
    })
  });
}

function pointer(type: string, x: number, y: number) {
  if (typeof PointerEvent === 'function') {
    return new PointerEvent(type, {
      bubbles: true,
      pointerId: 1,
      clientX: x,
      clientY: y
    });
  }

  const event = new Event(type, { bubbles: true }) as PointerEvent;
  Object.defineProperty(event, 'pointerId', { value: 1 });
  Object.defineProperty(event, 'clientX', { value: x });
  Object.defineProperty(event, 'clientY', { value: y });
  return event;
}

describe('QuadSelector', () => {
  it('updates the dragged corner and redraws the polygon', () => {
    const onChange = vi.fn();
    const points = createDefaultQuad(1000, 1400);
    render(<QuadSelector width={1000} height={1400} points={points} onChange={onChange} />);
    const overlay = screen.getByLabelText('四边形框选叠加层');
    setSvgRect(overlay);
    Object.defineProperty(overlay, 'setPointerCapture', { configurable: true, value: vi.fn() });
    Object.defineProperty(overlay, 'releasePointerCapture', { configurable: true, value: vi.fn() });

    overlay.dispatchEvent(pointer('pointerdown', 10, 14));
    overlay.dispatchEvent(pointer('pointermove', 20, 28));
    overlay.dispatchEvent(pointer('pointerup', 20, 28));

    expect(onChange).toHaveBeenCalledWith({
      ...points,
      tl: { x: 200, y: 280 }
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run from `app/frontend/`:

```bash
npm run test -- QuadSelector.test.tsx
```

Expected: FAIL because `QuadSelector` has no pointer handlers.

- [ ] **Step 3: Implement pointer drag**

Update `app/frontend/src/components/mobile-capture/QuadSelector.tsx`:

```tsx
import { useId, useMemo, useRef, useState } from 'react';
```

Inside `QuadSelector`, add:

```tsx
  const svgRef = useRef<SVGSVGElement>(null);
  const [activeCorner, setActiveCorner] = useState<QuadCorner | null>(null);

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value));
  }

  function eventToPoint(event: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return {
      x: clamp(Math.round(((event.clientX - rect.left) / rect.width) * width), 0, width),
      y: clamp(Math.round(((event.clientY - rect.top) / rect.height) * height), 0, height)
    };
  }

  function nearestCorner(point: { x: number; y: number }) {
    return cornerOrder.reduce((nearest, corner) => {
      const current = points[corner];
      const nearestPoint = points[nearest];
      const currentDistance = (current.x - point.x) ** 2 + (current.y - point.y) ** 2;
      const nearestDistance = (nearestPoint.x - point.x) ** 2 + (nearestPoint.y - point.y) ** 2;
      return currentDistance < nearestDistance ? corner : nearest;
    }, cornerOrder[0]);
  }

  function handlePointerDown(event: React.PointerEvent<SVGSVGElement>) {
    const point = eventToPoint(event);
    if (!point) return;
    const corner = nearestCorner(point);
    setActiveCorner(corner);
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!activeCorner) return;
    const point = eventToPoint(event);
    if (!point) return;
    onChange({ ...points, [activeCorner]: point });
  }

  function handlePointerEnd(event: React.PointerEvent<SVGSVGElement>) {
    if (activeCorner) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    setActiveCorner(null);
  }
```

Then add these props to the `<svg>`:

```tsx
        ref={svgRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
```

- [ ] **Step 4: Run drag test**

Run:

```bash
npm run test -- QuadSelector.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Add clamp test**

Append to `QuadSelector.test.tsx`:

```tsx
  it('clamps dragged corners inside the image bounds', () => {
    const onChange = vi.fn();
    const points = createDefaultQuad(1000, 1400);
    render(<QuadSelector width={1000} height={1400} points={points} onChange={onChange} />);
    const overlay = screen.getByLabelText('四边形框选叠加层');
    setSvgRect(overlay);
    Object.defineProperty(overlay, 'setPointerCapture', { configurable: true, value: vi.fn() });
    Object.defineProperty(overlay, 'releasePointerCapture', { configurable: true, value: vi.fn() });

    overlay.dispatchEvent(pointer('pointerdown', 10, 14));
    overlay.dispatchEvent(pointer('pointermove', -50, 200));

    expect(onChange).toHaveBeenCalledWith({
      ...points,
      tl: { x: 0, y: 1400 }
    });
  });
```

- [ ] **Step 6: Run focused tests and typecheck**

Run:

```bash
npm run test -- QuadSelector.test.tsx
npm run typecheck
```

Expected: both pass.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/components/mobile-capture/QuadSelector.tsx app/frontend/src/components/mobile-capture/QuadSelector.test.tsx
git commit -m "补齐手机框选四角拖动"
```

---

### Task 3: Mobile Saved Quad Replay

**Files:**
- Modify: `app/frontend/src/api/captureSessions.ts`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
- Modify: `app/frontend/tests/fixtures/sessions.ts`

- [ ] **Step 1: Add failing saved quad replay test**

Append to `MobileCapturePage.test.tsx`:

```tsx
it('opens re-quad with saved backend quad points', async () => {
  let updatedQuad: Array<{ x: number; y: number }> | null = null;
  server.use(
    mockGetCaptureSession({
      ...activeSession,
      page_count: 1,
      pages: [
        {
          page_id: 'page_a',
          page_no: 1,
          image_width: 1000,
          image_height: 1400,
          quad_points: [
            { x: 10, y: 20 },
            { x: 990, y: 30 },
            { x: 980, y: 1380 },
            { x: 20, y: 1370 }
          ]
        }
      ]
    }),
    http.put('*/api/mobile/sess_001/pages/page_a/quad', async ({ request }) => {
      const body = await request.json() as { quad_points: Array<{ x: number; y: number }> };
      updatedQuad = body.quad_points;
      return HttpResponse.json({ success: true, data: { page_id: 'page_a', page_no: 1, quad_points: body.quad_points } });
    })
  );

  renderMobileCapture();
  await screen.findByText('第 1 页');
  await userEvent.setup().click(screen.getByRole('button', { name: '重新框选第 1 页' }));
  await userEvent.setup().click(screen.getByRole('button', { name: '确认框选' }));

  await waitFor(() => expect(updatedQuad).toEqual([
    { x: 10, y: 20 },
    { x: 990, y: 30 },
    { x: 980, y: 1380 },
    { x: 20, y: 1370 }
  ]));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: FAIL because current page initialization uses default quad.

- [ ] **Step 3: Extend capture session API type**

In `app/frontend/src/api/captureSessions.ts`, change `CaptureSession.pages` item type to:

```typescript
  pages?: Array<{
    page_id: string;
    page_no: number;
    image_width?: number;
    image_height?: number;
    quad_points?: QuadPoint[] | null;
  }>;
```

- [ ] **Step 4: Add conversion helper and use saved metadata**

In `MobileCapturePage.tsx`, add:

```typescript
function arrayToQuadByCorner(points: Array<{ x: number; y: number }> | null | undefined, width: number, height: number): QuadPointsByCorner {
  if (!Array.isArray(points) || points.length !== 4) {
    return createDefaultQuad(width, height);
  }
  const [tl, tr, br, bl] = points;
  if (![tl, tr, br, bl].every((point) => Number.isFinite(point?.x) && Number.isFinite(point?.y))) {
    return createDefaultQuad(width, height);
  }
  return { tl, tr, br, bl };
}
```

Then update `toInitialPages()`:

```typescript
function toInitialPages(session: CaptureSession): CapturePageItem[] {
  return (session.pages ?? []).map((page, index) => {
    const width = page.image_width ?? PREVIEW_WIDTH;
    const height = page.image_height ?? PREVIEW_HEIGHT;
    return {
      localId: page.page_id,
      pageId: page.page_id,
      pageNo: index + 1,
      status: 'uploaded',
      width,
      height,
      quad: arrayToQuadByCorner(page.quad_points, width, height)
    };
  });
}
```

- [ ] **Step 5: Run mobile tests**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/api/captureSessions.ts app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx app/frontend/tests/fixtures/sessions.ts
git commit -m "回显已保存页面框选坐标"
```

---

### Task 4: Workstation Status Retry

**Files:**
- Modify: `app/frontend/src/app/App.tsx`
- Modify: `app/frontend/src/components/workstation/WorkstationHero.tsx`
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- Test: `app/frontend/src/app/App.test.tsx`

- [ ] **Step 1: Add failing retry test**

Append to `App.test.tsx`:

```tsx
it('retries system status loading after service no response', async () => {
  const user = userEvent.setup();
  let statusCalls = 0;
  server.use(
    http.get('*/api/system/status', () => {
      statusCalls += 1;
      if (statusCalls === 1) {
        return HttpResponse.error();
      }
      return HttpResponse.json({
        success: true,
        data: {
          status: 'running',
          version: 'test',
          started_at: '2026-05-14T10:00:00+08:00',
          lan_addresses: ['192.168.1.5:8081']
        }
      });
    }),
    mockTasks([])
  );

  render(<App />);
  expect(await screen.findByText('服务无响应')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: '重试' }));
  expect(await screen.findByText('系统已启动')).toBeTruthy();
  expect(statusCalls).toBe(2);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: FAIL because no retry button exists.

- [ ] **Step 3: Extract dashboard reload function**

In `App.tsx`, add state:

```typescript
const [isRetryingSystem, setIsRetryingSystem] = useState(false);
```

Replace the `useEffect()` body with a reusable function:

```typescript
async function loadDashboard() {
  try {
    const status = await getSystemStatus();
    setSystemStatus(status);
    setSystemError(status.status === 'running' ? null : status.message ?? '系统状态异常');
  } catch (error: unknown) {
    setSystemStatus(null);
    setSystemError(getErrorMessage(error, '服务无响应'));
  }

  try {
    const nextTasks = await getTasks();
    setTasks(nextTasks);
    setTaskError(null);
  } catch (error: unknown) {
    setTasks([]);
    setTaskError(getErrorMessage(error, '任务列表加载失败'));
  }
}

useEffect(() => {
  void loadDashboard();
}, []);

async function handleRetrySystem() {
  setIsRetryingSystem(true);
  await loadDashboard();
  setIsRetryingSystem(false);
}
```

Pass `onRetrySystem={handleRetrySystem}` and `isRetryingSystem={isRetryingSystem}` into `WorkstationPage`.

- [ ] **Step 4: Render retry button in WorkstationHero**

Add props to `WorkstationHero`:

```typescript
isRetryingSystem?: boolean;
onRetrySystem?: () => void;
```

Render after the status grid:

```tsx
{systemStatus.startup === 'error' ? (
  <button className="secondary-action" type="button" disabled={isRetryingSystem} onClick={onRetrySystem}>
    {isRetryingSystem ? '正在重试' : '重试'}
  </button>
) : null}
```

Thread the props through `WorkstationPage.tsx`.

- [ ] **Step 5: Run App tests**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/app/App.tsx app/frontend/src/components/workstation/WorkstationHero.tsx app/frontend/src/pages/workstation/WorkstationPage.tsx app/frontend/src/app/App.test.tsx
git commit -m "补齐工作台状态重试入口"
```

---

### Task 5: QR Help Address Selection and Manual URL

**Files:**
- Modify: `app/frontend/src/app/App.tsx`
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- Modify: `app/frontend/src/components/workstation/CaptureQrDialog.tsx`
- Test: `app/frontend/src/app/App.test.tsx`

- [ ] **Step 1: Add failing QR help test**

Append to `App.test.tsx`:

```tsx
it('lets connection help choose LAN address and manually edit mobile URL', async () => {
  const user = userEvent.setup();
  server.use(
    mockSystemStatus({
      success: true,
      data: {
        status: 'running',
        version: 'test',
        started_at: '2026-05-14T10:00:00+08:00',
        lan_addresses: ['192.168.1.5:8081', '10.0.0.8:8081']
      }
    }),
    mockTasks([]),
    mockCreateCaptureSession()
  );
  render(<App />);

  await user.click(await screen.findByRole('button', { name: /新建采集/ }));
  const dialog = await screen.findByRole('dialog', { name: '采集二维码' });
  await user.click(within(dialog).getByRole('button', { name: '手机无法连接？' }));

  expect(within(dialog).getByRole('button', { name: '192.168.1.5:8081' })).toBeTruthy();
  await user.click(within(dialog).getByRole('button', { name: '10.0.0.8:8081' }));
  expect((within(dialog).getByLabelText('手机访问链接') as HTMLInputElement).value).toContain('10.0.0.8:8081');

  await user.clear(within(dialog).getByLabelText('手机访问链接'));
  await user.type(within(dialog).getByLabelText('手机访问链接'), 'http://192.168.1.9:8081/mobile/sessions/sess_001');
  await user.click(within(dialog).getByRole('button', { name: '重新生成二维码' }));

  const qrImage = within(dialog).getByRole('img', { name: '采集二维码' }) as HTMLImageElement;
  expect(qrImage.dataset.qrValue).toBe('http://192.168.1.9:8081/mobile/sessions/sess_001');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: FAIL because LAN address choices and editable QR override do not exist.

- [ ] **Step 3: Pass LAN addresses into dialog**

In `WorkstationPage.tsx`, add prop:

```typescript
lanAddresses?: string[];
```

Pass `lanAddresses={lanAddresses}` into `CaptureQrDialog`.

In `App.tsx`, pass `lanAddresses={systemStatus?.lan_addresses ?? []}` into `WorkstationPage`.

- [ ] **Step 4: Implement QR override state**

In `CaptureQrDialog.tsx`, add props:

```typescript
lanAddresses?: string[];
```

Add state:

```typescript
const [manualUrl, setManualUrl] = useState('');
const [qrValueOverride, setQrValueOverride] = useState<string | null>(null);
const [manualUrlError, setManualUrlError] = useState<string | null>(null);
const qrValue = qrValueOverride ?? session?.qrCodeValue ?? '';
```

Use `qrValue` instead of `session.qrCodeValue` when generating QR and copying.

When dialog opens or session changes:

```typescript
setQrValueOverride(null);
setManualUrl(session?.qrCodeValue ?? '');
setManualUrlError(null);
```

Add helpers:

```typescript
function buildUrlForAddress(address: string) {
  if (!session) return '';
  return `http://${address}/mobile/sessions/${encodeURIComponent(session.id)}`;
}

function applyManualUrl() {
  try {
    const parsed = new URL(manualUrl);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      throw new Error('invalid protocol');
    }
    setQrValueOverride(parsed.toString());
    setManualUrlError(null);
  } catch {
    setManualUrlError('请输入有效的手机访问链接');
  }
}
```

In help panel, render:

```tsx
{lanAddresses.length > 0 ? (
  <div className="qr-help-panel__addresses" aria-label="局域网地址列表">
    {lanAddresses.map((address) => (
      <button
        className="secondary-action"
        key={address}
        type="button"
        onClick={() => {
          const nextUrl = buildUrlForAddress(address);
          setManualUrl(nextUrl);
          setQrValueOverride(nextUrl);
          setManualUrlError(null);
        }}
      >
        {address}
      </button>
    ))}
  </div>
) : null}
<input
  id="mobile-capture-url"
  value={manualUrl}
  onChange={(event) => setManualUrl(event.currentTarget.value)}
/>
<button className="secondary-action" type="button" onClick={applyManualUrl}>
  重新生成二维码
</button>
{manualUrlError ? <span role="alert">{manualUrlError}</span> : null}
```

Keep the existing copy button, but copy `qrValue`.

- [ ] **Step 5: Run App tests**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/app/App.tsx app/frontend/src/pages/workstation/WorkstationPage.tsx app/frontend/src/components/workstation/CaptureQrDialog.tsx app/frontend/src/app/App.test.tsx
git commit -m "补齐二维码连接帮助地址选择"
```

---

### Task 6: Current Session End Placeholder

**Files:**
- Modify: `app/frontend/src/components/workstation/WorkstationHero.tsx`
- Modify: `app/frontend/src/pages/workstation/WorkstationPage.tsx`
- Test: `app/frontend/src/app/App.test.tsx`

- [ ] **Step 1: Add failing placeholder test**

Append to `App.test.tsx`:

```tsx
it('shows end session placeholder on current active session card', async () => {
  const user = userEvent.setup();
  server.use(mockSystemStatus(), mockTasks([]), mockCreateCaptureSession());
  render(<App />);

  await user.click(await screen.findByRole('button', { name: /新建采集/ }));
  await user.click(await screen.findByRole('button', { name: '关闭' }));
  await user.click(screen.getByRole('button', { name: '结束会话' }));

  expect(screen.getByText('请在手机端点击完成采集；如需作废，请重新生成二维码。')).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: FAIL because no “结束会话” button exists.

- [ ] **Step 3: Add placeholder action**

In `WorkstationHero.tsx`, add local state:

```tsx
import { useState } from 'react';
```

Inside component:

```tsx
const [endSessionHint, setEndSessionHint] = useState(false);
```

Inside `.session-summary__actions`, after “查看二维码”:

```tsx
<button className="secondary-action" type="button" onClick={() => setEndSessionHint(true)}>
  结束会话
</button>
```

Under the actions or summary:

```tsx
{endSessionHint ? (
  <p className="inline-hint">请在手机端点击完成采集；如需作废，请重新生成二维码。</p>
) : null}
```

- [ ] **Step 4: Run test**

Run:

```bash
npm run test -- App.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/components/workstation/WorkstationHero.tsx app/frontend/src/app/App.test.tsx
git commit -m "增加当前采集会话结束占位"
```

---

### Task 7: Full Verification and Documentation Sync

**Files:**
- Modify if needed: `docs/PRD任务清单.md`
- Modify if needed: `docs/superpowers/specs/2026-05-14-workstation-mobile-completion-gaps-design.md`

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py app/backend/tests/test_api_contracts.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend tests**

Run from `app/frontend/`:

```bash
npm run test
```

Expected: all Vitest tests pass.

- [ ] **Step 3: Run frontend typecheck**

Run from `app/frontend/`:

```bash
npm run typecheck
```

Expected: command exits with code 0.

- [ ] **Step 4: Run frontend build**

Run from `app/frontend/`:

```bash
npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 5: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Update PRD checklist only if all checks pass**

If all checks pass, update `docs/PRD任务清单.md` notes for `FE-01` and `FE-02` to mention:

- real quad drag is implemented,
- saved quad replay is implemented,
- workstation retry and connection-help override are implemented,
- “结束会话” remains an intentional placeholder until a backend cancel/session-end API is defined.

- [ ] **Step 7: Commit verification/docs**

If Step 6 changed docs:

```bash
git add docs/PRD任务清单.md docs/superpowers/specs/2026-05-14-workstation-mobile-completion-gaps-design.md
git commit -m "同步首页和手机采集页缺口验收状态"
```

If Step 6 made no doc changes, do not create an empty commit.

---

## Plan 自审

- **Spec coverage**：P0 mobile gaps are covered by Tasks 1-3; P1 workstation gaps are covered by Tasks 4-6; verification and doc sync are covered by Task 7.
- **Placeholder scan**：No `TBD`, `TODO`, “implement later”, or vague “add tests” steps remain. Each task has concrete files, code snippets, commands, and expected results.
- **Type consistency**：The plan uses `QuadPoint`, `QuadPointsByCorner`, `CaptureSession.pages[].quad_points`, `lanAddresses`, and `qrValueOverride` consistently across tasks.
- **Boundary check**：No task implements OCR, image processing, cancellation backend APIs, review, export, or task list work.
