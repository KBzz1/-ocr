# Review OCR Floating Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the always-visible OCR panel in the review workspace with a draggable, resizable floating OCR window while letting the structured field panel occupy the full lower workspace.

**Architecture:** Keep `ReviewSourcePanel` responsible for complete OCR text rendering, evidence highlighting, and internal scrolling. Add a focused `ReviewOcrFloatingWindow` wrapper that owns open/close, position, size, drag, resize, and viewport clamping. `ReviewPage` removes the default OCR column, opens/updates the OCR window when fields are selected, and keeps image page linkage unchanged.

**Tech Stack:** React 18, TypeScript, CSS, Vitest, React Testing Library, MSW.

---

## Execution Notes

This plan is designed for an implementation agent without visual review. Do not make taste-based styling decisions beyond the CSS tokens and constraints listed here. The final visual polishing pass will be handled separately by the reviewer.

Before editing, read:

- `app/frontend/AGENTS.md`
- `docs/superpowers/specs/2026-06-25-review-ocr-floating-window-design.md`
- `app/frontend/src/components/review/ReviewSourcePanel.tsx`
- `app/frontend/src/pages/review/ReviewPage.tsx`
- `app/frontend/src/pages/review/review.css`

Use these verification commands:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewOcrFloatingWindow.test.tsx src/components/review/ReviewSourcePanel.test.tsx src/pages/review/ReviewPage.test.tsx
npm --prefix app/frontend run typecheck
```

## File Structure

- Create `app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx`
  - A presentational/interaction wrapper around `ReviewSourcePanel`.
  - Owns window position, size, drag, resize, close, and reset-to-default behavior.
  - Receives full OCR text and `sourceMessage` from `ReviewPage`.

- Create `app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx`
  - Unit tests for open rendering, close, drag, resize, viewport clamping, and no instructional title text.

- Modify `app/frontend/src/components/review/ReviewSourcePanel.tsx`
  - Keep existing highlighter behavior.
  - Add an optional `onReturnToHighlightReady?: (callback: () => void) => void` only if needed for the floating window's "return to highlight" button.
  - Do not change raw OCR rendering semantics.

- Modify `app/frontend/src/components/review/ReviewSourcePanel.test.tsx`
  - Keep existing offset/long evidence tests passing.
  - Add coverage only if `ReviewSourcePanel` gains a callback prop.

- Modify `app/frontend/src/pages/review/ReviewPage.tsx`
  - Remove the default `review-panel--ocr` section from the lower workspace.
  - Add OCR window state.
  - Open/update the floating OCR window from field focus and from an "打开 OCR" action.
  - Keep page image selection logic in `handleFocusField`.

- Modify `app/frontend/src/pages/review/ReviewPage.test.tsx`
  - Update tests that currently expect the OCR panel to be visible by default.
  - Add tests for floating OCR opening, evidence highlighting, and no position reset when switching fields.

- Modify `app/frontend/src/pages/review/review.css`
  - Make `.review-grid` single-column for the lower workspace.
  - Add deterministic floating window classes.
  - Add compact icon-button styles with accessible labels and no visible instructional text.

## Task 1: Component Tests For Floating OCR Window

**Files:**
- Create: `app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx`
- Create later in Task 2: `app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx`

- [ ] **Step 1: Write the failing component test**

Create `app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ReviewOcrFloatingWindow } from './ReviewOcrFloatingWindow';

function renderWindow(overrides: Partial<ComponentProps<typeof ReviewOcrFloatingWindow>> = {}) {
  const onClose = vi.fn();
  const props: ComponentProps<typeof ReviewOcrFloatingWindow> = {
    text: '姓名：张三\n\n## 主诉\n反复咳嗽、咳痰15年，加重伴喘憋3天。',
    sourceMessage: {
      kind: 'located',
      text: '点击字段可定位原文',
      evidenceText: '反复咳嗽、咳痰15年',
      startIndex: '姓名：张三\n\n## 主诉\n'.length,
    },
    selectedFieldLabel: '主诉',
    onClose,
    ...overrides,
  };
  render(<ReviewOcrFloatingWindow {...props} />);
  return { onClose };
}

describe('ReviewOcrFloatingWindow', () => {
  it('renders complete OCR in a lightweight window without instructional chrome text', () => {
    renderWindow();

    expect(screen.getByRole('dialog', { name: '主诉 OCR 原文' })).toBeTruthy();
    expect(screen.getByText('主诉')).toBeTruthy();
    expect(screen.getByLabelText('合并 OCR 文本').textContent).toContain('姓名：张三');
    expect(screen.getByText('反复咳嗽、咳痰15年', { selector: 'mark' })).toBeTruthy();
    expect(screen.queryByText(/拖动标题栏/)).toBeNull();
    expect(screen.queryByText(/右下角缩放/)).toBeNull();
  });

  it('uses icon-style controls with accessible names', () => {
    const { onClose } = renderWindow();

    expect(screen.getByRole('button', { name: '回到当前字段原文' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '恢复默认窗口大小和位置' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '关闭 OCR 原文窗口' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('moves within the viewport when the title bar is dragged', () => {
    renderWindow();

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' });
    const handle = screen.getByTestId('ocr-window-drag-handle');

    fireEvent.mouseDown(handle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 180, clientY: 150 });
    fireEvent.mouseUp(window);

    expect(dialog).toHaveStyle({ left: '420px', top: '190px' });
  });

  it('clamps drag position so the window cannot be lost off screen', () => {
    renderWindow({
      viewportSize: { width: 800, height: 600 },
      initialRect: { left: 320, top: 140, width: 520, height: 340 },
    });

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' });
    const handle = screen.getByTestId('ocr-window-drag-handle');

    fireEvent.mouseDown(handle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 900, clientY: 900 });
    fireEvent.mouseUp(window);

    expect(dialog).toHaveStyle({ left: '280px', top: '260px' });
  });

  it('resizes with the resize handle while preserving minimum dimensions', () => {
    renderWindow();

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' });
    const resizeHandle = screen.getByTestId('ocr-window-resize-handle');

    fireEvent.mouseDown(resizeHandle, { clientX: 840, clientY: 480 });
    fireEvent.mouseMove(window, { clientX: 900, clientY: 540 });
    fireEvent.mouseUp(window);

    expect(dialog).toHaveStyle({ width: '580px', height: '400px' });

    fireEvent.mouseDown(resizeHandle, { clientX: 900, clientY: 540 });
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100 });
    fireEvent.mouseUp(window);

    expect(dialog).toHaveStyle({ width: '360px', height: '240px' });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewOcrFloatingWindow.test.tsx
```

Expected: FAIL because `ReviewOcrFloatingWindow` does not exist.

## Task 2: Implement ReviewOcrFloatingWindow

**Files:**
- Create: `app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx`

- [ ] **Step 1: Implement the component**

Create `app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ReviewSourcePanel, type SourceMessage } from './ReviewSourcePanel';

type WindowRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type ViewportSize = {
  width: number;
  height: number;
};

type ReviewOcrFloatingWindowProps = {
  text: string;
  sourceMessage: SourceMessage | null;
  selectedFieldLabel?: string;
  onClose: () => void;
  initialRect?: WindowRect;
  viewportSize?: ViewportSize;
};

const DEFAULT_RECT: WindowRect = { left: 340, top: 140, width: 520, height: 340 };
const MIN_WIDTH = 360;
const MIN_HEIGHT = 240;
const EDGE_MARGIN = 0;

function getViewportSize(override?: ViewportSize): ViewportSize {
  if (override) return override;
  if (typeof window === 'undefined') return { width: 1280, height: 800 };
  return {
    width: window.innerWidth || 1280,
    height: window.innerHeight || 800,
  };
}

function clampRect(rect: WindowRect, viewport: ViewportSize): WindowRect {
  const width = Math.min(Math.max(rect.width, MIN_WIDTH), viewport.width);
  const height = Math.min(Math.max(rect.height, MIN_HEIGHT), viewport.height);
  const maxLeft = Math.max(EDGE_MARGIN, viewport.width - width);
  const maxTop = Math.max(EDGE_MARGIN, viewport.height - height);
  return {
    left: Math.min(Math.max(rect.left, EDGE_MARGIN), maxLeft),
    top: Math.min(Math.max(rect.top, EDGE_MARGIN), maxTop),
    width,
    height,
  };
}

export function ReviewOcrFloatingWindow({
  text,
  sourceMessage,
  selectedFieldLabel,
  onClose,
  initialRect = DEFAULT_RECT,
  viewportSize,
}: ReviewOcrFloatingWindowProps) {
  const viewport = useMemo(() => getViewportSize(viewportSize), [viewportSize]);
  const [rect, setRect] = useState<WindowRect>(() => clampRect(initialRect, viewport));
  const dragRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);

  const title = selectedFieldLabel ? `${selectedFieldLabel} OCR 原文` : 'OCR 原文';

  const resetRect = useCallback(() => {
    setRect(clampRect(DEFAULT_RECT, getViewportSize(viewportSize)));
  }, [viewportSize]);

  useEffect(() => {
    function handleMouseMove(event: MouseEvent) {
      if (dragRef.current) {
        const { startX, startY, startRect } = dragRef.current;
        setRect(clampRect({
          ...startRect,
          left: startRect.left + event.clientX - startX,
          top: startRect.top + event.clientY - startY,
        }, getViewportSize(viewportSize)));
      }

      if (resizeRef.current) {
        const { startX, startY, startRect } = resizeRef.current;
        setRect(clampRect({
          ...startRect,
          width: startRect.width + event.clientX - startX,
          height: startRect.height + event.clientY - startY,
        }, getViewportSize(viewportSize)));
      }
    }

    function handleMouseUp() {
      dragRef.current = null;
      resizeRef.current = null;
    }

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [viewportSize]);

  return (
    <section
      aria-label={title}
      className="review-ocr-window"
      role="dialog"
      style={{
        left: `${rect.left}px`,
        top: `${rect.top}px`,
        width: `${rect.width}px`,
        height: `${rect.height}px`,
      }}
    >
      <header
        className="review-ocr-window__titlebar"
        data-testid="ocr-window-drag-handle"
        onMouseDown={(event) => {
          if (event.button !== 0) return;
          dragRef.current = { startX: event.clientX, startY: event.clientY, startRect: rect };
        }}
      >
        <div className="review-ocr-window__title">
          <span>{selectedFieldLabel ?? 'OCR'}</span>
          <strong>OCR 原文</strong>
        </div>
        <div className="review-ocr-window__actions">
          <button type="button" aria-label="回到当前字段原文" title="回到当前字段原文">
            ↺
          </button>
          <button type="button" aria-label="恢复默认窗口大小和位置" title="恢复默认窗口大小和位置" onClick={resetRect}>
            ◱
          </button>
          <button type="button" aria-label="关闭 OCR 原文窗口" title="关闭 OCR 原文窗口" onClick={onClose}>
            ×
          </button>
        </div>
      </header>
      <div className="review-ocr-window__body">
        <ReviewSourcePanel text={text} sourceMessage={sourceMessage} />
      </div>
      <button
        type="button"
        aria-label="调整 OCR 原文窗口大小"
        className="review-ocr-window__resize"
        data-testid="ocr-window-resize-handle"
        onMouseDown={(event) => {
          if (event.button !== 0) return;
          resizeRef.current = { startX: event.clientX, startY: event.clientY, startRect: rect };
        }}
      />
    </section>
  );
}
```

- [ ] **Step 2: Add deterministic CSS for the component**

Append these classes near the OCR panel styles in `app/frontend/src/pages/review/review.css`:

```css
.review-ocr-window {
  position: fixed;
  z-index: 30;
  display: grid;
  grid-template-rows: 38px minmax(0, 1fr);
  min-width: 360px;
  min-height: 240px;
  overflow: hidden;
  border: 1px solid #c8d7ea;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.2);
}

.review-ocr-window__titlebar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid #e2eaf5;
  padding: 0 8px 0 12px;
  background: #f8fbff;
  cursor: move;
  user-select: none;
}

.review-ocr-window__title {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.review-ocr-window__title span {
  min-width: 0;
  overflow: hidden;
  color: #33496a;
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.review-ocr-window__title strong {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.review-ocr-window__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.review-ocr-window__actions button {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #53657f;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
}

.review-ocr-window__actions button:hover {
  border-color: #d4dfec;
  background: #eef5ff;
  color: #244f93;
}

.review-ocr-window__body {
  min-height: 0;
  padding: 10px;
}

.review-ocr-window .review-source {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.review-ocr-window .review-source pre {
  height: 100%;
  min-height: 0;
  max-height: none;
}

.review-ocr-window__resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 18px;
  height: 18px;
  border: 0;
  background: linear-gradient(135deg, transparent 52%, #9db0c8 52%, #9db0c8 60%, transparent 60%);
  cursor: nwse-resize;
}
```

- [ ] **Step 3: Run the component test**

Run:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewOcrFloatingWindow.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx app/frontend/src/pages/review/review.css
git commit -m "新增OCR原文浮窗组件"
```

## Task 3: ReviewPage Tests For New Layout

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify later in Task 4: `app/frontend/src/pages/review/ReviewPage.tsx`

- [ ] **Step 1: Update the existing OCR evidence test**

In `app/frontend/src/pages/review/ReviewPage.test.tsx`, replace the test named `highlights selected field evidence in OCR and reports missing source text` with:

```tsx
  it('opens floating OCR window for selected field evidence and reports missing source text inside the window', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '姓名：张三\n第二页没有来源',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '姓名：张三'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '第二页没有来源'
                }
              ],
              fields: [
                {
                  field_key: 'patient_name',
                  label: '姓名',
                  value: '张三',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '张三' }]
                },
                {
                  field_key: 'chief_complaint',
                  label: '主诉',
                  value: '头痛三天',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_002', page_no: 2, text: '头痛三天' }]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(screen.queryByRole('region', { name: 'OCR 文本' })).toBeNull();
    await userEvent.click(await screen.findByTestId('review-field-card-patient_name'));

    const dialog = screen.getByRole('dialog', { name: '姓名 OCR 原文' });
    expect(within(dialog).getByText('点击字段可定位原文')).toBeTruthy();
    expect(within(dialog).getByText('张三', { selector: 'mark' })).toBeTruthy();

    await userEvent.click(screen.getByTestId('review-field-card-chief_complaint'));
    expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
    expect(screen.getByRole('dialog', { name: '主诉 OCR 原文' })).toBeTruthy();
    expect(within(screen.getByRole('dialog', { name: '主诉 OCR 原文' })).getByText('来源文本未在当前 OCR 中定位')).toBeTruthy();
  });
```

- [ ] **Step 2: Add a no-reset test for position and size**

Add this test near the OCR evidence tests:

```tsx
  it('keeps floating OCR window position and size while switching fields', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    await userEvent.click(await screen.findByTestId('review-field-card-patient_name'));
    const dialog = screen.getByRole('dialog', { name: '姓名 OCR 原文' });
    const dragHandle = screen.getByTestId('ocr-window-drag-handle');
    const resizeHandle = screen.getByTestId('ocr-window-resize-handle');

    fireEvent.mouseDown(dragHandle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 180, clientY: 150 });
    fireEvent.mouseUp(window);

    fireEvent.mouseDown(resizeHandle, { clientX: 840, clientY: 480 });
    fireEvent.mouseMove(window, { clientX: 900, clientY: 540 });
    fireEvent.mouseUp(window);

    expect(dialog).toHaveStyle({ left: '420px', top: '190px', width: '580px', height: '400px' });

    await userEvent.click(screen.getByTestId('review-field-card-chief_complaint'));
    const updatedDialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' });
    expect(updatedDialog).toHaveStyle({ left: '420px', top: '190px', width: '580px', height: '400px' });
  });
```

If `fireEvent` is not imported at the top of `ReviewPage.test.tsx`, change the import to:

```tsx
import { fireEvent, render, screen, cleanup, waitFor, within } from '@testing-library/react';
```

- [ ] **Step 3: Add a full-width field workspace test**

Add this test:

```tsx
  it('uses the lower workspace for fields instead of rendering a default OCR column', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('字段校对')).toBeTruthy();
    expect(screen.queryByRole('region', { name: 'OCR 文本' })).toBeNull();
    expect(document.querySelector('.review-grid--fields-only')).toBeTruthy();
  });
```

- [ ] **Step 4: Run tests to verify failure**

Run:

```bash
npm --prefix app/frontend run test -- --run src/pages/review/ReviewPage.test.tsx
```

Expected: FAIL because `ReviewPage` still renders the default OCR panel and does not open the floating window.

## Task 4: Refactor ReviewPage To Use Floating OCR

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Import the floating window**

In `app/frontend/src/pages/review/ReviewPage.tsx`, add:

```tsx
import { ReviewOcrFloatingWindow } from '../../components/review/ReviewOcrFloatingWindow';
```

Keep the existing `ReviewSourcePanel` import only if another section still uses it. After this task, `ReviewPage` should import `type SourceMessage` from `ReviewSourcePanel`, not the component:

```tsx
import type { SourceMessage } from '../../components/review/ReviewSourcePanel';
```

- [ ] **Step 2: Add floating OCR state**

Near existing selected field state in `ReviewPage`, add:

```tsx
  const [isOcrWindowOpen, setIsOcrWindowOpen] = useState(false);
```

- [ ] **Step 3: Add a field label helper**

Near `sourceMessage`, add:

```tsx
  const selectedFieldLabel = selectedField?.field_name ?? selectedField?.label ?? selectedField?.field_key;
```

- [ ] **Step 4: Open the OCR window when a field is focused**

Update `handleFocusField` to open the window while preserving existing page selection behavior:

```tsx
  function handleFocusField(field: ReviewField) {
    setSelectedFieldKey(field.field_key);
    setIsOcrWindowOpen(true);
    const evidence = field.evidence?.find((item) => item.page_id || item.page_no);
    if (evidence?.page_id) {
      setSelectedPageId(evidence.page_id);
      return;
    }
    const pageByNo = pages.find((page) => page.page_no === evidence?.page_no);
    if (pageByNo) setSelectedPageId(pageByNo.page_id);
  }
```

- [ ] **Step 5: Replace the lower workspace markup**

Find the branch that starts with `) : (` after the readonly panel and currently renders `<div className="review-grid">`. Replace that whole lower workspace, from the opening `<div className="review-grid">` through its matching closing `</div>`, with this markup:

```tsx
        <div className="review-grid review-grid--fields-only">
          <section className="review-panel review-panel--fields" aria-label="结构化字段" ref={fieldsPanelRef}>
            <div className="review-panel__heading">
              <div>
                <h2>字段校对</h2>
              </div>
              <div className="review-panel__heading-right">
                <span className="review-panel__count">{fields.length} 个字段，{confirmedFieldCount} 个已确认</span>
                <button
                  type="button"
                  className="review-ocr-open-button"
                  onClick={() => setIsOcrWindowOpen(true)}
                >
                  打开 OCR
                </button>
                <button
                  type="button"
                  className="review-reextract-button"
                  onClick={() => void handleReextract()}
                  disabled={isReextracting || saveStatus === 'saving' || isCompleting}
                >
                  {isReextracting ? (
                    <>
                      <span className="review-reextract-button__spinner" aria-hidden="true" />
                      重新抽取中
                    </>
                  ) : (
                    '重新抽取'
                  )}
                </button>
                {isReextracting ? (
                  <button
                    type="button"
                    className="review-reextract-cancel-button"
                    onClick={handleCancelReextract}
                  >
                    取消
                  </button>
                ) : null}
              </div>
            </div>
            <FieldList
              fields={fields}
              fieldGroups={review?.field_groups}
              selectedFieldKey={selectedFieldKey}
              onChange={handleFieldsChange}
              onFocusField={handleFocusField}
              onToggleReviewed={handleToggleFieldReviewed}
            />
          </section>
          {isOcrWindowOpen ? (
            <ReviewOcrFloatingWindow
              text={visibleOcrText || '无 OCR 文本'}
              sourceMessage={sourceMessage}
              selectedFieldLabel={selectedFieldLabel}
              onClose={() => setIsOcrWindowOpen(false)}
            />
          ) : null}
        </div>
```

Remove `ocrPanelStyle` if it becomes unused. Keep the `fieldsPanelRef` height sync only if TypeScript still needs it; otherwise remove `ocrPanelHeight`, `setOcrPanelHeight`, and the related `useEffect`.

- [ ] **Step 6: Update CSS for the fields-only grid**

In `app/frontend/src/pages/review/review.css`, add after the latest `.review-grid` definition:

```css
.review-grid--fields-only {
  grid-template-columns: minmax(0, 1fr);
}

.review-grid--fields-only .review-panel--fields {
  min-width: 0;
}

.review-ocr-open-button {
  min-height: 32px;
  border: 1px solid #d8e3f0;
  border-radius: 6px;
  padding: 0 12px;
  background: #ffffff;
  color: #355270;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.review-ocr-open-button:hover {
  border-color: #aac4e8;
  background: #f7fbff;
  color: #24539a;
}
```

Remove or leave unused `.review-panel--ocr` styles only if doing so does not disturb unrelated tests. Do not spend time deleting every old OCR CSS rule in this task.

- [ ] **Step 7: Run the ReviewPage test**

Run:

```bash
npm --prefix app/frontend run test -- --run src/pages/review/ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/src/pages/review/review.css
git commit -m "将审核页OCR改为浮窗展示"
```

## Task 5: Preserve ReviewSourcePanel Behavior

**Files:**
- Modify if needed: `app/frontend/src/components/review/ReviewSourcePanel.tsx`
- Modify if needed: `app/frontend/src/components/review/ReviewSourcePanel.test.tsx`
- Test: `app/frontend/src/components/review/ReviewSourcePanel.test.tsx`

- [ ] **Step 1: Run existing ReviewSourcePanel tests**

Run:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewSourcePanel.test.tsx
```

Expected: PASS.

- [ ] **Step 2: If the floating window "return to highlight" button is inert, wire it explicitly**

If Task 2 left the "回到当前字段原文" button without behavior, update `ReviewSourcePanel.tsx` to expose an optional callback. If the button already works through a remount or a local callback, skip to Step 5.

Change the prop type:

```tsx
type ReviewSourcePanelProps = {
  text: string;
  sourceMessage: SourceMessage | null;
  onReturnToHighlightReady?: (callback: () => void) => void;
};
```

Inside `ReviewSourcePanel`, create a scroll callback and register it:

```tsx
  const scrollToHighlight = useCallback(() => {
    if (effectiveSourceMessage?.kind !== 'located') return;
    if (typeof markRef.current?.scrollIntoView !== 'function') return;
    markRef.current.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, [effectiveSourceMessage?.kind, effectiveSourceMessage?.evidenceText]);

  useEffect(() => {
    scrollToHighlight();
  }, [scrollToHighlight]);

  useEffect(() => {
    onReturnToHighlightReady?.(scrollToHighlight);
  }, [onReturnToHighlightReady, scrollToHighlight]);
```

Add `useCallback` to the React import.

- [ ] **Step 3: Update the floating window to call the callback**

In `ReviewOcrFloatingWindow.tsx`, add:

```tsx
  const [returnToHighlight, setReturnToHighlight] = useState<(() => void) | null>(null);
```

Update the "回到当前字段原文" button:

```tsx
          <button
            type="button"
            aria-label="回到当前字段原文"
            title="回到当前字段原文"
            onClick={() => returnToHighlight?.()}
          >
            ↺
          </button>
```

Update the panel usage:

```tsx
        <ReviewSourcePanel
          text={text}
          sourceMessage={sourceMessage}
          onReturnToHighlightReady={(callback) => setReturnToHighlight(() => callback)}
        />
```

- [ ] **Step 4: Add a callback test only if Step 2 was needed**

Append to `ReviewSourcePanel.test.tsx`:

```tsx
  it('exposes a return-to-highlight callback when evidence is located', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    let callback: (() => void) | undefined;

    render(
      <ReviewSourcePanel
        text="主诉：反复咳嗽、咳痰15年"
        sourceMessage={{
          kind: 'located',
          text: '点击字段可定位原文',
          evidenceText: '反复咳嗽、咳痰15年',
          startIndex: 3,
        }}
        onReturnToHighlightReady={(nextCallback) => {
          callback = nextCallback;
        }}
      />,
    );

    callback?.();
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', inline: 'nearest' });
  });
```

Also import `vi`:

```tsx
import { describe, expect, it, vi } from 'vitest';
```

- [ ] **Step 5: Run source panel and floating window tests**

Run:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewSourcePanel.test.tsx src/components/review/ReviewOcrFloatingWindow.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit if code changed**

If this task changed files:

```bash
git add app/frontend/src/components/review/ReviewSourcePanel.tsx app/frontend/src/components/review/ReviewSourcePanel.test.tsx app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx app/frontend/src/components/review/ReviewOcrFloatingWindow.test.tsx
git commit -m "保留OCR高亮回看能力"
```

If no code changed, do not create an empty commit.

## Task 6: Broad Verification For Non-Visual Agent

**Files:**
- No intended code changes.

- [ ] **Step 1: Run focused component/page tests**

Run:

```bash
npm --prefix app/frontend run test -- --run src/components/review/ReviewOcrFloatingWindow.test.tsx src/components/review/ReviewSourcePanel.test.tsx src/pages/review/ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run typecheck**

Run:

```bash
npm --prefix app/frontend run typecheck
```

Expected: PASS.

- [ ] **Step 3: Run full frontend unit suite if focused checks pass**

Run:

```bash
npm --prefix app/frontend run test -- --run
```

Expected: PASS.

- [ ] **Step 4: Document visual-review handoff in the final implementation message**

The implementation agent must report:

```text
Implemented the OCR floating window behavior and tests. I did not perform visual polish because this plan reserves final front-end visual review for the reviewer. Please run a browser review for window placement, titlebar density, icon affordance, and field-grid spacing.
```

Do not claim the UI is visually polished without reviewer inspection.

## Task 7: Reserved Visual Polish Review

**Owner:** Reviewer with visual access, not the non-visual implementation agent.

**Files likely touched after implementation:**
- `app/frontend/src/pages/review/review.css`
- Possibly `app/frontend/src/components/review/ReviewOcrFloatingWindow.tsx`

Checklist for the reviewer:

- [ ] Verify default floating window size covers only part of the field workspace.
- [ ] Verify titlebar feels compact and does not contain instructional text.
- [ ] Verify icon buttons are understandable with tooltips and not visually noisy.
- [ ] Verify OCR text remains readable at default, minimum, and enlarged sizes.
- [ ] Verify field cards benefit from the full-width lower workspace.
- [ ] Verify evidence highlight is visible but not warning-like.
- [ ] Verify drag/resize affordance is discoverable enough without extra visible copy.

Suggested visual commands if a dev server is needed:

```bash
npm --prefix app/frontend run dev
```

The reviewer should open a review/demo route with existing local fixtures or mocked data and inspect the checklist above. The non-visual implementation agent should not make final visual-quality claims.
