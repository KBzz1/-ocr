# Review Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有审核页优化为以图片和字段为主的统一审核工作台，保留全局工作站导航，并把 OCR 文本改为可折叠辅助栏。

**Architecture:** 复用现有 `GET/PUT /api/tasks/{taskId}/review`、`POST /api/tasks/{taskId}/complete` 和导出 API，不新增后端契约。前端将 `ReviewPage` 放入 `WorkstationLayout`，在页内管理当前页、当前字段、OCR 展开状态、保存状态和统一审核完成流程。字段列表只支持编辑和聚焦，不提供逐字段确认按钮；统一审核时批量把未修改的 `unreviewed` 字段提交为 `confirmed`。

**Tech Stack:** React + TypeScript + Vite；Vitest + React Testing Library + MSW；Playwright route mock；现有 CSS modules-by-file 风格。

---

## Reference Context

- Spec: `docs/superpowers/specs/2026-05-20-review-efficiency-design.md`
- PRD: `docs/产品PRD.md` 中 `PR-FE-004：审核界面`
- State contract: `docs/Shared/state-enums.md`
- Frontend boundary: `app/frontend/README.md`
- Current implementation:
  - `app/frontend/src/pages/review/ReviewPage.tsx`
  - `app/frontend/src/components/review/FieldList.tsx`
  - `app/frontend/src/components/review/ReviewSourcePanel.tsx`
  - `app/frontend/src/pages/review/review.css`
  - `app/frontend/src/pages/review/ReviewPage.test.tsx`
  - `app/frontend/tests/e2e/current-workflows.spec.ts`

## File Structure

- Modify: `app/frontend/src/components/layout/WorkstationLayout.tsx`
  - Allow review page to use the same shell and sidebar navigation as workstation/task pages.
  - Extend `activeRouteId` to include `review`, and add a visible review nav item only when the current review task id is available.
- Modify: `app/frontend/src/app/App.tsx`
  - Keep review route mounted through `ReviewPage`; no API behavior change.
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
  - Own page state: selected page, selected field, OCR visibility, OCR mode, dirty flag, saving/completing status, message.
  - Render inside `WorkstationLayout`.
  - Implement unified review completion.
- Modify: `app/frontend/src/components/review/FieldList.tsx`
  - Render editable field cards without per-field confirm button.
  - Emit field focus to parent for page/OCR linkage.
- Modify: `app/frontend/src/components/review/ReviewSourcePanel.tsx`
  - Reuse existing highlight logic; add empty-source message handling only if needed by tests.
- Modify: `app/frontend/src/pages/review/review.css`
  - Replace standalone page shell with workbench content styles.
  - Add two-column workbench, page tabs, collapsible OCR panel, field summary, save state styles.
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
  - Cover layout shell, OCR collapse, page switch, field edit, unified review completion, save failure.
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`
  - Update success flow button names and add OCR toggle assertions.

## Task 1: Shared Workstation Shell For Review

**Files:**
- Modify: `app/frontend/src/components/layout/WorkstationLayout.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write the failing test for global navigation on review page**

Add this test to `describe('ReviewPage', ...)` in `app/frontend/src/pages/review/ReviewPage.test.tsx`:

```tsx
it('uses the shared workstation navigation shell', async () => {
  mockReviewRoutes();
  render(<ReviewPage taskId="task_001" />);

  expect(await screen.findByRole('navigation', { name: '主要模块' })).toBeTruthy();
  expect(screen.getByRole('link', { name: /工作台总览/ }).getAttribute('href')).toBe('/');
  expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
  expect(screen.getByRole('link', { name: /人工审核/ }).getAttribute('aria-current')).toBe('page');
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: FAIL because `ReviewPage` currently renders a standalone `<main>` and no shared `WorkstationLayout` navigation.

- [ ] **Step 3: Extend `WorkstationLayout` active route and review nav support**

In `app/frontend/src/components/layout/WorkstationLayout.tsx`, replace the static `navigationItems` and prop type with this implementation:

```tsx
const baseNavigationItems = [
  { id: appRoutes.workstation.id, label: '工作台总览', href: appRoutes.workstation.path },
  { id: appRoutes.tasks.id, label: '任务管理', href: appRoutes.tasks.path }
];

type WorkstationLayoutProps = {
  children: ReactNode;
  activeRouteId?: 'workstation' | 'tasks' | 'review';
  reviewTaskHref?: string;
  headerKicker?: string;
  headerTitle?: string;
  systemStatus?: {
    tone: 'success' | 'warning' | 'danger' | 'neutral';
    title: string;
    subtitle: string;
  };
  isRetryingSystem?: boolean;
  onRetrySystem?: () => void;
};
```

Then update the function signature and navigation list inside `WorkstationLayout`:

```tsx
export function WorkstationLayout({
  children,
  activeRouteId = 'workstation',
  reviewTaskHref,
  headerKicker = '工作台总览',
  headerTitle = '病历文书结构化采集',
  systemStatus = {
    tone: 'success',
    title: '系统已启动',
    subtitle: '正在运行中'
  },
  isRetryingSystem = false,
  onRetrySystem
}: WorkstationLayoutProps) {
  const navigationItems = reviewTaskHref
    ? [
        ...baseNavigationItems,
        { id: appRoutes.review.id, label: '人工审核', href: reviewTaskHref }
      ]
    : baseNavigationItems;
```

Keep the existing `<nav>` mapping unchanged; it will now include the review item only when `reviewTaskHref` is passed.

- [ ] **Step 4: Wrap the review loading/error/success states in `WorkstationLayout`**

In `app/frontend/src/pages/review/ReviewPage.tsx`, update the React import and add layout imports:

```tsx
import { useEffect, useState, type ReactNode } from 'react';

import { buildReviewPath } from '../../app/routes';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
```

Add this helper inside the component before the loading branch:

```tsx
function renderShell(content: ReactNode) {
  return (
    <WorkstationLayout
      activeRouteId="review"
      reviewTaskHref={buildReviewPath(taskId)}
      headerKicker="人工审核"
      headerTitle={`任务 ${taskId}`}
    >
      {content}
    </WorkstationLayout>
  );
}
```

Replace the loading branch with:

```tsx
if (isLoading) {
  return renderShell(<main className="review-page" aria-label="人工审核页">正在加载审核数据</main>);
}
```

Replace the error branch with:

```tsx
if (!review) {
  return renderShell(
    <main className="review-page" aria-label="人工审核页">
      <p role="alert" className="review-alert review-alert--danger">{message ?? '审核数据加载失败'}</p>
    </main>
  );
}
```

Wrap the final success `<main>` in `renderShell(...)` instead of returning it directly.

- [ ] **Step 5: Run the focused test and verify it passes**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: PASS for the new navigation test and existing ReviewPage tests.

- [ ] **Step 6: Commit shell integration**

```bash
git add app/frontend/src/components/layout/WorkstationLayout.tsx app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "统一审核页工作站导航"
```

## Task 2: Review Page State Model And Current Page View

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Expand review mock to multiple pages**

Update `mockReviewRoutes()` in `app/frontend/src/pages/review/ReviewPage.test.tsx` so the `GET` review payload has two pages and two fields:

```tsx
review_result: {
  ocr_text: '第一页文本\n第二页文本',
  pages: [
    {
      page_id: 'page_001',
      page_no: 1,
      preview_url: '/api/tasks/task_001/images/page_001',
      parsed_text: '第一页文本'
    },
    {
      page_id: 'page_002',
      page_no: 2,
      preview_url: '/api/tasks/task_001/images/page_002',
      parsed_text: '第二页文本'
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
```

Also update the `PUT` handler to allow both fields and return the submitted field array:

```tsx
http.put('*/api/tasks/task_001/review', async ({ request }) => {
  const body = await request.json() as { fields: Array<Record<string, unknown>> };
  expect(body).toMatchObject({
    fields: expect.arrayContaining([
      expect.objectContaining({ field_key: 'patient_name' })
    ])
  });
  return HttpResponse.json({
    success: true,
    data: {
      task_id: 'task_001',
      status: 'review',
      review_result: {
        ocr_text: '第一页文本\n第二页文本',
        pages: [
          {
            page_id: 'page_001',
            page_no: 1,
            preview_url: '/api/tasks/task_001/images/page_001',
            parsed_text: '第一页文本'
          },
          {
            page_id: 'page_002',
            page_no: 2,
            preview_url: '/api/tasks/task_001/images/page_002',
            parsed_text: '第二页文本'
          }
        ],
        fields: body.fields
      }
    }
  });
})
```

- [ ] **Step 2: Write the failing current-page test**

Add:

```tsx
it('shows one current page image and switches pages without rendering all images', async () => {
  mockReviewRoutes();
  render(<ReviewPage taskId="task_001" />);

  expect(await screen.findByRole('img', { name: '第 1 页原图' })).toBeTruthy();
  expect(screen.queryByRole('img', { name: '第 2 页原图' })).toBeNull();

  await userEvent.click(screen.getByRole('button', { name: '第 2 页' }));

  expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
  expect(screen.queryByRole('img', { name: '第 1 页原图' })).toBeNull();
});
```

- [ ] **Step 3: Run the focused test and verify it fails**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: FAIL because `ReviewPage` currently renders all images vertically.

- [ ] **Step 4: Add current page state and derived values**

In `ReviewPage.tsx`, keep the React import from Task 1:

```tsx
import { useEffect, useState, type ReactNode } from 'react';
```

Add state:

```tsx
const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
const [selectedFieldKey, setSelectedFieldKey] = useState<string | null>(null);
```

Inside the `getReview(taskId).then(...)` success block, after `setFields(...)`, add:

```tsx
const firstPageId = payload.review_result.pages?.[0]?.page_id ?? null;
setSelectedPageId(firstPageId);
setSelectedFieldKey(payload.review_result.fields[0]?.field_key ?? null);
```

After the loading/error branches and before the final return, add:

```tsx
const pages = review.pages ?? [];
const selectedPage = pages.find((page) => page.page_id === selectedPageId) ?? pages[0] ?? null;
```

- [ ] **Step 5: Replace all-images rendering with page tabs and current image**

Replace the task image section in `ReviewPage.tsx` with:

```tsx
<section className="review-panel review-panel--image" aria-label="任务图片">
  <div className="review-panel__heading">
    <h2>任务图片</h2>
    <span>{pages.length ? `共 ${pages.length} 页` : '无页面'}</span>
  </div>
  {pages.length ? (
    <div className="review-page-tabs" role="tablist" aria-label="任务页码">
      {pages.map((page) => (
        <button
          aria-selected={page.page_id === selectedPage?.page_id}
          key={page.page_id}
          type="button"
          onClick={() => setSelectedPageId(page.page_id)}
        >
          第 {page.page_no} 页
        </button>
      ))}
    </div>
  ) : null}
  {selectedPage?.preview_url || selectedPage?.image_url ? (
    <img src={selectedPage.preview_url ?? selectedPage.image_url} alt={`第 ${selectedPage.page_no} 页原图`} />
  ) : (
    <p className="review-empty">后端未返回当前页原图</p>
  )}
</section>
```

- [ ] **Step 6: Update CSS for page tabs and current image**

In `review.css`, keep `.review-page-tabs` but add:

```css
.review-panel__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.review-panel__heading h2 {
  margin: 0;
}

.review-panel__heading span {
  color: #5d6b82;
  font-size: 13px;
}

.review-page-tabs button[aria-selected='true'] {
  border-color: #1f6feb;
  background: #eaf2ff;
  color: #174ea6;
}
```

- [ ] **Step 7: Run the focused test and verify it passes**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit current page view**

```bash
git add app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/review.css app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "优化审核页当前页预览"
```

## Task 3: Collapsible OCR Assistant Panel

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write the failing OCR collapse test**

Add:

```tsx
it('keeps OCR hidden by default and shows current page OCR on demand', async () => {
  mockReviewRoutes();
  render(<ReviewPage taskId="task_001" />);

  await screen.findByText('结构化字段');
  expect(screen.queryByText('第一页文本')).toBeNull();

  await userEvent.click(screen.getByRole('button', { name: '显示 OCR' }));
  expect(screen.getByText('第一页文本')).toBeTruthy();

  await userEvent.click(screen.getByRole('button', { name: '第 2 页' }));
  expect(screen.getByText('第二页文本')).toBeTruthy();
  expect(screen.queryByText('第一页文本')).toBeNull();

  await userEvent.click(screen.getByRole('button', { name: '隐藏 OCR' }));
  expect(screen.queryByText('第二页文本')).toBeNull();
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: FAIL because OCR currently renders as a permanent column.

- [ ] **Step 3: Add OCR visibility and mode state**

In `ReviewPage.tsx`, add:

```tsx
const [isOcrVisible, setIsOcrVisible] = useState(false);
const [ocrMode, setOcrMode] = useState<'page' | 'merged'>('page');
```

Add derived OCR text after `selectedPage`:

```tsx
const mergedOcrText = review.ocr_text ?? pages.map((page) => page.parsed_text ?? '').filter(Boolean).join('\n');
const currentPageOcrText = selectedPage?.parsed_text ?? mergedOcrText;
const visibleOcrText = ocrMode === 'page' ? currentPageOcrText : mergedOcrText;
```

- [ ] **Step 4: Replace permanent OCR column with collapsible panel**

Remove the permanent `<section aria-label="OCR 文本">...</section>`.

Add this section after the image section and before fields:

```tsx
<section className={`review-panel review-panel--ocr${isOcrVisible ? ' is-open' : ''}`} aria-label="OCR 文本">
  <div className="review-panel__heading">
    <h2>OCR 文本</h2>
    <button type="button" onClick={() => setIsOcrVisible((value) => !value)}>
      {isOcrVisible ? '隐藏 OCR' : '显示 OCR'}
    </button>
  </div>
  {isOcrVisible ? (
    <>
      <div className="review-text-actions" aria-label="OCR 文本范围">
        <button
          aria-pressed={ocrMode === 'page'}
          type="button"
          onClick={() => setOcrMode('page')}
        >
          当前页
        </button>
        <button
          aria-pressed={ocrMode === 'merged'}
          type="button"
          onClick={() => setOcrMode('merged')}
        >
          合并文本
        </button>
      </div>
      <ReviewSourcePanel text={visibleOcrText || '后端未返回 OCR 文本'} sourceMessage={null} />
    </>
  ) : null}
</section>
```

- [ ] **Step 5: Update grid CSS for OCR as auxiliary panel**

Replace `.review-grid` with:

```css
.review-grid {
  display: grid;
  grid-template-columns: minmax(260px, 0.9fr) minmax(420px, 1.4fr);
  gap: 12px;
  align-items: start;
}

.review-panel--ocr {
  grid-column: 1 / -1;
}
```

Keep the existing responsive media query, but ensure it still collapses to one column:

```css
@media (max-width: 1100px) {
  .review-grid {
    grid-template-columns: 1fr;
  }

  .review-source pre {
    min-height: 220px;
  }
}
```

- [ ] **Step 6: Run the focused test and verify it passes**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit OCR collapse**

```bash
git add app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/review.css app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "折叠审核页OCR辅助栏"
```

## Task 4: Field List Without Per-Field Confirmation

**Files:**
- Modify: `app/frontend/src/components/review/FieldList.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/review.css`
- Test: `app/frontend/src/pages/review/ReviewPage.test.tsx`

- [ ] **Step 1: Write the failing no-per-field-confirm test**

Add:

```tsx
it('does not require per-field confirmation and tracks field focus', async () => {
  mockReviewRoutes();
  render(<ReviewPage taskId="task_001" />);

  expect(await screen.findByLabelText('patient_name')).toBeTruthy();
  expect(screen.queryByRole('button', { name: '确认' })).toBeNull();

  await userEvent.click(screen.getByLabelText('chief_complaint'));
  expect(screen.getByText('来源：第 2 页')).toBeTruthy();
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: FAIL because `FieldList` currently renders per-field “确认” buttons and does not expose focus to the page.

- [ ] **Step 3: Update `FieldList` props**

Replace `FieldListProps` in `app/frontend/src/components/review/FieldList.tsx` with:

```tsx
type FieldListProps = {
  fields: ReviewField[];
  selectedFieldKey: string | null;
  onChange: (fields: ReviewField[]) => void;
  onFocusField: (field: ReviewField) => void;
  getStatusLabel: (status: FieldStatus) => string;
};
```

Update the function signature:

```tsx
export function FieldList({ fields, selectedFieldKey, onChange, onFocusField, getStatusLabel }: FieldListProps) {
```

- [ ] **Step 4: Remove per-field confirm and add focus/evidence display**

Replace the mapped field card in `FieldList.tsx` with:

```tsx
{fields.map((field) => {
  const sourcePageNo = field.evidence?.find((item) => item.page_no)?.page_no;
  const isSelected = field.field_key === selectedFieldKey;

  return (
    <article className={`review-field${isSelected ? ' is-selected' : ''}`} key={field.field_key}>
      <div className="review-field__header">
        <label htmlFor={`review-field-${field.field_key}`}>{field.label ?? field.field_key}</label>
        <span className={`review-field-status review-field-status--${field.status}`}>
          {getStatusLabel(field.status)}
        </span>
      </div>
      <textarea
        id={`review-field-${field.field_key}`}
        value={field.value}
        aria-label={field.field_key}
        onChange={(event) => updateField(field.field_key, event.currentTarget.value)}
        onFocus={() => onFocusField(field)}
      />
      {field.candidate_value ? <p className="review-candidate">候选值：{field.candidate_value}</p> : null}
      {sourcePageNo ? <p className="review-field__evidence">来源：第 {sourcePageNo} 页</p> : null}
    </article>
  );
})}
```

Remove the `confirmField()` function entirely.

- [ ] **Step 5: Wire field focus to selected page in `ReviewPage`**

Update `FieldList` usage in `ReviewPage.tsx`:

```tsx
<FieldList
  fields={fields}
  selectedFieldKey={selectedFieldKey}
  onChange={handleFieldsChange}
  onFocusField={handleFocusField}
  getStatusLabel={(fieldStatus) => fieldStatusMeta[fieldStatus].label}
/>
```

Add these handlers before the return:

```tsx
function handleFieldsChange(nextFields: ReviewField[]) {
  setFields(nextFields);
}

function handleFocusField(field: ReviewField) {
  setSelectedFieldKey(field.field_key);
  const evidence = field.evidence?.find((item) => item.page_id || item.page_no);
  if (evidence?.page_id) {
    setSelectedPageId(evidence.page_id);
    return;
  }
  const pageByNo = pages.find((page) => page.page_no === evidence?.page_no);
  if (pageByNo) setSelectedPageId(pageByNo.page_id);
}
```

- [ ] **Step 6: Add selected-field CSS**

Add to `review.css`:

```css
.review-field.is-selected {
  border-color: #1f6feb;
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.12);
}
```

- [ ] **Step 7: Run the focused test and verify it passes**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit field-list update**

```bash
git add app/frontend/src/components/review/FieldList.tsx app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/review.css app/frontend/src/pages/review/ReviewPage.test.tsx
git commit -m "改为审核页统一字段确认"
```

## Task 5: Unified Review Save And Complete Flow

**Files:**
- Modify: `app/frontend/src/pages/review/ReviewPage.tsx`
- Modify: `app/frontend/src/pages/review/ReviewPage.test.tsx`
- Modify: `app/frontend/tests/e2e/current-workflows.spec.ts`

- [ ] **Step 1: Write the failing unified completion test**

Add:

```tsx
it('saves unmodified fields as confirmed and modified fields as modified before completing', async () => {
  mockReviewRoutes();
  server.use(
    http.put('*/api/tasks/task_001/review', async ({ request }) => {
      const body = await request.json();
      expect(body).toMatchObject({
        fields: expect.arrayContaining([
          expect.objectContaining({ field_key: 'patient_name', value: '李四', status: 'modified' }),
          expect.objectContaining({ field_key: 'chief_complaint', value: '头痛三天', status: 'confirmed' })
        ])
      });
      return HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '第一页文本\n第二页文本',
            pages: [
              {
                page_id: 'page_001',
                page_no: 1,
                preview_url: '/api/tasks/task_001/images/page_001',
                parsed_text: '第一页文本'
              },
              {
                page_id: 'page_002',
                page_no: 2,
                preview_url: '/api/tasks/task_001/images/page_002',
                parsed_text: '第二页文本'
              }
            ],
            fields: [
              { field_key: 'patient_name', label: '姓名', value: '李四', status: 'modified' },
              { field_key: 'chief_complaint', label: '主诉', value: '头痛三天', status: 'confirmed' }
            ]
          }
        }
      });
    })
  );
  render(<ReviewPage taskId="task_001" />);

  const nameField = await screen.findByLabelText('patient_name');
  await userEvent.clear(nameField);
  await userEvent.type(nameField, '李四');
  await userEvent.click(screen.getByRole('button', { name: '统一审核并完成' }));

  expect(await screen.findByText('已完成')).toBeTruthy();
});
```

Keep the generic `PUT` handler in `mockReviewRoutes()` permissive. The strict unified-status assertion belongs only in this test so ordinary save tests can still verify partial edits without requiring unified completion.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: FAIL because the page still has separate save/complete behavior and does not batch-confirm unmodified fields.

- [ ] **Step 3: Add dirty/save status and unified field helper**

In `ReviewPage.tsx`, add state:

```tsx
const [saveStatus, setSaveStatus] = useState<'idle' | 'dirty' | 'saving' | 'saved' | 'failed'>('idle');
const [isCompleting, setIsCompleting] = useState(false);
```

Add helper functions before `handleSave`:

```tsx
function normalizeFieldsForUnifiedReview(currentFields: ReviewField[]) {
  return currentFields.map((field) =>
    field.status === 'unreviewed'
      ? { ...field, status: 'confirmed' as const }
      : field
  );
}

async function saveFields(nextFields: ReviewField[]) {
  setSaveStatus('saving');
  const saved = await saveReview(taskId, nextFields);
  setReview(saved.review_result);
  setFields(saved.review_result.fields);
  setSaveStatus('saved');
  setMessage('已保存');
  return saved.review_result.fields;
}
```

Update `handleFieldsChange`:

```tsx
function handleFieldsChange(nextFields: ReviewField[]) {
  setFields(nextFields);
  setSaveStatus('dirty');
}
```

- [ ] **Step 4: Update save and complete handlers**

Replace `handleSave`:

```tsx
async function handleSave() {
  try {
    await saveFields(fields);
  } catch (error) {
    setSaveStatus('failed');
    setMessage(error instanceof Error ? error.message : '保存失败，请重试');
  }
}
```

Replace `handleComplete`:

```tsx
async function handleComplete() {
  setIsCompleting(true);
  try {
    const unifiedFields = normalizeFieldsForUnifiedReview(fields);
    await saveFields(unifiedFields);
    const task = await completeTask(taskId);
    setStatus(task.status);
    setMessage('已完成');
  } catch (error) {
    setSaveStatus('failed');
    setMessage(error instanceof Error ? error.message : '统一审核完成失败');
  } finally {
    setIsCompleting(false);
  }
}
```

- [ ] **Step 5: Update header actions and save-state label**

Replace the header button block with:

```tsx
<div className="review-header__actions">
  <span className={`review-save-state review-save-state--${saveStatus}`}>
    {saveStatus === 'dirty'
      ? '未保存修改'
      : saveStatus === 'saving'
        ? '保存中'
        : saveStatus === 'saved'
          ? '已保存'
          : saveStatus === 'failed'
            ? '保存失败'
            : '无修改'}
  </span>
  <button type="button" onClick={() => void handleSave()} disabled={saveStatus === 'saving' || isCompleting}>
    保存
  </button>
  <button
    type="button"
    className="review-confirm-button"
    onClick={() => void handleComplete()}
    disabled={isCompleting || saveStatus === 'saving'}
  >
    {isCompleting ? '完成中' : '统一审核并完成'}
  </button>
</div>
```

Remove the old bottom “保存审核结果” button from the structure field section.

- [ ] **Step 6: Update ReviewPage unit-test button names**

In `app/frontend/src/pages/review/ReviewPage.test.tsx`, update the existing happy-path test from:

```tsx
await userEvent.click(screen.getByRole('button', { name: '保存审核结果' }));
expect(await screen.findByText('已保存')).toBeTruthy();
await userEvent.click(screen.getByRole('button', { name: '标记完成' }));
```

to:

```tsx
await userEvent.click(screen.getByRole('button', { name: '保存' }));
expect(await screen.findByText('已保存')).toBeTruthy();
await userEvent.click(screen.getByRole('button', { name: '统一审核并完成' }));
```

Update the completion-validation test from:

```tsx
await userEvent.click(screen.getByRole('button', { name: '标记完成' }));
```

to:

```tsx
await userEvent.click(screen.getByRole('button', { name: '统一审核并完成' }));
```

- [ ] **Step 7: Add keyboard shortcuts**

Add this effect in `ReviewPage.tsx`:

```tsx
useEffect(() => {
  function handleKeyDown(event: KeyboardEvent) {
    const isModifier = event.ctrlKey || event.metaKey;
    if (!isModifier) return;
    if (event.key.toLowerCase() === 's') {
      event.preventDefault();
      void handleSave();
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      void handleComplete();
    }
  }

  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, [fields, saveStatus, isCompleting]);
```

- [ ] **Step 8: Update E2E button names**

In `app/frontend/tests/e2e/current-workflows.spec.ts`, replace:

```ts
await page.getByRole('button', { name: '保存审核结果' }).click();
await page.getByRole('button', { name: '标记完成' }).click();
```

with:

```ts
await page.getByRole('button', { name: '保存' }).click();
await page.getByRole('button', { name: '统一审核并完成' }).click();
```

In the failed direct review test, replace:

```ts
await expect(page.getByRole('button', { name: '保存审核结果' })).toHaveCount(0);
```

with:

```ts
await expect(page.getByRole('button', { name: '统一审核并完成' })).toHaveCount(0);
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
npm --prefix app/frontend test -- ReviewPage.test.tsx
```

Expected: PASS.

- [ ] **Step 10: Run E2E smoke**

Run:

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin npm --prefix app/frontend run test:e2e
```

Expected: PASS. If sandbox blocks Vite listening on `127.0.0.1:5173`, rerun the same command with escalated permissions.

- [ ] **Step 11: Commit unified completion**

```bash
git add app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/tests/e2e/current-workflows.spec.ts
git commit -m "实现审核页统一审核完成"
```

## Task 6: Final Styling And Full Verification

**Files:**
- Modify: `app/frontend/src/pages/review/review.css`
- Verify: all touched frontend tests and backend regression tests

- [ ] **Step 1: Polish review workbench CSS**

Update `review.css` so `.review-page` no longer creates a competing full-screen shell:

```css
.review-page {
  color: #18202f;
}

.review-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.review-header__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.review-save-state {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  border: 1px solid #d8dee8;
  border-radius: 6px;
  padding: 0 10px;
  background: #ffffff;
  color: #5d6b82;
  font-size: 13px;
}

.review-save-state--dirty,
.review-save-state--failed {
  border-color: #f0c36d;
  background: #fff8e6;
  color: #7a4f00;
}

.review-save-state--saved {
  border-color: #b7dfc4;
  background: #e8f7ee;
  color: #17643a;
}
```

Keep button radius at 6px or less, avoid nested card styling, and ensure mobile layouts collapse to one column without text overlap.

- [ ] **Step 2: Run frontend unit tests**

Run:

```bash
npm --prefix app/frontend test
```

Expected: PASS, including `ReviewPage.test.tsx`.

- [ ] **Step 3: Run frontend build**

Run:

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin npm --prefix app/frontend run build
```

Expected: PASS.

- [ ] **Step 4: Run frontend E2E**

Run:

```bash
env -i HOME=$HOME PATH=/usr/bin:/bin npm --prefix app/frontend run test:e2e
```

Expected: PASS. If sandbox blocks Vite listening on `127.0.0.1:5173`, rerun the same command with escalated permissions.

- [ ] **Step 5: Run backend regression**

Run:

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests -q
```

Expected: PASS. This confirms no API expectation changed.

- [ ] **Step 6: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 7: Commit final styling and verification fixes**

```bash
git add app/frontend/src/pages/review/review.css app/frontend/src/pages/review/ReviewPage.tsx app/frontend/src/components/review/FieldList.tsx app/frontend/src/pages/review/ReviewPage.test.tsx app/frontend/tests/e2e/current-workflows.spec.ts
git commit -m "完善审核页效率优化样式"
```

## Review Notes

- The plan intentionally avoids backend changes because the spec says to reuse current API contracts.
- The plan intentionally removes per-field confirmation UI but preserves field statuses by converting unmodified `unreviewed` fields to `confirmed` during unified completion.
- The OCR panel is hidden by default and only renders text after the user clicks “显示 OCR”, matching the doctor-efficiency requirement.
- The review page is brought under `WorkstationLayout` so the main app navigation remains consistent with the home page and task page.
- No task adds manual field creation, schema inference, OCR parsing, image preprocessing, quad selection, or fallback extraction.
