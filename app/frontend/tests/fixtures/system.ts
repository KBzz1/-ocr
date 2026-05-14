import { http, HttpResponse } from 'msw';

export const runningSystemStatus = {
  success: true,
  data: {
    status: 'running',
    version: 'test',
    started_at: '2026-05-13T10:00:00+08:00',
    lan_addresses: ['192.168.1.5:8081']
  }
};

export function mockSystemStatus(body = runningSystemStatus) {
  return http.get('*/api/system/status', () => HttpResponse.json(body));
}

export function mockSystemStatusError() {
  return http.get('*/api/system/status', () =>
    HttpResponse.json(
      {
        error: {
          code: 'INTERNAL_SERVER_ERROR',
          message: '系统状态异常',
          details: {}
        }
      },
      { status: 500 }
    )
  );
}
