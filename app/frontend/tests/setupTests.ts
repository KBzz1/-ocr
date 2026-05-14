import { afterAll, afterEach, beforeAll } from 'vitest';
import { setupServer } from 'msw/node';

const allowedHosts = [
  'localhost',
  '127.0.0.1',
  '0.0.0.0',
  '::1',
  'host.docker.internal'
];

function isPrivateLanHost(hostname: string) {
  return (
    /^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(hostname) ||
    /^192\.168\.\d{1,3}\.\d{1,3}$/.test(hostname) ||
    /^172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}$/.test(hostname)
  );
}

function isAllowedLocalRequest(request: Request) {
  const url = new URL(request.url);

  return (
    url.origin === window.location.origin ||
    allowedHosts.includes(url.hostname) ||
    isPrivateLanHost(url.hostname)
  );
}

type MswServer = ReturnType<typeof setupServer>;

const testGlobal = globalThis as typeof globalThis & {
  __manzufeiOcrMswServer?: MswServer;
};

export const server = testGlobal.__manzufeiOcrMswServer ?? setupServer();
testGlobal.__manzufeiOcrMswServer = server;

beforeAll(() => {
  server.listen({
    onUnhandledRequest(request) {
      if (!isAllowedLocalRequest(request)) {
        throw new Error(`测试禁止外部网络请求: ${request.method} ${request.url}`);
      }

      throw new Error(`测试发现未 mock 的 API 请求: ${request.method} ${request.url}`);
    }
  });
});

afterEach(() => {
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});
