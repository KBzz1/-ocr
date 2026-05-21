import type { ReviewPayload } from '../../api/review';

export const demoReviewTaskId = 'task-demo-review';

export const demoReviewPayload: ReviewPayload = {
  task_id: demoReviewTaskId,
  status: 'review',
  review_result: {
    ocr_text: [
      '模拟 OCR 文本',
      '姓名：张三',
      '年龄：45岁',
      '科室：神经内科',
      '主诉：反复头痛三天，加重半天。',
      '既往史：高血压病史五年，规律服药。'
    ].join('\n'),
    pages: [
      {
        page_id: 'demo_page_1',
        page_no: 1,
        parsed_text: '模拟 OCR 文本\n姓名：张三\n年龄：45岁\n科室：神经内科\n主诉：反复头痛三天，加重半天。'
      }
    ],
    fields: [
      {
        field_key: 'patient_name',
        label: '姓名',
        value: '张三',
        candidate_value: '张三',
        status: 'unreviewed',
        evidence: [{ page_id: 'demo_page_1', page_no: 1, text: '姓名：张三' }]
      },
      {
        field_key: 'department',
        label: '科室',
        value: '神经内科',
        candidate_value: '神经内科',
        status: 'unreviewed',
        evidence: [{ page_id: 'demo_page_1', page_no: 1, text: '科室：神经内科' }]
      },
      {
        field_key: 'chief_complaint',
        label: '主诉',
        value: '反复头痛三天，加重半天。',
        candidate_value: '反复头痛三天，加重半天。',
        status: 'unreviewed',
        evidence: [{ page_id: 'demo_page_1', page_no: 1, text: '反复头痛三天' }]
      },
      {
        field_key: 'past_history',
        label: '既往史',
        value: '高血压病史五年，规律服药。',
        candidate_value: '高血压病史五年，规律服药。',
        status: 'unreviewed',
        evidence: [{ page_id: 'demo_page_1', page_no: 1, text: '高血压病史五年' }]
      }
    ]
  }
};
