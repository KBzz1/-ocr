import { http, HttpResponse } from 'msw';

import { activeSession } from './sessions';

export function makeImageFile(name = 'record.jpg', size = 16) {
  return new File([new Uint8Array(size)], name, { type: 'image/jpeg' });
}

export function makeLargeImageFile() {
  return new File([new Uint8Array(20 * 1024 * 1024 + 1)], 'large.jpg', {
    type: 'image/jpeg'
  });
}

export function mockUploadCapturePageSuccess(
  sessionId = activeSession.session_id,
  onUpload?: (request: Request) => void | Promise<void>
) {
  return http.post('*/api/mobile/:sessionId/pages', async ({ params, request }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }
    await onUpload?.(request);

    return HttpResponse.json({
      success: true,
      data: {
        page_id: `page_${Date.now()}`,
        page_index: 1,
        status: 'uploaded'
      }
    });
  });
}

export function mockUpdateCapturePageQuad(sessionId = activeSession.session_id) {
  return http.put('*/api/mobile/:sessionId/pages/:pageId/quad', async ({ params, request }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }
    const body = await request.json() as { quad_points: Array<{ x: number; y: number }> };
    return HttpResponse.json({
      success: true,
      data: {
        page_id: params.pageId,
        page_no: 1,
        quad_points: body.quad_points,
        quad_updated_at: '2026-05-14T08:05:00+00:00'
      }
    });
  });
}

export function mockReplaceCapturePageImage(sessionId = activeSession.session_id) {
  return http.put('*/api/mobile/:sessionId/pages/:pageId/image', ({ params }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }
    return HttpResponse.json({
      success: true,
      data: {
        page_id: params.pageId,
        page_index: 1,
        status: 'uploaded'
      }
    });
  });
}

export function mockUploadCapturePageError(sessionId = activeSession.session_id) {
  return http.post('*/api/mobile/:sessionId/pages', ({ params }) => {
    if (params.sessionId !== sessionId) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: '会话不存在', details: {} } },
        { status: 404 }
      );
    }

    return HttpResponse.json(
      {
        error: {
          code: 'UPLOAD_FAILED',
          message: '上传失败，请重试',
          details: {}
        }
      },
      { status: 500 }
    );
  });
}
