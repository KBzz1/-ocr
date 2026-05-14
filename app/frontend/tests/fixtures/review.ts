import { http, HttpResponse } from 'msw';

export const reviewFixture = {
  task_id: 'task-ready',
  fields: [
    {
      field_key: 'chief_complaint',
      label: '主诉',
      candidate_value: '头痛三天',
      final_value: '',
      status: 'unreviewed',
      evidence: [
        {
          page_id: 'page-001',
          page_no: 1,
          text: '头痛三天'
        }
      ]
    }
  ],
  summary: {
    unreviewed: 1,
    suspicious: 0,
    empty: 0,
    confirmed: 0
  }
};

export function mockReviewResult(taskId = 'task-ready') {
  return http.get(`*/api/tasks/${taskId}/review`, () =>
    HttpResponse.json({ success: true, data: reviewFixture })
  );
}
