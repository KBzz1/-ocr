import { http, HttpResponse } from 'msw';

export const reviewExportTask = {
  task_id: 'task-review',
  status: 'review' as const,
  export_summary: {
    formats: [] as string[],
    last_exported_at: null as string | null
  }
};

export const doneExportTask = {
  ...reviewExportTask,
  status: 'done' as const
};

export const processingExportTask = {
  ...reviewExportTask,
  status: 'processing' as const
};

export function mockJsonExport(taskId = 'task-review') {
  return http.get(`*/api/tasks/${taskId}/export/json`, () =>
    new HttpResponse(new Blob(['{}'], { type: 'application/json' }), {
      headers: { 'content-type': 'application/json' }
    })
  );
}

export function mockExcelExport(taskId = 'task-review') {
  return http.get(`*/api/tasks/${taskId}/export/excel`, () =>
    new HttpResponse(
      new Blob(['excel'], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }),
      {
        headers: {
          'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
      }
    )
  );
}

export function mockExportIntegrityError(taskId = 'task-review', format: 'json' | 'excel' = 'json') {
  return http.get(`*/api/tasks/${taskId}/export/${format}`, () =>
    HttpResponse.json(
      {
        error: {
          code: 'REVIEW_VALIDATION_FAILED',
          message: '存在未审核字段，Traceback: /secret/model.log',
          details: {
            unreviewed: 2,
            raw_text: '完整病历原文不应展示'
          }
        }
      },
      { status: 409 }
    )
  );
}
