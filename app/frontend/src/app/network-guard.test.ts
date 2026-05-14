import { describe, expect, it } from 'vitest';

describe('MSW network guard', () => {
  it('fails any local API request that was not mocked by the test', async () => {
    const response = await fetch(`${window.location.origin}/api/unmocked`);
    expect(response.status).toBe(500);
    expect(await response.text()).toContain('测试发现未 mock 的 API 请求');
  });
});
