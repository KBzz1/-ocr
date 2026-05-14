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

export type QuadPoint = {
  x: number;
  y: number;
};

export interface CapturePageUploadInput {
  file: File;
  width: number;
  height: number;
  quad_points: QuadPoint[];
}

export interface CapturePageUploadResult {
  page_id: string;
  page_index: number;
  status: 'uploaded';
}

export interface FinishCaptureSessionResult {
  session_id: string;
  status: 'locked';
  task_id: string;
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

export function uploadCapturePage(sessionId: string, input: CapturePageUploadInput) {
  const formData = new FormData();
  formData.set('file', input.file);
  formData.set('width', String(input.width));
  formData.set('height', String(input.height));
  formData.set('quad_points', JSON.stringify(input.quad_points));

  return apiRequest<CapturePageUploadResult>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/pages`,
    {
      method: 'POST',
      body: formData
    }
  );
}

export function finishCaptureSession(sessionId: string) {
  return apiRequest<FinishCaptureSessionResult>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/finish`,
    { method: 'POST' }
  );
}
