import { http, HttpResponse } from 'msw';

export const confirmedExportTask = {
  task_id: 'task-confirmed',
  status: 'confirmed' as const,
  review_summary: {
    unreviewed: 0,
    suspicious: 0,
    empty: 0,
    missing_source: 0
  },
  export_summary: {
    formats: [] as string[],
    last_exported_at: null as string | null,
    last_format: null as string | null
  }
};

export const unconfirmedExportTask = {
  ...confirmedExportTask,
  task_id: 'task-ready',
  status: 'ready_for_review' as const,
  review_summary: {
    unreviewed: 2,
    suspicious: 1,
    empty: 1,
    missing_source: 3
  }
};

export const exportedJsonTask = {
  ...confirmedExportTask,
  status: 'exported' as const,
  export_summary: {
    formats: ['json'],
    last_exported_at: '2026-05-14T10:30:00+08:00',
    last_format: 'json'
  }
};

export function mockJsonExport(taskId = 'task-confirmed') {
  return http.get(`*/api/tasks/${taskId}/export/json`, () =>
    new HttpResponse(new Blob(['{}'], { type: 'application/json' }), {
      headers: { 'content-type': 'application/json' }
    })
  );
}

export function mockExcelExport(taskId = 'task-confirmed') {
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

export function mockExportIntegrityError(taskId = 'task-confirmed', format: 'json' | 'excel' = 'json') {
  return http.get(`*/api/tasks/${taskId}/export/${format}`, () =>
    HttpResponse.json(
      {
        error: {
          code: 'REVIEW_VALIDATION_FAILED',
          message: '存在未审核字段，Traceback: /secret/model.log',
          details: {
            unreviewed: 2,
            suspicious: 1,
            raw_text: '完整病历原文不应展示',
            image_base64: 'data:image/png;base64,AAAA'
          }
        }
      },
      { status: 409 }
    )
  );
}
