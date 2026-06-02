# 前端 TDD — Fixtures 参考

```ts
export const mockTaskUploading = {
  task_id: 'task_20260515_0001',
  status: 'uploading',
  page_count: 0,
  upload_url: 'http://192.168.1.100:8081/mobile/upload/task_20260515_0001?token=test-token',
  upload_token: 'test-token',
  images: [],
};

export const mockTaskProcessing = {
  task_id: 'task_20260515_0001',
  status: 'processing',
  page_count: 3,
  images: [
    { page_no: 1, preview_url: '/api/tasks/task_20260515_0001/images/1/preview' },
    { page_no: 2, preview_url: '/api/tasks/task_20260515_0001/images/2/preview' },
    { page_no: 3, preview_url: '/api/tasks/task_20260515_0001/images/3/preview' },
  ],
};

export const mockTaskReview = {
  task_id: 'task_20260515_0001',
  status: 'review',
  page_count: 3,
  error: null,
};

export const mockTaskDone = {
  task_id: 'task_20260515_0001',
  status: 'done',
  page_count: 3,
  export_summary: { last_exported_at: null, formats: [], files: [] },
};

export const mockTaskAlgorithmFailed = {
  task_id: 'task_20260515_0001',
  status: 'failed',
  page_count: 3,
  error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
  error_message: '算法模块未配置，无法生成结构化字段',
};

export const mockSchemaFields = [
  { field_key: 'chief_complaint', field_name: '主诉', group: '入院记录' },
  { field_key: 'smoking_history', field_name: '吸烟史', group: '个人史' },
  { field_key: 'pulmonary_function', field_name: '肺功能', group: '检查结果' },
];

export const mockReviewFields = [
  {
    field_key: 'chief_complaint',
    field_name: '主诉',
    original_value: '反复咳嗽咳痰10年，加重3天',
    final_value: '反复咳嗽咳痰10年，加重3天',
    evidence: '主诉：反复咳嗽咳痰10年，加重3天。',
    page_no: 1,
    status: 'unreviewed',
    extraction_status: 'extracted',
    verification_status: 'passed',
    quality_flags: [],
  },
  {
    field_key: 'smoking_history',
    field_name: '吸烟史',
    original_value: '',
    final_value: '',
    evidence: null,
    page_no: null,
    status: 'unreviewed',
    extraction_status: 'not_found',
    verification_status: 'not_checked',
    quality_flags: ['missing_evidence'],
  },
];
```
