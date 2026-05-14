import { describe, it, expect } from 'vitest';
import { buildQrCodeUrl, type CaptureSession } from './captureSessions';

const baseSession: CaptureSession = {
  session_id: 'abc-123',
  status: 'active',
  created_at: '2026-05-14T00:00:00Z',
  expires_at: '2026-05-14T00:30:00Z',
  qr_code_url: 'http://192.168.1.5:8081/mobile/sessions/abc-123',
  page_count: 0,
};

describe('buildQrCodeUrl', () => {
  it('FE-NW-001: 生产模式原样返回后端 URL', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: false,
      currentHref: 'http://localhost:8081/',
    });
    expect(result).toBe('http://192.168.1.5:8081/mobile/sessions/abc-123');
  });

  it('FE-NW-002: 开发模式将端口转为 Vite origin', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: true,
      currentHref: 'http://192.168.1.5:5173/',
    });
    expect(result).toBe('http://192.168.1.5:5173/mobile/sessions/abc-123');
  });

  it('开发模式保留当前 origin 的 hostname 和 port', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: true,
      currentHref: 'http://10.0.0.99:3000/some-page',
    });
    expect(result).toBe('http://10.0.0.99:3000/mobile/sessions/abc-123');
  });

  it('session_id 含特殊字符时正确编码', () => {
    const session: CaptureSession = {
      ...baseSession,
      session_id: 'abc/123?x=1',
      qr_code_url: 'http://192.168.1.5:8081/mobile/sessions/abc/123?x=1',
    };
    const result = buildQrCodeUrl(session, {
      isDev: false,
      currentHref: 'http://localhost:8081/',
    });
    expect(result).toBe('http://192.168.1.5:8081/mobile/sessions/abc/123?x=1');
  });
});
