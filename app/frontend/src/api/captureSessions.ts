import { apiRequest, ApiError } from './client';

export type CaptureSessionStatus = 'active' | 'expired' | 'locked' | 'cancelled';

export interface CaptureSession {
  session_id: string;
  status: CaptureSessionStatus;
  created_at: string;
  expires_at: string;
  qr_code_url: string;
  page_count: number;
  pages?: Array<{
    page_id: string;
    page_no: number;
  }>;
}

function assertMobileQrUrl(session: CaptureSession) {
  const url = new URL(session.qr_code_url);
  if (url.hostname === '127.0.0.1' || url.hostname === 'localhost') {
    throw new ApiError('二维码地址不能使用本机回环地址', 'INVALID_QR_CODE_URL', 200);
  }
}

export async function createCaptureSession() {
  const session = await apiRequest<CaptureSession>('/api/capture-sessions', { method: 'POST' });
  assertMobileQrUrl(session);
  return session;
}

export function getCaptureSession(sessionId: string) {
  return apiRequest<CaptureSession>(`/api/capture-sessions/${encodeURIComponent(sessionId)}`);
}
