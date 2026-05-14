import { http, HttpResponse } from 'msw';

export const activeSession = {
  session_id: 'sess_001',
  status: 'active',
  created_at: '2026-05-13T10:00:00+08:00',
  expires_at: '2026-05-13T10:30:00+08:00',
  qr_code_url: 'http://192.168.1.5:8081/mobile/sess_001',
  page_count: 2
};

export function mockCreateCaptureSession(body = { success: true, data: activeSession }) {
  return http.post('*/api/capture-sessions', () => HttpResponse.json(body, { status: 201 }));
}

export function mockCreateCaptureSessionError() {
  return http.post('*/api/capture-sessions', () =>
    HttpResponse.json(
      {
        error: {
          code: 'INTERNAL_SERVER_ERROR',
          message: '创建失败',
          details: {}
        }
      },
      { status: 500 }
    )
  );
}

export function mockGetCaptureSession(session = activeSession) {
  return http.get(`*/api/capture-sessions/${session.session_id}`, () =>
    HttpResponse.json({ success: true, data: session })
  );
}

export function mockUploadCapturePage(sessionId = activeSession.session_id) {
  return http.post(`*/api/capture-sessions/${sessionId}/pages`, () =>
    HttpResponse.json({
      success: true,
      data: {
        page_id: 'page_001',
        page_index: 1,
        status: 'uploaded'
      }
    })
  );
}

export function mockFinishCaptureSession(sessionId = activeSession.session_id) {
  return http.post(`*/api/capture-sessions/${sessionId}/finish`, () =>
    HttpResponse.json({
      success: true,
      data: {
        session_id: sessionId,
        status: 'locked',
        task_id: 'task_001'
      }
    })
  );
}
