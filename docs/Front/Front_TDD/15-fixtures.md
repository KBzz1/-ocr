# 前端 TDD — Fixtures 参考

```ts
export const mockSession = {
  session_id: 'sess_001',
  status: 'active',
  task_id: 'task_20260515_0001',
  page_count: 0,
  expires_at: '2026-05-15T18:30:00+08:00',
  created_at: '2026-05-15T18:00:00+08:00',
};

export const mockSessionLocked = {
  session_id: 'sess_001',
  status: 'locked',
  task_id: 'task_20260515_0001',
  page_count: 3,
  locked_at: '2026-05-15T18:05:00+08:00',
};

export const mockSessionCancelled = {
  session_id: 'sess_001',
  status: 'cancelled',
  task_id: 'task_20260515_0001',
  page_count: 2,
  cancelled_at: '2026-05-15T18:03:00+08:00',
};

export const mockTaskCapturing = {
  task_id: 'task_20260515_0001',
  status: 'capturing',
  review_status: 'unconfirmed',
  export_status: 'not_exported',
  page_count: 0,
  thumbnail_url: null,
};

export const mockTaskUploaded = {
  task_id: 'task_20260515_0001',
  status: 'uploaded',
  review_status: 'unconfirmed',
  export_status: 'not_exported',
  page_count: 3,
  thumbnail_url: '/data/tasks/task_20260515_0001/uploads/page_001_thumb.jpg',
};

export const mockTaskReadyForReview = {
  task_id: 'task_20260515_0001',
  status: 'ready_for_review',
  review_status: 'unconfirmed',
  export_status: 'not_exported',
  page_count: 3,
  thumbnail_url: '/data/tasks/task_20260515_0001/uploads/page_001_thumb.jpg',
};

export const mockTaskAlgorithmFailed = {
  task_id: 'task_20260515_0001',
  status: 'failed',
  review_status: 'unconfirmed',
  export_status: 'not_exported',
  page_count: 3,
  error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
  error_message: '算法模块未配置，无法生成结构化字段',
};

export const mockSchemaFields = [
  { field_key: 'name', field_name: '姓名', group: '患者基本信息' },
  { field_key: 'chief_complaint', field_name: '主诉', group: '入院/病程信息' },
  { field_key: 'temperature', field_name: '体温', group: '体格检查' },
  { field_key: 'primary_diagnosis', field_name: '初步诊断', group: '诊断相关' },
];

export const mockReviewFields = [
  {
    field_key: 'chief_complaint',
    field_name: '主诉',
    original_value: '头痛3天',
    final_value: '头痛3天',
    evidence: '主诉：头痛3天。',
    page_no: 1,
    status: 'unreviewed',
  },
  {
    field_key: 'name',
    field_name: '姓名',
    original_value: '张三',
    final_value: '张三',
    evidence: '姓名：张三',
    page_no: 1,
    status: 'confirmed',
  },
  {
    field_key: 'marital_history',
    field_name: '婚育史',
    original_value: '',
    final_value: '',
    evidence: null,
    page_no: null,
    status: 'empty',
  },
];
```
