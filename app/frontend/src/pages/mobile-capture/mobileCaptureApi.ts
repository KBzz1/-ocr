import { apiRequest } from '../../api/client';
import {
  buildCapturePageFormData,
  type CapturePageUploadInput,
  type CapturePageUploadResult,
  type QuadPoint
} from '../../api/captureSessions';

export interface UpdateCapturePageQuadResult {
  page_id: string;
  page_no: number;
  quad_points: QuadPoint[];
  quad_updated_at?: string;
}

export function deleteCapturePage(sessionId: string, pageId: string) {
  return apiRequest<{ ok: boolean }>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}`,
    { method: 'DELETE' }
  );
}

export function reorderCapturePages(sessionId: string, pageIds: string[]) {
  return apiRequest<{ ok: boolean }>(
    `/api/capture-sessions/${encodeURIComponent(sessionId)}/pages/order`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page_ids: pageIds })
    }
  );
}

export function updateCapturePageQuad(sessionId: string, pageId: string, quadPoints: QuadPoint[]) {
  return apiRequest<UpdateCapturePageQuadResult>(
    `/api/mobile/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}/quad`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quad_points: quadPoints })
    }
  );
}

export function replaceCapturePageImage(
  sessionId: string,
  pageId: string,
  input: CapturePageUploadInput
) {
  return apiRequest<CapturePageUploadResult>(
    `/api/mobile/${encodeURIComponent(sessionId)}/pages/${encodeURIComponent(pageId)}/image`,
    {
      method: 'PUT',
      body: buildCapturePageFormData(input)
    }
  );
}
