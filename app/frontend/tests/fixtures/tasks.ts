import { http, HttpResponse } from 'msw';

import type { TaskSummary } from '../../src/api/tasks';

export const taskFixtures: TaskSummary[] = [
  {
    task_id: 'task-uploading',
    status: 'uploading',
    created_at: '2026-05-19T09:40:00+08:00',
    page_count: 0,
    review_summary: { status: null, confirmed_count: 0, total_count: 0 },
    export_summary: { formats: [] },
    error_code: null,
    error_message: null
  },
  {
    task_id: 'task-ready',
    status: 'review',
    created_at: '2026-05-19T09:30:00+08:00',
    page_count: 3,
    review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 8 },
    export_summary: { formats: [] },
    error_code: null,
    error_message: null
  },
  {
    task_id: 'task-processing',
    status: 'processing',
    created_at: '2026-05-19T09:20:00+08:00',
    page_count: 2,
    processing_summary: {
      stage: 'document_parsing',
      status: 'running',
      label: 'OCR 文档解析',
      progress_percent: 55,
      page_count: 2,
      started_at: '2026-05-19T09:20:00+08:00',
      updated_at: '2026-05-19T09:21:00+08:00',
      elapsed_seconds: 60
    },
    review_summary: { status: null },
    export_summary: { formats: [] },
    error_code: null,
    error_message: null
  },
  {
    task_id: 'task-failed',
    status: 'failed',
    created_at: '2026-05-19T09:10:00+08:00',
    page_count: 1,
    review_summary: { status: null },
    export_summary: { formats: [] },
    error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
    error_message: '图像处理模块未配置'
  },
  {
    task_id: 'task-done',
    status: 'done',
    created_at: '2026-05-19T09:00:00+08:00',
    page_count: 5,
    review_summary: { status: 'confirmed', confirmed_count: 8, total_count: 8 },
    export_summary: { formats: ['json'] },
    error_code: null,
    error_message: null
  }
];

export function mockTasks(tasks: TaskSummary[] = taskFixtures) {
  return http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks } }));
}

export function mockCreateTask(
  result = {
    task_id: 'task_001',
    status: 'uploading' as const,
    upload_token: 'token_001',
    mobile_upload_url: 'http://127.0.0.1:8081/mobile/upload/task_001?token=token_001'
  }
) {
  return http.post('*/api/tasks', () => HttpResponse.json({ success: true, data: result }));
}

export function mockCreateTaskError() {
  return http.post('*/api/tasks', () =>
    HttpResponse.json(
      { error: { code: 'TASK_CREATE_FAILED', message: '创建任务失败', details: {} } },
      { status: 500 }
    )
  );
}

export function mockTaskDetail(task = taskFixtures[0]) {
  return http.get(`*/api/tasks/${task.task_id}`, () =>
    HttpResponse.json({
      success: true,
      data: {
        ...task,
        pages: [{ page_id: 'page_001', page_no: 1 }]
      }
    })
  );
}

export function mockRetryTaskProcessing(
  taskId = 'task-failed',
  resolve: () => { task_id: string; status: string } = () => ({
    task_id: taskId,
    status: 'processing'
  })
) {
  return http.post(`*/api/tasks/${taskId}/process`, () =>
    HttpResponse.json({
      success: true,
      data: resolve()
    })
  );
}
