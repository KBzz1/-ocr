import { expect, test } from '@playwright/test';

const systemStatusApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\/system\/status$/;
const tasksApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\/tasks$/;
const captureSessionsApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\/capture-sessions$/;
const localApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\//;

const systemStatus = {
  success: true,
  data: {
    status: 'running',
    version: 'test',
    started_at: '2026-05-13T10:00:00+08:00',
    lan_addresses: ['192.168.1.5:8081']
  }
};

const session = {
  session_id: 'sess_e2e',
  status: 'active',
  created_at: '2026-05-13T10:00:00+08:00',
  expires_at: '2026-05-13T10:30:00+08:00',
  qr_code_url: 'http://192.168.1.5:8081/mobile/sess_e2e',
  page_count: 0
};

const tasks = {
  success: true,
  data: {
    tasks: []
  }
};

test.beforeEach(async ({ page }) => {
  const unmockedApiRequests: string[] = [];
  const externalRequests: string[] = [];

  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      externalRequests.push(request.url());
    }
  });

  await page.route(localApi, async (route) => {
    unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });
  await page.route(captureSessionsApi, async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({ status: 201, json: { success: true, data: session } });
      return;
    }
    unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });
  await page.route(tasksApi, async (route) => {
    await route.fulfill({ json: tasks });
  });
  await page.route(systemStatusApi, async (route) => {
    await route.fulfill({ json: systemStatus });
  });

  await page.exposeFunction('__assertNetworkGate', () => {
    expect(unmockedApiRequests).toEqual([]);
    expect(externalRequests).toEqual([]);
  });
});

test('loads workstation without external requests or homepage address exposure', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text());
    }
  });

  await page.goto('/');
  await expect(page.getByText('系统已启动')).toBeVisible();
  await expect(page.getByText('离线运行')).toHaveCount(0);
  await expect(page.getByText('手机采集可用')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/https?:\/\/|127\.0\.0\.1|localhost|192\.168\./);
  await expect(page.locator('body')).not.toContainText(/mobile\/|capture\?session=/);
  expect(consoleErrors).toEqual([]);
  await page.evaluate(() => window.__assertNetworkGate());
});

test('opens QR modal after creating a capture session', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '新建采集' }).click();

  const dialog = page.getByRole('dialog', { name: '采集二维码' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('img', { name: '采集二维码' })).toBeVisible();
  await expect(dialog).toContainText('会话已创建');
  await expect(dialog).toContainText('已上传');
  await expect(page.locator('body')).not.toContainText('http://192.168.1.5:8081/mobile/sess_e2e');
  await page.evaluate(() => window.__assertNetworkGate());
});

declare global {
  interface Window {
    __assertNetworkGate: () => void;
  }
}
