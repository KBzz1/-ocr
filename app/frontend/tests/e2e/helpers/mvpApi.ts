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
