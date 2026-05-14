import { http, HttpResponse } from 'msw';

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
