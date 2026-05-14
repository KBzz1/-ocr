import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import {
  buildCapturePageFormData,
  finishCaptureSession,
  getCaptureSession,
  uploadCapturePage
} from './captureSessions';
import { exportTaskExcel, exportTaskJson } from './export';
import { normalizeApiError } from './errors';
import {
  confirmReview,
  getReviewResult,
  saveReviewField
} from './review';
import { getTaskDetail, retryTaskProcessing } from './tasks';
import {
  fieldStatusMeta,
  sessionStatusMeta,
  taskStatusMeta
} from '../styles/status';
import { server } from '../../tests/setupTests';

describe('shared frontend contracts', () => {
  it('maps task, session and field states to Chinese labels', () => {
    expect(taskStatusMeta.ready_for_review.label).toBe('待审核');
    expect(taskStatusMeta.processing.label).toBe('处理中');
    expect(taskStatusMeta.failed.label).toBe('处理失败');
    expect(sessionStatusMeta.active.label).toBe('采集中');
    expect(sessionStatusMeta.locked.label).toBe('已完成采集');
    expect(fieldStatusMeta.unreviewed.label).toBe('未审核');
    expect(fieldStatusMeta.suspicious.label).toBe('存疑');
  });

  it('loads capture session, uploads page metadata and finishes capture', async () => {
    let uploadEndpointWasCalled = false;
    const uploadInput = {
      file: new File(['image'], 'page.jpg', { type: 'image/jpeg' }),
      width: 1200,
      height: 1600,
      quad_points: [
        { x: 0, y: 0 },
        { x: 1200, y: 0 },
        { x: 1200, y: 1600 },
        { x: 0, y: 1600 }
      ]
    };
    const formData = buildCapturePageFormData(uploadInput);

    expect(formData.get('image')).toBe(uploadInput.file);
    expect(formData.get('image_width')).toBe('1200');
    expect(formData.get('image_height')).toBe('1600');
    expect(formData.get('quad_points')).toBe(JSON.stringify(uploadInput.quad_points));

    server.use(
      http.get('*/api/capture-sessions/sess_001', () =>
        HttpResponse.json({
          success: true,
          data: {
            session_id: 'sess_001',
            status: 'active',
            created_at: '2026-05-14T10:00:00+08:00',
            expires_at: '2026-05-14T10:30:00+08:00',
            qr_code_url: 'http://192.168.1.5:8081/mobile/sess_001',
            page_count: 1
          }
        })
      ),
      http.post('*/api/mobile/sess_001/pages', () => {
        uploadEndpointWasCalled = true;
        return HttpResponse.json({
          success: true,
          data: {
            page_id: 'page_001',
            page_index: 1,
            status: 'uploaded'
          }
        });
      }),
      http.post('*/api/mobile/sess_001/finish', () =>
        HttpResponse.json({
          success: true,
          data: {
            session_id: 'sess_001',
            status: 'locked',
            task_id: 'task_001'
          }
        })
      )
    );

    await expect(getCaptureSession('sess_001')).resolves.toMatchObject({ session_id: 'sess_001' });
    await expect(uploadCapturePage('sess_001', uploadInput)).resolves.toMatchObject({ page_id: 'page_001' });
    expect(uploadEndpointWasCalled).toBe(true);
    await expect(finishCaptureSession('sess_001')).resolves.toMatchObject({ task_id: 'task_001' });
  });

  it('loads task detail and retries failed processing', async () => {
    server.use(
      http.get('*/api/tasks/task_failed', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            session_id: 'sess_failed',
            status: 'failed',
            created_at: '2026-05-14T10:00:00+08:00',
            page_count: 2,
            error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
            error_message: '图像处理模块未配置'
          }
        })
      ),
      http.post('*/api/tasks/task_failed/retry', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            status: 'processing'
          }
        })
      )
    );

    await expect(getTaskDetail('task_failed')).resolves.toMatchObject({ status: 'failed' });
    await expect(retryTaskProcessing('task_failed')).resolves.toMatchObject({ status: 'processing' });
  });

  it('loads review result, saves a field and confirms review', async () => {
    server.use(
      http.get('*/api/tasks/task_ready/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_ready',
            fields: [
              {
                field_key: 'chief_complaint',
                label: '主诉',
                candidate_value: '头痛三天',
                final_value: '',
                status: 'unreviewed',
                evidence: []
              }
            ],
            summary: { unreviewed: 1, suspicious: 0, empty: 0, confirmed: 0 }
          }
        })
      ),
      http.put('*/api/tasks/task_ready/review/fields/chief_complaint', async ({ request }) => {
        await expect(request.json()).resolves.toMatchObject({
          final_value: '头痛三天',
          status: 'confirmed'
        });
        return HttpResponse.json({
          success: true,
          data: {
            field_key: 'chief_complaint',
            final_value: '头痛三天',
            status: 'confirmed'
          }
        });
      }),
      http.post('*/api/tasks/task_ready/review/confirm', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_ready',
            status: 'confirmed'
          }
        })
      )
    );

    await expect(getReviewResult('task_ready')).resolves.toMatchObject({ task_id: 'task_ready' });
    await expect(
      saveReviewField('task_ready', 'chief_complaint', {
        final_value: '头痛三天',
        status: 'confirmed'
      })
    ).resolves.toMatchObject({ status: 'confirmed' });
    await expect(confirmReview('task_ready')).resolves.toMatchObject({ status: 'confirmed' });
  });

  it('normalizes API errors without leaking technical details', () => {
    const message = normalizeApiError({
      code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
      message: 'Traceback: /secret/path',
      details: { raw_text: '完整病历原文' }
    });
    expect(message).toBe('处理模块未配置，请检查本地服务配置后重试。');
    expect(message).not.toContain('Traceback');
    expect(message).not.toContain('完整病历原文');
  });

  it('exports JSON and Excel through backend download endpoints', async () => {
    server.use(
      http.get('*/api/tasks/task_confirmed/export/json', () =>
        new HttpResponse(new Blob(['{}'], { type: 'application/json' }), {
          headers: { 'content-type': 'application/json' }
        })
      ),
      http.get('*/api/tasks/task_confirmed/export/excel', () =>
        new HttpResponse(new Blob(['excel'], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }), {
          headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
        })
      )
    );

    await expect(exportTaskJson('task_confirmed')).resolves.toBeInstanceOf(Blob);
    await expect(exportTaskExcel('task_confirmed')).resolves.toBeInstanceOf(Blob);
  });
});
