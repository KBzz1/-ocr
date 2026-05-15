import { expect, test, type Page, type Route } from '@playwright/test';

const localApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\//;
const imageFixture = 'src/assets/logos/xinqiao-hospital-logo.jpg';

const readyTask = {
  task_id: 'task-ready',
  session_id: 'sess-ready',
  status: 'ready_for_review',
  created_at: '2026-05-13T09:30:00+08:00',
  page_count: 3,
  error_code: null,
  error_message: null,
  review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 1 },
  export_summary: { formats: [] }
};

const failedTask = {
  task_id: 'task-failed',
  session_id: 'sess-failed',
  status: 'failed',
  created_at: '2026-05-13T09:10:00+08:00',
  page_count: 1,
  error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
  error_message: '算法模块未配置，无法生成结构化字段',
  review_summary: { status: null, confirmed_count: 0, total_count: 0 },
  export_summary: { formats: [] }
};

const confirmedTask = {
  ...readyTask,
  task_id: 'task-confirmed',
  status: 'confirmed',
  review_summary: { status: 'confirmed', confirmed_count: 1, total_count: 1 }
};

const activeSession = {
  session_id: 'sess-e2e',
  status: 'active',
  created_at: '2026-05-13T10:00:00+08:00',
  expires_at: '2026-05-13T10:30:00+08:00',
  qr_code_url: 'http://192.168.1.5:8081/mobile/sess-e2e',
  page_count: 0,
  pages: []
};

const reviewTaskDetail = {
  ...readyTask,
  pages: [
    {
      page_id: 'page-001',
      page_no: 1,
      status: 'processed',
      image_url: '/api/tasks/task-ready/pages/page-001/image',
      parsed_text: '第1页解析文本：主诉 头痛三天'
    }
  ]
};

const failedTaskDetail = {
  ...failedTask,
  pages: []
};

const reviewResult = {
  task_id: 'task-ready',
  fields: [
    {
      field_key: 'chief_complaint',
      label: '主诉',
      candidate_value: '头痛三天',
      final_value: '头痛三天',
      status: 'unreviewed',
      evidence: [{ page_id: 'page-001', page_no: 1, text: '头痛三天' }]
    }
  ],
  summary: {
    unreviewed: 1,
    suspicious: 0,
    empty: 0,
    confirmed: 0
  }
};

async function installNetworkGate(page: Page) {
  const unmockedApiRequests: string[] = [];
  const externalRequests: string[] = [];
  const consoleErrors: string[] = [];

  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      externalRequests.push(request.url());
    }
  });
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.route(localApi, async (route) => {
    unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });

  await page.exposeFunction('__assertE2eNetworkGate', () => {
    expect(unmockedApiRequests).toEqual([]);
    expect(externalRequests).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({ status, json: { success: true, data } });
}

test.beforeEach(async ({ page }) => {
  await installNetworkGate(page);
});

test('lists ready and failed tasks with review and retry actions', async ({ page }) => {
  await page.route('**/api/tasks', async (route) => {
    await fulfillJson(route, { tasks: [readyTask, failedTask] });
  });
  await page.route('**/api/tasks/task-failed/retry', async (route) => {
    await fulfillJson(route, { task_id: 'task-failed', status: 'processing' });
  });

  await page.goto('/tasks');

  await expect(page.getByRole('main', { name: '任务列表页' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'task-ready' })).toBeVisible();
  await expect(page.getByRole('link', { name: '开始审核' })).toHaveAttribute(
    'href',
    '/tasks/task-ready/review'
  );
  await expect(page.getByText('算法模块未配置，无法生成结构化字段').first()).toBeVisible();

  await page.getByRole('button', { name: '待审核' }).click();
  await expect(page.getByRole('cell', { name: 'task-ready' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'task-failed' })).toHaveCount(0);

  await page.getByRole('button', { name: '失败' }).click();
  await expect(page.getByRole('cell', { name: 'task-failed' })).toBeVisible();
  await page.getByRole('button', { name: '重新处理' }).click();
  await page.getByRole('button', { name: '全部' }).click();
  await expect(page.getByText('处理中')).toBeVisible();

  await page.evaluate(() => window.__assertE2eNetworkGate());
});

test('reviews current fields and blocks confirm until field status is resolved', async ({ page }) => {
  const savedFields: Array<{ fieldKey: string; payload: unknown }> = [];
  let confirmCalls = 0;

  await page.route('**/api/tasks/task-ready', async (route) => {
    await fulfillJson(route, reviewTaskDetail);
  });
  await page.route('**/api/tasks/task-ready/review', async (route) => {
    await fulfillJson(route, reviewResult);
  });
  await page.route('**/api/tasks/task-ready/pages/page-001/image', async (route) => {
    await route.fulfill({ path: imageFixture, contentType: 'image/jpeg' });
  });
  await page.route('**/api/tasks/task-ready/review/fields/chief_complaint', async (route) => {
    const payload = await route.request().postDataJSON();
    savedFields.push({ fieldKey: 'chief_complaint', payload });
    await fulfillJson(route, {
      field_key: 'chief_complaint',
      final_value: payload.final_value,
      status: payload.status
    });
  });
  await page.route('**/api/tasks/task-ready/review/confirm', async (route) => {
    confirmCalls += 1;
    await fulfillJson(route, { task_id: 'task-ready', status: 'confirmed' });
  });

  await page.goto('/tasks/task-ready/review');

  await expect(page.getByRole('main', { name: '人工审核页' })).toBeVisible();
  await expect(page.getByText('第1页解析文本：主诉 头痛三天')).toBeVisible();

  await page.getByLabel('主诉').fill('头痛三天，伴恶心');
  await page.getByLabel('主诉').blur();
  await expect.poll(() => savedFields.at(-1)?.payload).toEqual({
    final_value: '头痛三天，伴恶心',
    status: 'modified'
  });
  await expect(page.getByText('已修改')).toBeVisible();

  await page.getByRole('button', { name: '标记存疑' }).click();
  await expect(page.getByText('存疑', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认审核' }).click();
  await expect(page.getByRole('alert')).toContainText('仍有 1 个存疑字段');
  expect(confirmCalls).toBe(0);

  await page.getByRole('button', { name: '确认', exact: true }).click();
  await expect(page.getByText('已确认', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认审核' }).click();
  await expect(page.getByRole('alert')).toContainText('审核已确认');
  expect(confirmCalls).toBe(1);

  await page.evaluate(() => window.__assertE2eNetworkGate());
});

test('shows failed review state without manual fallback path', async ({ page }) => {
  let retryCalls = 0;

  await page.route('**/api/tasks/task-failed', async (route) => {
    await fulfillJson(route, failedTaskDetail);
  });
  await page.route('**/api/tasks/task-failed/retry', async (route) => {
    retryCalls += 1;
    await fulfillJson(route, { task_id: 'task-failed', status: 'processing' });
  });

  await page.goto('/tasks/task-failed/review');

  await expect(page.getByRole('alert')).toContainText('算法模块未配置，无法生成结构化字段');
  await expect(page.getByRole('button', { name: '重新处理' })).toBeVisible();
  await expect(page.getByRole('button', { name: '确认审核' })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/人工补录|继续确认|导出/);
  await page.getByRole('button', { name: '重新处理' }).click();
  expect(retryCalls).toBe(1);

  await page.evaluate(() => window.__assertE2eNetworkGate());
});

test('exports confirmed task as JSON and Excel downloads', async ({ page }) => {
  await page.route('**/api/tasks/task-confirmed', async (route) => {
    await fulfillJson(route, confirmedTask);
  });
  await page.route('**/api/tasks/task-confirmed/export/json', async (route) => {
    await route.fulfill({
      body: JSON.stringify({ task_id: 'task-confirmed', fields: [] }),
      headers: { 'content-type': 'application/json' }
    });
  });
  await page.route('**/api/tasks/task-confirmed/export/excel', async (route) => {
    await route.fulfill({
      body: 'excel',
      headers: {
        'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }
    });
  });

  await page.goto('/tasks/task-confirmed/export');

  await expect(page.getByRole('main', { name: '导出页' })).toBeVisible();
  await expect(page.getByRole('button', { name: '导出 JSON' })).toBeEnabled();
  const jsonDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出 JSON' }).click();
  await expect((await jsonDownload).suggestedFilename()).toBe('task-confirmed.json');

  const excelDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出 Excel' }).click();
  await expect((await excelDownload).suggestedFilename()).toBe('task-confirmed.xlsx');

  await page.evaluate(() => window.__assertE2eNetworkGate());
});

test('captures three mobile pages and locks the session after finish', async ({ page }) => {
  let uploadedPages = 0;

  await page.route('**/api/capture-sessions/sess-e2e', async (route) => {
    await fulfillJson(route, { ...activeSession, page_count: uploadedPages });
  });
  await page.route('**/api/mobile/sess-e2e/pages', async (route) => {
    const form = await route.request().postDataBuffer();
    if (!form) throw new Error('Expected upload request to contain multipart form data');
    expect(form.byteLength).toBeGreaterThan(0);
    uploadedPages += 1;
    await fulfillJson(
      route,
      { page_id: `page-${String(uploadedPages).padStart(3, '0')}`, page_index: uploadedPages, status: 'uploaded' },
      201
    );
  });
  await page.route('**/api/mobile/sess-e2e/finish', async (route) => {
    await fulfillJson(route, { session_id: 'sess-e2e', status: 'locked', task_id: 'task-ready' });
  });

  await page.goto('/mobile/sessions/sess-e2e');

  await expect(page.getByRole('main', { name: '手机采集页' })).toBeVisible();
  await expect(page.getByText('采集会话进行中')).toBeVisible();

  for (let pageNo = 1; pageNo <= 3; pageNo += 1) {
    await page.locator('input[type="file"]').setInputFiles(imageFixture);
    await expect(page.getByRole('region', { name: '调整识别范围' })).toBeVisible();
    await page.getByRole('button', { name: '确认上传' }).click();
    await expect(page.getByRole('listitem', { name: new RegExp(`第 ${pageNo} 页 已上传`) })).toBeVisible();
  }

  await expect(page.getByText('已采集 3 页')).toBeVisible();
  await page.getByRole('button', { name: '完成采集' }).click();
  await expect(page.getByText('采集已完成，请在电脑端查看')).toBeVisible();
  await expect(page.getByRole('button', { name: '继续拍下一页' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '完成采集' })).toBeDisabled();

  await page.evaluate(() => window.__assertE2eNetworkGate());
});

declare global {
  interface Window {
    __assertE2eNetworkGate: () => void;
  }
}
