# 前端 TDD — Fixtures 参考

```ts
export const mockSession = {
  session_id: 'sess_001',
  status: 'active',
  page_count: 0,
  upload_locked: false,
  expires_at: '2026-05-11T18:00:00+08:00',
};

export const mockTaskAlgorithmFailed = {
  task_id: 'task_20260511_0001',
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
    original_value: '',
    final_value: '',
    evidence: null,
    page_no: null,
    status: 'empty',
  },
];
```
