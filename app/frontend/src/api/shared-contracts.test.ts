import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { exportTaskExcel, exportTaskJson, exportTasksBatchZip } from './export';
import { normalizeApiError } from './errors';
import { getReviewResult, saveReviewField } from './review';
import { buildTaskImageFormData, finishTaskUpload, updateTaskDocumentType, uploadTaskImage } from './mobileUpload';
import { cancelTaskProcessing, createTask, getTaskDetail, getTasks, processTask, reextractTaskFromOcr, type TaskStatus } from './tasks';
import { fieldStatusMeta, getTaskStatusLabel, taskStatusMeta } from '../styles/status';
import { server } from '../../tests/setupTests';

describe('shared frontend contracts', () => {
  const mvpStatuses: TaskStatus[] = ['uploading', 'processing', 'review', 'done', 'failed'];

  it('frontend task statuses match MVP states', () => {
    expect(mvpStatuses).toEqual(['uploading', 'processing', 'review', 'done', 'failed']);
  });

  it('legacy task statuses are not assignable through runtime status labels', () => {
    expect(() => getTaskStatusLabel('ready_for_review' as TaskStatus)).toThrow('未知任务状态');
    expect(() => getTaskStatusLabel('exported' as TaskStatus)).toThrow('未知任务状态');
  });

  it('maps MVP task and field states to Chinese labels', () => {
    expect(taskStatusMeta.uploading.label).toBe('上传中');
    expect(taskStatusMeta.processing.label).toBe('处理中');
    expect(taskStatusMeta.review.label).toBe('待审核');
    expect(taskStatusMeta.done.label).toBe('已完成');
    expect(taskStatusMeta.failed.label).toBe('失败');
    expect(fieldStatusMeta.unreviewed.label).toBe('未审核');
    expect(fieldStatusMeta.modified.label).toBe('已修改');
  });

  it('creates task, uploads task image and finishes task upload', async () => {
    let uploadEndpointWasCalled = false;
    const file = new File(['image'], 'page.jpg', { type: 'image/jpeg' });
    const formData = buildTaskImageFormData(file, { image_width: 1200, image_height: 1600 });

    expect(formData.get('image')).toBe(file);
    expect(formData.get('image_width')).toBe('1200');
    expect(formData.get('image_height')).toBe('1600');
    expect(formData.has('quad_points')).toBe(false);

    server.use(
      http.post('*/api/tasks', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'uploading',
            upload_token: 'token_001',
            mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001'
          }
        })
      ),
      http.post('*/api/mobile-upload/task_001/images', () => {
        uploadEndpointWasCalled = true;
        return HttpResponse.json({
          success: true,
          data: {
            page_id: 'page_001',
            task_id: 'task_001',
            page_no: 1,
            uploaded_at: '2026-05-19T10:00:00+08:00'
          }
        });
      }),
      http.post('*/api/mobile-upload/task_001/finish', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'processing',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 1
          }
        })
      )
    );

    await expect(createTask()).resolves.toMatchObject({ task_id: 'task_001', status: 'uploading' });
    await expect(uploadTaskImage('task_001', 'token_001', file)).resolves.toMatchObject({ page_no: 1 });
    expect(uploadEndpointWasCalled).toBe(true);
    await expect(finishTaskUpload('task_001', 'token_001')).resolves.toMatchObject({ status: 'processing' });
  });

  it('loads task detail and retries failed processing through process endpoint', async () => {
    server.use(
      http.get('*/api/tasks/task_failed', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            status: 'failed',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 2,
            error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
            error_message: '图像处理模块未配置'
          }
        })
      ),
      http.post('*/api/tasks/task_failed/process', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            status: 'processing',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 2
          }
        })
      )
    );

    await expect(getTaskDetail('task_failed')).resolves.toMatchObject({ status: 'failed' });
    await expect(processTask('task_failed')).resolves.toMatchObject({ status: 'processing' });
  });

  it('cancels processing through the cancel-processing endpoint', async () => {
    server.use(
      http.post('*/api/tasks/task_processing/cancel-processing', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_processing',
            status: 'failed',
            error_code: 'TASK_PROCESSING_CANCELLED',
            error_message: '用户取消处理'
          }
        })
      )
    );

    await expect(cancelTaskProcessing('task_processing')).resolves.toMatchObject({
      status: 'failed',
      error_code: 'TASK_PROCESSING_CANCELLED'
    });
  });

  it('hides empty uploading placeholder tasks from task lists', async () => {
    server.use(
      http.get('*/api/tasks', () =>
        HttpResponse.json({
          success: true,
          data: {
            tasks: [
              {
                task_id: 'task_empty',
                status: 'uploading',
                created_at: '2026-05-19T10:00:00+08:00',
                page_count: 0
              },
              {
                task_id: 'task_uploaded',
                status: 'uploading',
                created_at: '2026-05-19T10:01:00+08:00',
                page_count: 1
              }
            ]
          }
        })
      )
    );

    await expect(getTasks()).resolves.toEqual([
      expect.objectContaining({ task_id: 'task_uploaded', status: 'uploading', page_count: 1 })
    ]);
  });

  it('loads review result and saves a field', async () => {
    server.use(
      http.get('*/api/tasks/task_review/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_review',
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
            summary: { unreviewed: 1, confirmed: 0, modified: 0 }
          }
        })
      ),
      http.put('*/api/tasks/task_review/review', async ({ request }) => {
        await expect(request.json()).resolves.toMatchObject({
          fields: [{ field_key: 'chief_complaint', value: '头痛三天', status: 'confirmed' }]
        });
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_review',
            status: 'review',
            review_result: {
              fields: [{
                field_key: 'chief_complaint',
                label: '主诉',
                value: '头痛三天',
                status: 'confirmed'
              }]
            }
          }
        });
      })
    );

    await expect(getReviewResult('task_review')).resolves.toMatchObject({ task_id: 'task_review' });
    await expect(
      saveReviewField('task_review', 'chief_complaint', {
        final_value: '头痛三天',
        status: 'confirmed'
      })
    ).resolves.toMatchObject({ status: 'confirmed' });
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
      http.get('*/api/tasks/task_review/export/json', () =>
        new HttpResponse(new Blob(['{}'], { type: 'application/json' }), {
          headers: { 'content-type': 'application/json' }
        })
      ),
      http.get('*/api/tasks/task_review/export/excel', () =>
        new HttpResponse(new Blob(['excel'], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }), {
          headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }
        })
      )
    );

    await expect(exportTaskJson('task_review')).resolves.toBeInstanceOf(Blob);
    await expect(exportTaskExcel('task_review')).resolves.toBeInstanceOf(Blob);
  });

  it('exports multiple tasks through batch zip endpoint', async () => {
    server.use(
      http.post('*/api/tasks/export/batch-zip', async ({ request }) => {
        await expect(request.json()).resolves.toEqual({ task_ids: ['task_001', 'task_002'] });
        return new HttpResponse(new Blob(['zip'], { type: 'application/zip' }), {
          headers: { 'content-type': 'application/zip' }
        });
      })
    );

    await expect(exportTasksBatchZip(['task_001', 'task_002'])).resolves.toBeInstanceOf(Blob);
  });

  it('updates mobile task document type', async () => {
    server.use(
      http.patch('*/api/mobile-upload/task_001/document-type', async ({ request }) => {
        const body = await request.json() as { document_type: string };
        expect(body.document_type).toBe('copd_admission_record');
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            schema_version: 'copd.v1'
          }
        });
      })
    );

    await expect(updateTaskDocumentType('task_001', 'token_001', 'copd_admission_record')).resolves.toMatchObject({
      document_type: 'copd_admission_record',
      document_type_label: '入院记录'
    });
  });

  it('requests OCR-only reextraction and receives version metadata', async () => {
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            run_id: 'reextract_001',
            source: 'ocr_text_only',
            schema_version: 'copd.v1',
            prompt_version: 'copd.prompt.v1',
            candidate_count: 3
          }
        })
      )
    );

    await expect(reextractTaskFromOcr('task_001')).resolves.toMatchObject({
      source: 'ocr_text_only',
      schema_version: 'copd.v1',
      prompt_version: 'copd.prompt.v1'
    });
  });
});
