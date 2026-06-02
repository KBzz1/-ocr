# Mobile Capture UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the mobile capture page to match the 2026-05-14 UX spec and mobile PNG references, including single image entry, simplified quad selection, inline page actions, drag sorting, re-quad, current-page replacement capture, and non-fixed footer actions.

**Architecture:** Backend adds two page-edit endpoints for active capture sessions: update quad only, and replace a page image while preserving page identity and order. Frontend extracts mobile capture into focused components and API wrappers; `MobileCapturePage` keeps state orchestration while presentational components own UI and events. CSS follows the three mobile PNG references and removes engineering controls from the visible mobile UI.

**Tech Stack:** Flask, local JSON storage, pytest, React 18, TypeScript, Vitest, React Testing Library, MSW, CSS.

---

## File Structure

Backend:

- Modify: `app/backend/services/page_service.py` for `update_quad()` and `replace_image()`.
- Modify: `app/backend/routes/mobile.py` for `PUT /api/mobile/<session_id>/pages/<page_id>/quad` and `PUT /api/mobile/<session_id>/pages/<page_id>/image`.
- Modify: `app/backend/tests/test_page_service.py` for service-level metadata replacement and rollback tests.
- Modify: `app/backend/tests/test_mobile_pages.py` for API contract tests.
- Modify only if needed: `app/backend/tests/fixtures/client.py` to add a helper for uploading a page and returning `session_id/page_id`.

Frontend:

- Create: `app/frontend/src/pages/mobile-capture/mobileCapture.types.ts`.
- Create: `app/frontend/src/pages/mobile-capture/mobileCaptureApi.ts`.
- Create: `app/frontend/src/pages/mobile-capture/CapturePhotoButton.tsx`.
- Create: `app/frontend/src/pages/mobile-capture/CaptureQuadScreen.tsx`.
- Create: `app/frontend/src/pages/mobile-capture/CapturePageItem.tsx`.
- Create: `app/frontend/src/pages/mobile-capture/CapturePageList.tsx`.
- Create: `app/frontend/src/pages/mobile-capture/CaptureFooter.tsx`.
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`.
- Modify: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`.
- Modify: `app/frontend/src/pages/mobile-capture/mobile-capture.css`.
- Add/modify tests under `app/frontend/src/pages/mobile-capture/`.
- Modify: `app/frontend/tests/fixtures/uploads.ts` for `mockUpdateCapturePageQuad()` and `mockReplaceCapturePageImage()`.

Validation:

- Backend: `conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py app/backend/tests/test_api_contracts.py -q`
- Frontend: from `app/frontend/`, run `npm run test`, `npm run typecheck`, `npm run build`
- Repo: `git diff --check`

---

### Task 1: Backend PageService Quad Update

**Files:**
- Modify: `app/backend/services/page_service.py`
- Modify: `app/backend/tests/test_page_service.py`

- [ ] **Step 1: Write failing service tests**

Append these tests to `app/backend/tests/test_page_service.py` after `TestPageService`:

```python
class TestPageServiceQuadUpdate:
    def test_update_quad_preserves_image_and_page_order(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        ps.save(session["session_id"], page["page_id"], page["page_no"], _make_jpg(), 1920, 1080)

        new_quad = json.dumps([
            {"x": 100, "y": 100},
            {"x": 1800, "y": 100},
            {"x": 1800, "y": 900},
            {"x": 100, "y": 900},
        ])

        updated = ps.update_quad(session["session_id"], page["page_id"], new_quad)

        assert updated["page_id"] == page["page_id"]
        assert updated["page_no"] == 1
        assert updated["quad_points"] == [
            {"x": 100, "y": 100},
            {"x": 1800, "y": 100},
            {"x": 1800, "y": 900},
            {"x": 100, "y": 900},
        ]
        assert updated["quad_updated_at"] is not None
        current = ss.get(session["session_id"])
        assert current["pages"][0]["page_id"] == page["page_id"]
        assert current["pages"][0]["page_no"] == 1

    def test_update_quad_rejects_invalid_points_without_changing_metadata(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode

        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(
            session["session_id"],
            page["page_id"],
            page["page_no"],
            _make_jpg(),
            1920,
            1080,
            quad_points_raw=json.dumps([[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
        )

        with pytest.raises(AppError) as exc_info:
            ps.update_quad(session["session_id"], page["page_id"], "not json")

        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code
        meta = ps._store.read(f"data/pages/{session['session_id']}/{page['page_id']}.json")
        assert meta["quad_points"] == original["quad_points"]
        assert "quad_updated_at" not in meta
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py::TestPageServiceQuadUpdate -q
```

Expected: both tests fail with `AttributeError: 'PageService' object has no attribute 'update_quad'`.

- [ ] **Step 3: Implement `update_quad()`**

Add this method to `PageService` in `app/backend/services/page_service.py`:

```python
    def update_quad(
        self,
        session_id: str,
        page_id: str,
        quad_points_raw: str | None,
    ) -> dict:
        session = self._session_service.get(session_id)
        page = next((p for p in session.get("pages", []) if p.get("page_id") == page_id), None)
        if page is None or not page.get("upload_ref"):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        meta = self._store.read(page["upload_ref"])
        if meta is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        quad_points = validate_quad_points(
            quad_points_raw,
            int(meta["image_width"]),
            int(meta["image_height"]),
            self._min_quad_area_ratio,
        )
        meta["quad_points"] = quad_points
        meta["quad_updated_at"] = datetime.now(timezone.utc).isoformat()
        self._store.write(page["upload_ref"], meta)
        return meta
```

- [ ] **Step 4: Run service tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py::TestPageServiceQuadUpdate -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/page_service.py app/backend/tests/test_page_service.py
git commit -m "新增页面框选坐标更新服务"
```

---

### Task 2: Backend Replace Image Service

**Files:**
- Modify: `app/backend/services/page_service.py`
- Modify: `app/backend/tests/test_page_service.py`

- [ ] **Step 1: Write failing replacement tests**

Append this class to `app/backend/tests/test_page_service.py`:

```python
class TestPageServiceReplaceImage:
    def test_replace_image_preserves_page_id_and_page_no(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(session["session_id"], page["page_id"], page["page_no"], _make_jpg(), 1920, 1080)

        replacement_quad = json.dumps([
            {"x": 50, "y": 60},
            {"x": 950, "y": 60},
            {"x": 950, "y": 1260},
            {"x": 50, "y": 1260},
        ])

        updated = ps.replace_image(
            session["session_id"],
            page["page_id"],
            b"\xff\xd8\xff\xe0" + b"\x11" * 120,
            1000,
            1400,
            replacement_quad,
        )

        assert updated["page_id"] == original["page_id"]
        assert updated["page_no"] == original["page_no"]
        assert updated["image_width"] == 1000
        assert updated["image_height"] == 1400
        assert updated["quad_points"] == [
            {"x": 50, "y": 60},
            {"x": 950, "y": 60},
            {"x": 950, "y": 1260},
            {"x": 50, "y": 1260},
        ]
        assert updated["uploaded_at"] is not None
        assert updated["quad_updated_at"] is not None
        assert ss.get(session["session_id"])["pages"][0]["page_id"] == page["page_id"]

    def test_replace_image_failure_keeps_previous_metadata(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode

        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page = ss.add_page(session["session_id"])["pages"][0]
        original = ps.save(
            session["session_id"],
            page["page_id"],
            page["page_no"],
            _make_jpg(),
            1920,
            1080,
            quad_points_raw=json.dumps([[0, 0], [1920, 0], [1920, 1080], [0, 1080]]),
        )

        with pytest.raises(AppError) as exc_info:
            ps.replace_image(
                session["session_id"],
                page["page_id"],
                b"%PDF-1.4 fake pdf",
                1000,
                1400,
                json.dumps([[0, 0], [1000, 0], [1000, 1400], [0, 1400]]),
            )

        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code
        meta = ps._store.read(f"data/pages/{session['session_id']}/{page['page_id']}.json")
        assert meta["original_image_path"] == original["original_image_path"]
        assert meta["image_width"] == 1920
        assert meta["image_height"] == 1080
        assert meta["quad_points"] == original["quad_points"]
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py::TestPageServiceReplaceImage -q
```

Expected: both tests fail with `AttributeError: 'PageService' object has no attribute 'replace_image'`.

- [ ] **Step 3: Implement `replace_image()`**

Add `import shutil` near the top of `app/backend/services/page_service.py`, then add this method below `update_quad()`:

```python
    def replace_image(
        self,
        session_id: str,
        page_id: str,
        image_data: bytes,
        image_width: int,
        image_height: int,
        quad_points_raw: str | None = None,
    ) -> dict:
        if not isinstance(image_width, int) or image_width <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 必须为正整数")
        if not isinstance(image_height, int) or image_height <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_height 必须为正整数")

        session = self._session_service.get(session_id)
        page = next((p for p in session.get("pages", []) if p.get("page_id") == page_id), None)
        if page is None or not page.get("upload_ref"):
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        previous_meta = self._store.read(page["upload_ref"])
        if previous_meta is None:
            raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")

        validation = self._file_validator.validate(image_data)
        quad_points = validate_quad_points(
            quad_points_raw,
            image_width,
            image_height,
            self._min_quad_area_ratio,
        )
        ext = validation["ext"]
        rel_path = self._file_validator.build_path(session_id, page_id, ext)
        abs_image_path = os.path.join(self._storage_dir, rel_path)
        os.makedirs(os.path.dirname(abs_image_path), exist_ok=True)

        previous_image_path = previous_meta.get("original_image_path")
        new_meta = {
            **previous_meta,
            "page_id": page_id,
            "session_id": session_id,
            "page_no": page["page_no"],
            "original_image_path": abs_image_path,
            "processed_image_path": None,
            "image_width": image_width,
            "image_height": image_height,
            "quad_points": quad_points,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "quad_updated_at": datetime.now(timezone.utc).isoformat(),
        }

        tmp_path = abs_image_path + ".tmp"
        backup_path = abs_image_path + ".bak"
        made_backup = False

        try:
            if previous_image_path == abs_image_path and os.path.isfile(abs_image_path):
                shutil.copy2(abs_image_path, backup_path)
                made_backup = True

            with open(tmp_path, "wb") as f:
                f.write(image_data)
            os.replace(tmp_path, abs_image_path)
            self._store.write(page["upload_ref"], new_meta)
        except Exception:
            self._safe_remove(tmp_path)
            if made_backup and os.path.isfile(backup_path):
                os.replace(backup_path, abs_image_path)
            self._store.write(page["upload_ref"], previous_meta)
            if abs_image_path != previous_image_path:
                self._safe_remove(abs_image_path)
            raise
        finally:
            self._safe_remove(tmp_path)
            self._safe_remove(backup_path)

        if previous_image_path and previous_image_path != abs_image_path:
            self._safe_remove(previous_image_path)

        return new_meta
```

- [ ] **Step 4: Run service tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py::TestPageServiceReplaceImage -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/page_service.py app/backend/tests/test_page_service.py
git commit -m "新增补拍替换页面服务"
```

---

### Task 3: Backend Mobile Page Edit Routes

**Files:**
- Modify: `app/backend/routes/mobile.py`
- Modify: `app/backend/tests/test_mobile_pages.py`

- [ ] **Step 1: Add failing API tests**

Append these tests to `app/backend/tests/test_mobile_pages.py` inside `TestMobilePages`:

```python
    def test_update_quad_route_returns_stable_page_data(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/quad",
            json={
                "quad_points": [
                    {"x": 100, "y": 100},
                    {"x": 1800, "y": 100},
                    {"x": 1800, "y": 900},
                    {"x": 100, "y": 900},
                ]
            },
        )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["page_id"] == page_id
        assert data["page_no"] == 1
        assert data["quad_points"][0] == {"x": 100, "y": 100}
        assert data["quad_updated_at"] is not None

    def test_update_quad_route_rejects_locked_session(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]
        client.post(f"/api/mobile/{sid}/finish")

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/quad",
            json={"quad_points": [{"x": 0, "y": 0}]},
        )

        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_replace_image_route_preserves_page_identity(self, client):
        sid = _create_session(client)
        upload = client.post(
            f"/api/mobile/{sid}/pages",
            data={
                "image": (io.BytesIO(_make_jpg()), "test.jpg"),
                "image_width": "1920",
                "image_height": "1080",
            },
            content_type="multipart/form-data",
        )
        page_id = upload.get_json()["data"]["page_id"]

        resp = client.put(
            f"/api/mobile/{sid}/pages/{page_id}/image",
            data={
                "image": (io.BytesIO(_make_jpg()), "replacement.jpg"),
                "image_width": "1000",
                "image_height": "1400",
                "quad_points": json.dumps([
                    {"x": 50, "y": 60},
                    {"x": 950, "y": 60},
                    {"x": 950, "y": 1260},
                    {"x": 50, "y": 1260},
                ]),
            },
            content_type="multipart/form-data",
        )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["page_id"] == page_id
        assert data["page_no"] == 1
        assert data["image_width"] == 1000
        assert data["image_height"] == 1400
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_mobile_pages.py::TestMobilePages::test_update_quad_route_returns_stable_page_data app/backend/tests/test_mobile_pages.py::TestMobilePages::test_update_quad_route_rejects_locked_session app/backend/tests/test_mobile_pages.py::TestMobilePages::test_replace_image_route_preserves_page_identity -q
```

Expected: route tests fail with HTTP 404.

- [ ] **Step 3: Implement routes**

Add helpers and routes to `app/backend/routes/mobile.py`:

```python
def _parse_dimensions():
    image_width_str = request.form.get("image_width")
    image_height_str = request.form.get("image_height")
    if not image_width_str or not image_height_str:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image_width 或 image_height")

    try:
        return int(image_width_str), int(image_height_str)
    except (ValueError, TypeError):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 和 image_height 必须为整数")
```

Refactor `upload_page()` to use `_parse_dimensions()`:

```python
    image_width, image_height = _parse_dimensions()
```

Add `import json` near the top of `app/backend/routes/mobile.py`, then add these routes:

```python
@mobile_bp.route("/api/mobile/<session_id>/pages/<page_id>/quad", methods=["PUT"])
def update_page_quad(session_id: str, page_id: str):
    _service()._ensure_editable(_service().get(session_id))
    payload = request.get_json(silent=True) or {}
    result = _page_service().update_quad(
        session_id=session_id,
        page_id=page_id,
        quad_points_raw=json.dumps(payload.get("quad_points")),
    )
    return success(
        data={
            "page_id": result["page_id"],
            "page_no": result["page_no"],
            "quad_points": result["quad_points"],
            "quad_updated_at": result.get("quad_updated_at"),
        }
    )


@mobile_bp.route("/api/mobile/<session_id>/pages/<page_id>/image", methods=["PUT"])
def replace_page_image(session_id: str, page_id: str):
    _service()._ensure_editable(_service().get(session_id))
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_width, image_height = _parse_dimensions()
    image_data = request.files["image"].read()
    result = _page_service().replace_image(
        session_id=session_id,
        page_id=page_id,
        image_data=image_data,
        image_width=image_width,
        image_height=image_height,
        quad_points_raw=request.form.get("quad_points"),
    )
    return success(data=result)
```

The route uses the existing session edit guard so locked and expired sessions return the same errors as upload/delete/sort.

- [ ] **Step 4: Run mobile page route tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_mobile_pages.py -q
```

Expected: all tests in `test_mobile_pages.py` pass.

- [ ] **Step 5: Run backend focused suite**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py app/backend/tests/test_api_contracts.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routes/mobile.py app/backend/tests/test_mobile_pages.py
git commit -m "接入手机页面重新框选和补拍接口"
```

---

### Task 4: Frontend API Wrappers and Contract Tests

**Files:**
- Create: `app/frontend/src/pages/mobile-capture/mobileCaptureApi.ts`
- Modify: `app/frontend/tests/fixtures/uploads.ts`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`

- [ ] **Step 1: Create failing API path tests in page test**

Add these helpers near the top of `MobileCapturePage.test.tsx`:

```typescript
function jsonOk(data: unknown) {
  return HttpResponse.json({ success: true, data });
}
```

Add this test:

```typescript
it('uses capture-session routes for delete and reorder', async () => {
  const calls: string[] = [];
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  server.use(
    mockGetCaptureSession({
      ...activeSession,
      page_count: 2,
      pages: [
        { page_id: 'page_a', page_no: 1 },
        { page_id: 'page_b', page_no: 2 }
      ]
    }),
    http.delete('*/api/capture-sessions/sess_001/pages/:pageId', ({ request }) => {
      calls.push(new URL(request.url).pathname);
      return jsonOk({ ok: true });
    }),
    http.put('*/api/capture-sessions/sess_001/pages/order', async ({ request }) => {
      calls.push(new URL(request.url).pathname);
      expect(await request.json()).toEqual({ page_ids: ['page_b', 'page_a'] });
      return jsonOk({ ok: true });
    })
  );

  renderMobileCapture();
  await screen.findByText('第 1 页');
  await userEvent.setup().click(screen.getByRole('button', { name: '下移第 1 页' }));
  await userEvent.setup().click(screen.getByRole('button', { name: '删除第 1 页' }));

  await waitFor(() => expect(calls).toEqual([
    '/api/capture-sessions/sess_001/pages/order',
    '/api/capture-sessions/sess_001/pages/page_b',
  ]));
  confirmSpy.mockRestore();
});
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: test fails because current code calls `/api/mobile/<session_id>/pages/reorder` and `/api/mobile/<session_id>/pages/<page_id>`.

- [ ] **Step 3: Create API wrapper**

Create `app/frontend/src/pages/mobile-capture/mobileCaptureApi.ts`:

```typescript
import { apiRequest } from '../../api/client';
import {
  buildCapturePageFormData,
  type CapturePageUploadInput,
  type CapturePageUploadResult,
  type QuadPoint
} from '../../api/captureSessions';

export interface UpdateCapturePageQuadResult {
  page_id: string;
  page_no: number;
  quad_points: QuadPoint[];
  quad_updated_at?: string;
}

export function deleteCapturePage(sessionId: string, pageId: string) {
  return apiRequest<{ ok: boolean }>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}`,
    { method: 'DELETE' }
  );
}

export function reorderCapturePages(sessionId: string, pageIds: string[]) {
  return apiRequest<{ ok: boolean }>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/pages/order`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_ids: pageIds })
    }
  );
}

export function updateCapturePageQuad(sessionId: string, pageId: string, quadPoints: QuadPoint[]) {
  return apiRequest<UpdateCapturePageQuadResult>(
    `/api/mobile/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}/quad`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quad_points: quadPoints })
    }
  );
}

export function replaceCapturePageImage(
  sessionId: string,
  pageId: string,
  input: CapturePageUploadInput
) {
  return apiRequest<CapturePageUploadResult>(
    `/api/mobile/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}/image`,
    {
      method: 'PUT',
      body: buildCapturePageFormData(input)
    }
  );
}
```

- [ ] **Step 4: Import wrappers in `MobileCapturePage.tsx`**

Remove the local `deleteCapturePage()` and `reorderCapturePages()` functions from `MobileCapturePage.tsx`, remove the direct `apiRequest` import, and add:

```typescript
import {
  deleteCapturePage,
  reorderCapturePages
} from './mobileCaptureApi';
```

- [ ] **Step 5: Run API path test**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: the new test passes and existing tests continue passing.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/mobile-capture/mobileCaptureApi.ts app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx
git commit -m "修正手机采集页面管理接口路径"
```

---

### Task 5: QuadSelector Visible UI Simplification

**Files:**
- Modify: `app/frontend/src/components/mobile-capture/QuadSelector.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/mobile-capture.css`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`

- [ ] **Step 1: Update failing test for no coordinate controls**

In `MobileCapturePage.test.tsx`, replace:

```typescript
expect(screen.getAllByRole('slider')).toHaveLength(4);
```

with:

```typescript
expect(screen.queryByRole('slider')).toBeNull();
expect(screen.queryByLabelText(/坐标/)).toBeNull();
```

- [ ] **Step 2: Run test and confirm failure**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: test fails because the existing `QuadSelector` renders sliders.

- [ ] **Step 3: Remove coordinate controls from QuadSelector**

In `app/frontend/src/components/mobile-capture/QuadSelector.tsx`, remove `cornerLabels`, `clamp`, `updateCorner()`, and the complete `quad-selector__controls` block. Keep `cornerOrder`, SVG, polygon and circles.

The component body should end like this:

```tsx
        {cornerOrder.map((corner) => (
          <circle
            key={corner}
            cx={points[corner].x}
            cy={points[corner].y}
            r="18"
            fill="#1167f2"
            stroke="#ffffff"
            strokeWidth="5"
          />
        ))}
      </svg>
    </div>
  );
}
```

- [ ] **Step 4: Remove CSS for deleted controls**

Delete the full selector blocks for these selectors from `mobile-capture.css`:

```css
.quad-selector__controls
.quad-selector fieldset
.quad-selector legend
.quad-selector label
.quad-selector input[type="number"]
```

- [ ] **Step 5: Run test**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
```

Expected: mobile capture tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/components/mobile-capture/QuadSelector.tsx app/frontend/src/pages/mobile-capture/mobile-capture.css app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx
git commit -m "简化手机端四边形框选控件"
```

---

### Task 6: Split Mobile Capture Types and Presentational Components

**Files:**
- Create: `app/frontend/src/pages/mobile-capture/mobileCapture.types.ts`
- Create: `app/frontend/src/pages/mobile-capture/CapturePhotoButton.tsx`
- Create: `app/frontend/src/pages/mobile-capture/CaptureQuadScreen.tsx`
- Create: `app/frontend/src/pages/mobile-capture/CaptureFooter.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`

- [ ] **Step 1: Create types file**

Create `mobileCapture.types.ts`:

```typescript
import type { QuadPointsByCorner } from '../../components/mobile-capture/QuadSelector';

export type CapturePageStatus = 'uploaded' | 'uploading' | 'failed';
export type CaptureMode = 'empty' | 'list' | 'quad-new' | 'quad-replace' | 'quad-edit' | 'readonly';

export interface CapturePageItem {
  localId: string;
  pageId?: string;
  pageNo: number;
  status: CapturePageStatus;
  previewUrl?: string;
  file?: File;
  width: number;
  height: number;
  quad: QuadPointsByCorner;
}
```

- [ ] **Step 2: Create `CapturePhotoButton.tsx`**

```tsx
import { useRef } from 'react';

interface CapturePhotoButtonProps {
  disabled: boolean;
  label?: string;
  onFileSelected: (file: File) => void;
}

export function CapturePhotoButton({
  disabled,
  label = '拍摄/选择图片',
  onFileSelected
}: CapturePhotoButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        className="visually-hidden-input"
        aria-label={label}
        type="file"
        accept="image/jpeg,image/png,image/bmp"
        capture="environment"
        disabled={disabled}
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) onFileSelected(file);
          event.currentTarget.value = '';
        }}
      />
      <button
        className="mobile-button capture-photo-btn"
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        拍摄/选择图片
      </button>
    </>
  );
}
```

- [ ] **Step 3: Create `CaptureQuadScreen.tsx`**

```tsx
import {
  QuadSelector,
  type QuadPointsByCorner
} from '../../components/mobile-capture/QuadSelector';

interface CaptureQuadScreenProps {
  previewUrl?: string;
  quad: QuadPointsByCorner;
  width: number;
  height: number;
  isUploading: boolean;
  confirmLabel: string;
  onChangeQuad: (quad: QuadPointsByCorner) => void;
  onResetQuad: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CaptureQuadScreen({
  previewUrl,
  quad,
  width,
  height,
  isUploading,
  confirmLabel,
  onChangeQuad,
  onResetQuad,
  onCancel,
  onConfirm
}: CaptureQuadScreenProps) {
  return (
    <section className="preview-panel" aria-label="调整识别范围">
      <p className="mobile-capture__hint">
        请框选病历正文区域，排除屏幕边缘、灰色背景和工具栏
      </p>
      <div className="preview-panel__image-wrap">
        {previewUrl ? <img src={previewUrl} alt="待上传病历页面预览" /> : <div className="preview-panel__placeholder">缩略图</div>}
        <QuadSelector width={width} height={height} points={quad} onChange={onChangeQuad} />
      </div>
      <div className="capture-actions capture-actions--split">
        <button className="mobile-button ghost" type="button" onClick={onCancel}>
          重拍
        </button>
        <button className="mobile-button secondary" type="button" onClick={onResetQuad}>
          重置框选
        </button>
        <button className="mobile-button" type="button" disabled={isUploading} onClick={onConfirm}>
          {isUploading ? '上传中' : confirmLabel}
        </button>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create `CaptureFooter.tsx`**

```tsx
interface CaptureFooterProps {
  disabled: boolean;
  isFinishing: boolean;
  canFinish: boolean;
  onCaptureNext: () => void;
  onFinish: () => void;
}

export function CaptureFooter({
  disabled,
  isFinishing,
  canFinish,
  onCaptureNext,
  onFinish
}: CaptureFooterProps) {
  return (
    <footer className="capture-footer">
      <button className="mobile-button secondary" type="button" disabled={disabled} onClick={onCaptureNext}>
        继续拍下一页
      </button>
      <button
        className="mobile-button"
        type="button"
        disabled={disabled || isFinishing || !canFinish}
        onClick={onFinish}
      >
        {isFinishing ? '提交中' : '完成采集'}
      </button>
    </footer>
  );
}
```

- [ ] **Step 5: Move local types out of `MobileCapturePage.tsx`**

In `MobileCapturePage.tsx`, remove local `type PageStatus` and `interface CapturePageItem`, then import:

```typescript
import type { CapturePageItem } from './mobileCapture.types';
```

- [ ] **Step 6: Replace inline photo input and quad screen**

Use `CapturePhotoButton`, `CaptureQuadScreen`, and `CaptureFooter` from the new files. Keep existing behavior while changing only composition.

- [ ] **Step 7: Run tests and typecheck**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
npm run typecheck
```

Expected: both commands pass.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src/pages/mobile-capture
git commit -m "拆分手机采集页面基础组件"
```

---

### Task 7: Inline Page Item Buttons and Drag Sorting

**Files:**
- Create: `app/frontend/src/pages/mobile-capture/CapturePageItem.tsx`
- Create: `app/frontend/src/pages/mobile-capture/CapturePageList.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`

- [ ] **Step 1: Update tests for new list buttons**

In `MobileCapturePage.test.tsx`, replace expectations for “上移/下移/补拍页面” with:

```typescript
expect(screen.queryByRole('button', { name: /上移/ })).toBeNull();
expect(screen.queryByRole('button', { name: /下移/ })).toBeNull();
expect(screen.queryByRole('button', { name: '补拍页面' })).toBeNull();
expect(screen.getByRole('button', { name: '补拍第 1 页' })).toBeTruthy();
expect(screen.getByRole('button', { name: '重新框选第 1 页' })).toBeTruthy();
expect(screen.getByRole('button', { name: '删除第 1 页' })).toBeTruthy();
```

Add a drag test:

```typescript
it('reorders uploaded pages with drag handle', async () => {
  const calls: string[][] = [];
  server.use(
    mockGetCaptureSession({
      ...activeSession,
      page_count: 2,
      pages: [
        { page_id: 'page_a', page_no: 1 },
        { page_id: 'page_b', page_no: 2 }
      ]
    }),
    http.put('*/api/capture-sessions/sess_001/pages/order', async ({ request }) => {
      const body = await request.json() as { page_ids: string[] };
      calls.push(body.page_ids);
      return HttpResponse.json({ success: true, data: { ok: true } });
    })
  );

  renderMobileCapture();
  await screen.findByText('第 1 页');
  const source = screen.getByLabelText('拖拽第 2 页');
  const target = screen.getByLabelText('第 1 页 已上传');

  source.dispatchEvent(new DragEvent('dragstart', { bubbles: true }));
  target.dispatchEvent(new DragEvent('dragover', { bubbles: true }));
  target.dispatchEvent(new DragEvent('drop', { bubbles: true }));

  await waitFor(() => expect(calls).toEqual([['page_b', 'page_a']]));
});
```

- [ ] **Step 2: Create `CapturePageItem.tsx`**

```tsx
import type { CapturePageItem as PageItem } from './mobileCapture.types';

interface CapturePageItemProps {
  page: PageItem;
  index: number;
  total: number;
  isReadOnly: boolean;
  dragDisabled: boolean;
  onDelete: (page: PageItem) => void;
  onRetry: (page: PageItem) => void;
  onSupplement: (page: PageItem) => void;
  onRequad: (page: PageItem) => void;
  onDragStart: (index: number) => void;
  onDragOver: (event: React.DragEvent, index: number) => void;
  onDrop: (index: number) => void;
}

export function CapturePageItem({
  page,
  index,
  isReadOnly,
  dragDisabled,
  onDelete,
  onRetry,
  onSupplement,
  onRequad,
  onDragStart,
  onDragOver,
  onDrop
}: CapturePageItemProps) {
  const isFailed = page.status === 'failed';
  const isUploading = page.status === 'uploading';

  return (
    <li
      className={`page-item is-${page.status}`}
      aria-label={`第 ${index + 1} 页 ${isFailed ? '上传失败' : '已上传'}`}
      onDragOver={(event) => onDragOver(event, index)}
      onDrop={() => onDrop(index)}
    >
      <button
        className="page-item__drag"
        type="button"
        aria-label={`拖拽第 ${index + 1} 页`}
        draggable={!isReadOnly && !dragDisabled}
        disabled={isReadOnly || dragDisabled}
        onDragStart={() => onDragStart(index)}
      >
        ⋮⋮
      </button>
      <div className="page-item__thumb">
        {page.previewUrl ? <img src={page.previewUrl} alt={`第 ${index + 1} 页缩略图`} /> : '缩略图'}
      </div>
      <div className="page-item__content">
        <h3>第 {index + 1} 页</h3>
        <span className={`page-item__status is-${page.status}`}>
          {isFailed ? '上传失败' : isUploading ? '上传中' : '已上传'}
        </span>
        {!isReadOnly ? (
          <div className="page-item__actions">
            {isFailed ? (
              <>
                <button className="page-action is-primary" type="button" onClick={() => onRetry(page)} aria-label={`重试第 ${index + 1} 页`}>
                  重试
                </button>
                <button className="page-action is-delete" type="button" onClick={() => onDelete(page)} aria-label={`删除第 ${index + 1} 页`}>
                  删除
                </button>
              </>
            ) : (
              <>
                <button className="page-action is-blue" type="button" disabled={isUploading} onClick={() => onSupplement(page)} aria-label={`补拍第 ${index + 1} 页`}>
                  补拍
                </button>
                <button className="page-action is-orange" type="button" disabled={isUploading || !page.pageId} onClick={() => onRequad(page)} aria-label={`重新框选第 ${index + 1} 页`}>
                  重新框选
                </button>
                <button className="page-action is-delete" type="button" disabled={isUploading} onClick={() => onDelete(page)} aria-label={`删除第 ${index + 1} 页`}>
                  删除
                </button>
              </>
            )}
          </div>
        ) : null}
      </div>
    </li>
  );
}
```

- [ ] **Step 3: Create `CapturePageList.tsx`**

```tsx
import { useState } from 'react';

import type { CapturePageItem as PageItem } from './mobileCapture.types';
import { CapturePageItem } from './CapturePageItem';

interface CapturePageListProps {
  pages: PageItem[];
  isReadOnly: boolean;
  onDelete: (page: PageItem) => void;
  onRetry: (page: PageItem) => void;
  onSupplement: (page: PageItem) => void;
  onRequad: (page: PageItem) => void;
  onReorder: (fromIndex: number, toIndex: number) => void;
}

export function CapturePageList({
  pages,
  isReadOnly,
  onDelete,
  onRetry,
  onSupplement,
  onRequad,
  onReorder
}: CapturePageListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const dragDisabled = pages.some((page) => page.status !== 'uploaded');

  function handleDragOver(event: React.DragEvent, index: number) {
    if (dragIndex === null || dragIndex === index || dragDisabled) return;
    event.preventDefault();
  }

  function handleDrop(index: number) {
    if (dragIndex === null || dragIndex === index || dragDisabled) return;
    onReorder(dragIndex, index);
    setDragIndex(null);
  }

  return (
    <section className="page-list" aria-label="已采集页面列表">
      <div className="page-list__header">
        <div>
          <h2>页面列表</h2>
          <p>长按拖拽调整顺序</p>
        </div>
      </div>
      {pages.length === 0 ? (
        <div className="page-list__empty">
          <div>
            <strong>暂未上传页面</strong>
            <p>上传后可在这里查看、删除或调整顺序</p>
          </div>
        </div>
      ) : (
        <ol className="page-list__items">
          {pages.map((page, index) => (
            <CapturePageItem
              key={page.localId}
              page={page}
              index={index}
              total={pages.length}
              isReadOnly={isReadOnly}
              dragDisabled={dragDisabled}
              onDelete={onDelete}
              onRetry={onRetry}
              onSupplement={onSupplement}
              onRequad={onRequad}
              onDragStart={setDragIndex}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Replace inline `PageList` in `MobileCapturePage.tsx`**

Remove the local `PageList` function and use `CapturePageList`. Replace `movePage(index, direction)` with:

```typescript
async function reorderPages(fromIndex: number, toIndex: number) {
  if (isReadOnly) return;
  const previous = pages;
  const next = [...pages];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  const renumbered = renumberPages(next);
  setPages(renumbered);

  try {
    await reorderCapturePages(
      sessionId,
      renumbered.map((page) => page.pageId).filter((pageId): pageId is string => Boolean(pageId))
    );
  } catch {
    setPages(previous);
    setError('排序失败，请重试');
  }
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
npm run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/mobile-capture
git commit -m "改造手机采集页面列表行内操作"
```

---

### Task 8: Re-Quad and Current Page Replacement Flows

**Files:**
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.tsx`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`
- Modify: `app/frontend/tests/fixtures/uploads.ts`

- [ ] **Step 1: Add MSW fixtures**

Add to `app/frontend/tests/fixtures/uploads.ts`:

```typescript
export function mockUpdateCapturePageQuad(sessionId = activeSession.session_id) {
  return http.put('*/api/mobile/:sessionId/pages/:pageId/quad', async ({ params, request }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }
    const body = await request.json() as { quad_points: Array<{ x: number; y: number }> };
    return HttpResponse.json({
      success: true,
      data: {
        page_id: params.pageId,
        page_no: 1,
        quad_points: body.quad_points,
        quad_updated_at: '2026-05-14T08:05:00+00:00'
      }
    });
  });
}

export function mockReplaceCapturePageImage(sessionId = activeSession.session_id) {
  return http.put('*/api/mobile/:sessionId/pages/:pageId/image', ({ params }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }
    return HttpResponse.json({
      success: true,
      data: {
        page_id: params.pageId,
        page_index: 1,
        status: 'uploaded'
      }
    });
  });
}
```

- [ ] **Step 2: Add re-quad and replacement tests**

Add tests to `MobileCapturePage.test.tsx`:

```typescript
it('updates an uploaded page quad without re-uploading the image', async () => {
  let postUploads = 0;
  let quadUpdates = 0;
  server.use(
    mockGetCaptureSession({
      ...activeSession,
      page_count: 1,
      pages: [{ page_id: 'page_a', page_no: 1 }]
    }),
    http.post('*/api/mobile/sess_001/pages', () => {
      postUploads += 1;
      return HttpResponse.json({ success: true, data: { page_id: 'unexpected', page_index: 2, status: 'uploaded' } });
    }),
    http.put('*/api/mobile/sess_001/pages/page_a/quad', async ({ request }) => {
      quadUpdates += 1;
      const body = await request.json() as { quad_points: Array<{ x: number; y: number }> };
      expect(body.quad_points).toHaveLength(4);
      return HttpResponse.json({ success: true, data: { page_id: 'page_a', page_no: 1, quad_points: body.quad_points } });
    })
  );

  renderMobileCapture();
  await screen.findByText('第 1 页');
  await userEvent.setup().click(screen.getByRole('button', { name: '重新框选第 1 页' }));
  await userEvent.setup().click(screen.getByRole('button', { name: '确认上传' }));

  await waitFor(() => expect(quadUpdates).toBe(1));
  expect(postUploads).toBe(0);
});

it('replaces the current page image when supplementing an uploaded page', async () => {
  let replaceCalls = 0;
  server.use(
    mockGetCaptureSession({
      ...activeSession,
      page_count: 1,
      pages: [{ page_id: 'page_a', page_no: 1 }]
    }),
    http.put('*/api/mobile/sess_001/pages/page_a/image', () => {
      replaceCalls += 1;
      return HttpResponse.json({ success: true, data: { page_id: 'page_a', page_index: 1, status: 'uploaded' } });
    })
  );

  renderMobileCapture();
  await screen.findByText('第 1 页');
  await userEvent.setup().click(screen.getByRole('button', { name: '补拍第 1 页' }));
  await selectImage('拍摄/选择图片', makeImageFile('replacement.jpg'));
  await userEvent.setup().click(screen.getByRole('button', { name: '确认上传' }));

  await waitFor(() => expect(replaceCalls).toBe(1));
  expect(screen.getAllByText('已上传')).toHaveLength(1);
  expect(screen.getByText('第 1 页')).toBeTruthy();
});
```

- [ ] **Step 3: Implement mode state**

In `MobileCapturePage.tsx`, replace `insertIndex` with:

```typescript
const [editingPage, setEditingPage] = useState<CapturePageItem | null>(null);
const [editMode, setEditMode] = useState<'new' | 'replace' | 'quad' | null>(null);
```

Add these handlers:

```typescript
function startNewPage() {
  if (isReadOnly) return;
  setEditingPage(null);
  setEditMode('new');
}

function startReplacePage(page: CapturePageItem) {
  if (isReadOnly) return;
  setEditingPage(page);
  setEditMode('replace');
}

function startRequadPage(page: CapturePageItem) {
  if (isReadOnly || !page.pageId) return;
  setEditingPage(page);
  setSelectedPage(page);
  setEditMode('quad');
}
```

- [ ] **Step 4: Update file selection and confirmation**

When a file is selected, build the local page and set `selectedPage`. If `editMode === 'replace'` and `editingPage` exists, preserve `pageId` and `pageNo`:

```typescript
const targetPage = buildLocalPage(file, pages.length);
setSelectedPage(
  editMode === 'replace' && editingPage
    ? { ...targetPage, localId: editingPage.localId, pageId: editingPage.pageId, pageNo: editingPage.pageNo }
    : targetPage
);
```

In confirm logic:

- `editMode === 'quad'`: call `updateCapturePageQuad(sessionId, selectedPage.pageId, quadToArray(selectedPage.quad))`.
- `editMode === 'replace'`: call `replaceCapturePageImage(sessionId, selectedPage.pageId, { file, width, height, quad_points })`.
- otherwise: call `uploadCapturePage()`.

- [ ] **Step 5: Reset edit state after success or cancel**

After any success:

```typescript
setSelectedPage(null);
setEditingPage(null);
setEditMode(null);
```

On cancel:

```typescript
setSelectedPage(null);
setEditingPage(null);
setEditMode(null);
```

- [ ] **Step 6: Run tests**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
npm run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/mobile-capture app/frontend/tests/fixtures/uploads.ts
git commit -m "接入手机端重新框选和补拍替换"
```

---

### Task 9: Visual CSS Alignment and Fixed Footer Removal

**Files:**
- Modify: `app/frontend/src/pages/mobile-capture/mobile-capture.css`
- Modify: `app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx`

- [ ] **Step 1: Add CSS behavior assertion**

Add this test:

```typescript
it('keeps footer actions in normal content flow', async () => {
  server.use(mockGetCaptureSession({ ...activeSession, page_count: 0, pages: [] }));
  renderMobileCapture();

  await screen.findByText('采集会话进行中');
  const footer = screen.getByRole('contentinfo');
  expect(footer.className).toContain('capture-footer');
  expect(footer.className).not.toContain('mobile-capture__footer');
});
```

- [ ] **Step 2: Replace footer CSS**

In `mobile-capture.css`, remove:

```css
.mobile-capture__footer
.mobile-capture__footer-inner
```

Add:

```css
.capture-footer {
  width: 100%;
  max-width: 520px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  margin: 18px auto 0;
  padding: 0 16px 24px;
}
```

- [ ] **Step 3: Apply list button visual rules**

Add:

```css
.page-item {
  grid-template-columns: 44px 96px 1fr;
  align-items: center;
}

.page-item__drag {
  width: 44px;
  min-height: 96px;
  border: 0;
  background: transparent;
  color: #94a3b8;
  font-size: 24px;
  cursor: grab;
}

.page-item__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.page-action {
  min-height: 44px;
  border-radius: 8px;
  padding: 0 14px;
  background: #ffffff;
  font-weight: 800;
}

.page-action.is-primary {
  border: 1px solid #1167f2;
  background: #1167f2;
  color: #ffffff;
}

.page-action.is-blue {
  border: 1px solid #1167f2;
  color: #1167f2;
}

.page-action.is-orange {
  border: 1px solid #f97316;
  color: #f97316;
}

.page-action.is-delete {
  border: 1px solid #94a3b8;
  color: #dc2626;
}
```

- [ ] **Step 4: Remove obsolete selectors**

Delete `.supplement-card` styles and references, because the component is removed.

- [ ] **Step 5: Run tests and build**

Run:

```bash
npm run test -- MobileCapturePage.test.tsx
npm run build
```

Expected: tests and build pass.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/mobile-capture/mobile-capture.css app/frontend/src/pages/mobile-capture/MobileCapturePage.test.tsx
git commit -m "对齐手机采集页素材视觉"
```

---

### Task 10: Full Verification and Documentation Check

**Files:**
- Modify only if verification reveals a documentation mismatch: `docs/superpowers/2026-05-14-mobile-capture-ux-redesign.md`
- Modify only if implementation changes an agreed route or behavior: `docs/Front/Front_TDD/04-mobile-capture.md`, `docs/Front/Front_TDD/05-page-management.md`, `docs/Front/Front_TDD/06-quad-interaction.md`, `docs/Backend/Backend_TDD/05-file-upload.md`

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_page_service.py app/backend/tests/test_mobile_pages.py app/backend/tests/test_api_contracts.py -q
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

Expected: Vite build succeeds and writes `dist/`.

- [ ] **Step 5: Run repository diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 6: Manual mobile visual check**

Run from `app/frontend/`:

```bash
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/mobile/sessions/sess_001
```

Check these against the three PNG references:

- Top bar title, back button, help button visible.
- Green session status pill appears below top bar.
- Empty state uses a light blue card and one “拍摄/选择图片” button.
- List page uses white cards, drag handles, thumbnail area, green uploaded labels, inline buttons.
- Quad page uses blue info strip, full image area, blue corner handles, no coordinate controls.
- Footer buttons are visible after list content and do not overlay list items.

- [ ] **Step 7: Commit final verification/doc updates**

If Step 6 required doc or CSS changes:

```bash
git add app/frontend/src/pages/mobile-capture docs/superpowers/2026-05-14-mobile-capture-ux-redesign.md docs/Front docs/Backend
git commit -m "收口手机采集页重构验收"
```

If no changes are needed, do not create an empty commit.

---

## Coverage Checklist

- UX-001 single image entry: Task 6.
- UX-002 no pixel controls: Task 5.
- UX-003 default 80% quad and direct confirm: existing `createDefaultQuad`, verified in Task 5 and Task 8.
- UX-004 uploaded inline actions: Task 7.
- UX-005 failed inline actions: Task 7.
- UX-006 drag sorting: Task 7.
- UX-007 non-fixed footer: Task 9.
- UX-008 remove supplement card: Task 7 and Task 9.
- UX-009 update quad endpoint: Task 1 and Task 3.
- UX-010 replace page image endpoint: Task 2 and Task 3.
- UX-011 component split: Task 6 and Task 7.
- UX-012 visual alignment: Task 9 and Task 10.
