import type { ReviewPayload } from '../../api/review';

export const demoReviewTaskId = 'task-demo-review';

// 演示样本(开发用):对齐固定字段 schema 的入院记录,
// 覆盖 found / not_found / attention_required 三种状态,以及 ## 初步诊断 在
// OCR 文本中先于 ## 主诉 出现的"页面顺序与 schema 顺序不一致"场景,
// 便于在本地复核 FieldList 渲染、证据高亮与黄色重点核验提示。

const fieldGroups = [
  {
    group_key: 'chief_complaint',
    group_label: '主诉',
    fields: [
      { field_key: 'chief_complaint', label: '主诉' },
      { field_key: 'chief_complaint_duration', label: '主诉病程' }
    ]
  },
  {
    group_key: 'present_illness',
    group_label: '现病史',
    fields: [
      { field_key: 'present_illness', label: '现病史' },
      { field_key: 'onset_date', label: '起病时间' }
    ]
  },
  {
    group_key: 'past_history',
    group_label: '既往史',
    fields: [
      { field_key: 'past_history', label: '既往史' },
      { field_key: 'allergy_history', label: '过敏史' }
    ]
  },
  {
    group_key: 'physical_exam',
    group_label: '查体',
    fields: [
      { field_key: 'temperature', label: '体温' },
      { field_key: 'pulse', label: '脉搏' },
      { field_key: 'respiration', label: '呼吸' },
      { field_key: 'blood_pressure', label: '血压' }
    ]
  },
  {
    group_key: 'auxiliary_exam',
    group_label: '辅助检查',
    fields: [
      { field_key: 'blood_routine', label: '血常规' },
      { field_key: 'blood_gas_pao2', label: '血气 PaO2' }
    ]
  },
  {
    group_key: 'diagnosis',
    group_label: '诊断',
    fields: [
      { field_key: 'diagnosis_initial', label: '初步诊断' },
      { field_key: 'diagnosis_final', label: '最终诊断' }
    ]
  },
  {
    group_key: 'treatment_plan',
    group_label: '治疗计划',
    fields: [
      { field_key: 'treatment_plan', label: '治疗计划' },
      { field_key: 'discharge_criteria', label: '出院标准' }
    ]
  }
];

export const demoReviewPayload: ReviewPayload = {
  task_id: demoReviewTaskId,
  status: 'review',
  review_result: {
    // OCR 文本中## 初步诊断 先于 ## 主诉 出现(模拟页面顺序与 schema 顺序不一致)。
    ocr_text: [
      '## 初步诊断',
      '慢性阻塞性肺疾病急性加重',
      '',
      '## 主诉',
      '反复咳嗽、咳痰15年，加重伴喘憋3天。',
      '',
      '## 现病史',
      '患者15年前无明显诱因出现反复咳嗽、咳痰，白色黏痰。',
      '',
      '## 既往史',
      '高血压病史5年，最高血压160/92mmHg。',
      '',
      '## 查体',
      '体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg',
      '',
      '## 辅助检查',
      '血气分析 PaO2 76mmHg。'
    ].join('\n'),
    pages: [
      {
        page_id: 'demo_page_1',
        page_no: 1,
        parsed_text:
          '## 初步诊断\n慢性阻塞性肺疾病急性加重\n\n## 主诉\n反复咳嗽、咳痰15年，加重伴喘憋3天。'
      },
      {
        page_id: 'demo_page_2',
        page_no: 2,
        parsed_text:
          '## 现病史\n患者15年前无明显诱因出现反复咳嗽、咳痰，白色黏痰。\n\n## 既往史\n高血压病史5年，最高血压160/92mmHg。'
      },
      {
        page_id: 'demo_page_3',
        page_no: 3,
        parsed_text:
          '## 查体\n体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg\n\n## 辅助检查\n血气分析 PaO2 76mmHg。'
      }
    ],
    field_groups: fieldGroups,
    fields: [
      {
        field_key: 'chief_complaint',
        label: '主诉',
        field_name: '主诉',
        value: '反复咳嗽、咳痰15年，加重伴喘憋3天。',
        candidate_value: '反复咳嗽、咳痰15年，加重伴喘憋3天。',
        status: 'unreviewed',
        attention_required: false,
        evidence: [
          {
            id: 'u001',
            page_id: 'demo_page_1',
            page_no: 1,
            text: '反复咳嗽、咳痰15年',
            start_offset: 19,
            end_offset: 30
          }
        ]
      },
      {
        field_key: 'chief_complaint_duration',
        label: '主诉病程',
        field_name: '主诉病程',
        value: '15年',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u002', page_id: 'demo_page_1', page_no: 1, text: '15年' }]
      },
      {
        field_key: 'present_illness',
        label: '现病史',
        field_name: '现病史',
        value: '患者15年前无明显诱因出现反复咳嗽、咳痰，白色黏痰。',
        status: 'unreviewed',
        attention_required: false,
        evidence: [
          {
            id: 'u003',
            page_id: 'demo_page_2',
            page_no: 2,
            text: '患者15年前无明显诱因出现反复咳嗽、咳痰',
            start_offset: 7,
            end_offset: 23
          }
        ]
      },
      {
        field_key: 'onset_date',
        label: '起病时间',
        field_name: '起病时间',
        value: '',
        status: 'unreviewed',
        extraction_status: 'not_found',
        attention_required: false
      },
      {
        field_key: 'past_history',
        label: '既往史',
        field_name: '既往史',
        value: '高血压病史5年，最高血压160/92mmHg。',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u004', page_id: 'demo_page_2', page_no: 2, text: '高血压病史5年' }]
      },
      {
        field_key: 'allergy_history',
        label: '过敏史',
        field_name: '过敏史',
        value: '',
        status: 'unreviewed',
        extraction_status: 'not_found',
        attention_required: false
      },
      {
        field_key: 'temperature',
        label: '体温',
        field_name: '体温',
        value: '36.7℃',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u005', page_id: 'demo_page_3', page_no: 3, text: '体温：36.7℃' }]
      },
      {
        field_key: 'pulse',
        label: '脉搏',
        field_name: '脉搏',
        value: '99次/分',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u006', page_id: 'demo_page_3', page_no: 3, text: '脉搏：99次/分' }]
      },
      {
        field_key: 'respiration',
        label: '呼吸',
        field_name: '呼吸',
        value: '21次/分',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u007', page_id: 'demo_page_3', page_no: 3, text: '呼吸：21次/分' }]
      },
      {
        field_key: 'blood_pressure',
        label: '血压',
        field_name: '血压',
        value: '142/87mmHg',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u008', page_id: 'demo_page_3', page_no: 3, text: '血压：142/87mmHg' }]
      },
      {
        field_key: 'blood_routine',
        label: '血常规',
        field_name: '血常规',
        value: '',
        status: 'unreviewed',
        extraction_status: 'not_found',
        attention_required: false
      },
      {
        field_key: 'blood_gas_pao2',
        label: '血气 PaO2',
        field_name: '血气 PaO2',
        value: '76mmHg',
        status: 'unreviewed',
        attention_required: true,
        attention_message: '结果不确定，请核对原文',
        evidence: [{ id: 'u009', page_id: 'demo_page_3', page_no: 3, text: '血气分析 PaO2 76mmHg' }]
      },
      {
        field_key: 'diagnosis_initial',
        label: '初步诊断',
        field_name: '初步诊断',
        value: '慢性阻塞性肺疾病急性加重',
        status: 'unreviewed',
        attention_required: false,
        evidence: [
          {
            id: 'u010',
            page_id: 'demo_page_1',
            page_no: 1,
            text: '慢性阻塞性肺疾病急性加重',
            start_offset: 7,
            end_offset: 19
          }
        ]
      },
      {
        field_key: 'diagnosis_final',
        label: '最终诊断',
        field_name: '最终诊断',
        value: '',
        status: 'unreviewed',
        extraction_status: 'not_found',
        attention_required: false
      },
      {
        field_key: 'treatment_plan',
        label: '治疗计划',
        field_name: '治疗计划',
        value: '噻托溴铵粉雾剂18ug经口吸入1/日；布地奈德福莫特罗吸入粉雾剂320ug经口吸入2/日。',
        status: 'unreviewed',
        attention_required: false,
        evidence: [{ id: 'u011', page_id: 'demo_page_3', page_no: 3, text: '治疗计划：噻托溴铵粉雾剂' }]
      },
      {
        field_key: 'discharge_criteria',
        label: '出院标准',
        field_name: '出院标准',
        value: '',
        status: 'unreviewed',
        extraction_status: 'not_found',
        attention_required: false
      }
    ]
  }
};
