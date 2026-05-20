import { expect, test } from '@playwright/test';

const localApi = /^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?\/api\//;

test.beforeEach(async ({ page }) => {
  const unmockedApiRequests: string[] = [];

  await page.route(localApi, async (route) => {
    unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`);
    await route.abort();
  });
  await page.route('**/api/tasks', async (route) => {
    await route.fulfill({
      json: {
        success: true,
        data: {
          tasks: [{
            task_id: 'task_failed_001',
            status: 'failed',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 3,
            error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
            error_message: '算法模块未配置'
          }]
        }
      }
    });
  });

  await page.exposeFunction('__assertNetworkGate', () => {
    expect(unmockedApiRequests).toEqual([]);
  });
});

test('failed algorithm task shows reason in task management', async ({ page }) => {
  await page.goto('/tasks');

  await expect(page.getByText('task_failed_001')).toBeVisible();
  const taskTable = page.getByRole('table', { name: '任务列表' });
  await expect(taskTable.getByText('失败', { exact: true })).toBeVisible();
  await expect(page.getByText('算法模块未配置').first()).toBeVisible();
  await expect(page.getByRole('button', { name: '重新处理' })).toBeVisible();
  await expect(page.getByText('修订采集')).toHaveCount(0);
  await expect(page.getByText('取消会话')).toHaveCount(0);
});

declare global {
  interface Window {
    __assertNetworkGate: () => void;
  }
}
