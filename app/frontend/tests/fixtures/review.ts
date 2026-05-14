import { http, HttpResponse } from 'msw';

type ReviewFixtureTaskDetail = {
  task_id: string;
  session_id: string;
  status: 'ready_for_review' | 'failed';
  created_at: string;
  page_count: number;
  error_code: string | null;
  error_message: string | null;
  pages: Array<{
    page_id: string;
    page_no?: number;
    status?: string;
    image_url?: string;
    parsed_text?: string;
  }>;
};

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

export const readyReviewTaskDetail: ReviewFixtureTaskDetail = {
  task_id: 'task-ready',
  session_id: 'sess_ready',
  status: 'ready_for_review',
  created_at: '2026-05-13T09:30:00+08:00',
  page_count: 2,
  error_code: null,
  error_message: null,
  pages: [
    {
      page_id: 'page-001',
      page_no: 1,
      status: 'processed',
      image_url: '/api/tasks/task-ready/pages/page-001/image',
      parsed_text: '第1页解析文本：主诉 头痛三天'
    },
    {
      page_id: 'page-002',
      page_no: 2,
      status: 'processed',
      image_url: '/api/tasks/task-ready/pages/page-002/image',
      parsed_text: '第2页解析文本：既往史 无特殊'
    }
  ]
};

export const failedReviewTaskDetail: ReviewFixtureTaskDetail = {
  task_id: 'task-failed',
  session_id: 'sess_failed',
  status: 'failed',
  created_at: '2026-05-13T09:10:00+08:00',
  page_count: 1,
  error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
  error_message: '图像处理模块未配置',
  pages: []
};

export const completeReviewFixture = {
  task_id: 'task-ready',
  fields: [
    {
      field_key: 'chief_complaint',
      label: '主诉',
      candidate_value: '头痛三天',
      final_value: '头痛三天',
      status: 'confirmed',
      evidence: [
        {
          page_id: 'page-001',
          page_no: 1,
          text: '头痛三天'
        }
      ]
    },
    {
      field_key: 'past_history',
      label: '既往史',
      candidate_value: '无特殊',
      final_value: '无特殊',
      status: 'modified',
      evidence: []
    }
  ],
  summary: {
    unreviewed: 0,
    suspicious: 0,
    empty: 0,
    confirmed: 2
  }
};

export function mockReviewResult(taskId = 'task-ready') {
  return http.get(`*/api/tasks/${taskId}/review`, () =>
    HttpResponse.json({ success: true, data: reviewFixture })
  );
}

export function mockReviewResultData(data = reviewFixture, taskId = data.task_id) {
  return http.get(`*/api/tasks/${taskId}/review`, () =>
    HttpResponse.json({ success: true, data })
  );
}

export function mockReviewTaskDetail(data: ReviewFixtureTaskDetail = readyReviewTaskDetail) {
  return http.get(`*/api/tasks/${data.task_id}`, () =>
    HttpResponse.json({ success: true, data })
  );
}
