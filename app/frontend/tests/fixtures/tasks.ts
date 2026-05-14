import { http, HttpResponse } from 'msw';

export const taskFixtures = [
  {
    task_id: 'task-ready',
    session_id: 'sess_ready',
    status: 'ready_for_review',
    created_at: '2026-05-13T09:30:00+08:00',
    page_count: 3,
    review_summary: { status: 'unreviewed', confirmed_count: 0, total_count: 8 },
    export_summary: { formats: [] },
    error_code: null,
    error_message: null
  },
  {
    task_id: 'task-processing',
    session_id: 'sess_processing',
    status: 'processing',
    created_at: '2026-05-13T09:20:00+08:00',
    page_count: 2,
    review_summary: { status: null },
    export_summary: { formats: [] },
    error_code: null,
    error_message: null
  },
  {
    task_id: 'task-failed',
    session_id: 'sess_failed',
    status: 'failed',
    created_at: '2026-05-13T09:10:00+08:00',
    page_count: 1,
    review_summary: { status: null },
    export_summary: { formats: [] },
    error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
    error_message: '图像处理模块未配置'
  },
  {
    task_id: 'task-exported',
    session_id: 'sess_exported',
    status: 'exported',
    created_at: '2026-05-13T09:00:00+08:00',
    page_count: 5,
    review_summary: { status: 'confirmed', confirmed_count: 8, total_count: 8 },
    export_summary: { formats: ['json'] },
    error_code: null,
    error_message: null
  }
];

export function mockTasks(tasks = taskFixtures) {
  return http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks } }));
}

export function mockTaskDetail(task = taskFixtures[0]) {
  return http.get(`*/api/tasks/${task.task_id}`, () =>
    HttpResponse.json({
      success: true,
      data: {
        ...task,
        pages: [{ page_id: 'page_001', page_no: 1, status: 'uploaded' }]
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
  return http.post(`*/api/tasks/${taskId}/retry`, () =>
    HttpResponse.json({
      success: true,
      data: resolve()
    })
  );
}
