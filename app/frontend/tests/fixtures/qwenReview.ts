import type { FieldGroupDef, ReviewField, ReviewResult } from '../../src/api/review';

export const QWEN_V2_FIELD_GROUPS: FieldGroupDef[] = [
  {
    group_key: 'chief_complaint',
    group_label: '主诉',
    fields: [{ field_key: 'chief_complaint', label: '主诉', qwen_type: 'T', qwen_path: ['主诉'], review_control: 'text' }]
  },
  {
    group_key: 'history_of_present_illness',
    group_label: '现病史',
    fields: [
      { field_key: 'hpi_initial_onset', label: '初次发病情况', qwen_type: 'T', qwen_path: ['现病史', '初次发病情况'], review_control: 'text' },
      { field_key: 'hpi_subsequent_onset', label: '后续发病情况', qwen_type: 'T', qwen_path: ['现病史', '后续发病情况'], review_control: 'text' },
      { field_key: 'hpi_in_hospital_diagnosis', label: '院内诊断情况', qwen_type: 'T', qwen_path: ['现病史', '院内诊断情况'], review_control: 'text' },
      { field_key: 'hpi_medications', label: '治疗药物', qwen_type: 'T', qwen_path: ['现病史', '治疗药物'], review_control: 'text' },
      { field_key: 'hpi_recent_symptoms', label: '近期症状', qwen_type: 'T', qwen_path: ['现病史', '近期症状'], review_control: 'text' },
      { field_key: 'hpi_mental_sleep_appetite', label: '精神睡眠食欲', qwen_type: 'J', qwen_path: ['现病史', '精神睡眠食欲'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'hpi_stool', label: '大便情况', qwen_type: 'T', qwen_path: ['现病史', '大便情况'], review_control: 'text' },
      { field_key: 'hpi_urination', label: '小便情况', qwen_type: 'J', qwen_path: ['现病史', '小便情况'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'hpi_weight_change', label: '体重变化', qwen_type: 'T', qwen_path: ['现病史', '体重变化'], review_control: 'text' }
    ]
  },
  {
    group_key: 'past_history',
    group_label: '既往史',
    fields: [
      { field_key: 'pmh_heart_disease', label: '心脏病', qwen_type: 'T', qwen_path: ['既往史', '心脏病'], review_control: 'text' },
      { field_key: 'pmh_hypertension', label: '高血压', qwen_type: 'T', qwen_path: ['既往史', '高血压'], review_control: 'text' },
      { field_key: 'pmh_diabetes', label: '糖尿病', qwen_type: 'T', qwen_path: ['既往史', '糖尿病'], review_control: 'text' },
      { field_key: 'pmh_hepatitis_b', label: '乙肝', qwen_type: 'J', qwen_path: ['既往史', '乙肝'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_bloody_stool', label: '便血', qwen_type: 'T', qwen_path: ['既往史', '便血'], review_control: 'text' },
      { field_key: 'pmh_nephritis', label: '肾炎', qwen_type: 'J', qwen_path: ['既往史', '肾炎'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_blood_disease', label: '血液病', qwen_type: 'J', qwen_path: ['既往史', '血液病'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_coronary_heart_disease', label: '冠心病', qwen_type: 'T', qwen_path: ['既往史', '冠心病'], review_control: 'text' },
      { field_key: 'pmh_cerebral_infarction', label: '脑梗塞', qwen_type: 'T', qwen_path: ['既往史', '脑梗塞'], review_control: 'text' },
      { field_key: 'pmh_surgery_history', label: '手术史', qwen_type: 'J', qwen_path: ['既往史', '手术史'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_transfusion_history', label: '输血史', qwen_type: 'J', qwen_path: ['既往史', '输血史'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_blood_product_history', label: '血制品史', qwen_type: 'J', qwen_path: ['既往史', '血制品史'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pmh_allergy_history', label: '过敏史', qwen_type: 'J', qwen_path: ['既往史', '过敏史'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] }
    ]
  },
  {
    group_key: 'personal_history',
    group_label: '个人史',
    fields: [
      { field_key: 'personal_work', label: '工作', qwen_type: 'T', qwen_path: ['个人史', '工作'], review_control: 'text' },
      { field_key: 'personal_smoking_history', label: '吸烟史', qwen_type: 'T', qwen_path: ['个人史', '吸烟史'], review_control: 'text' },
      { field_key: 'personal_drinking_history', label: '饮酒史', qwen_type: 'T', qwen_path: ['个人史', '饮酒史'], review_control: 'text' }
    ]
  },
  {
    group_key: 'family_history',
    group_label: '家族史',
    fields: [{ field_key: 'family_history', label: '家族史', qwen_type: 'T', qwen_path: ['家族史'], review_control: 'text' }]
  },
  {
    group_key: 'physical_exam',
    group_label: '体格检查',
    fields: [
      { field_key: 'pe_vital_signs', label: '生命体征', qwen_type: 'T', qwen_path: ['体格检查', '生命体征'], review_control: 'text' },
      { field_key: 'pe_height_weight_bmi', label: '身高体重BMI', qwen_type: 'T', qwen_path: ['体格检查', '身高体重BMI'], review_control: 'text' },
      { field_key: 'pe_skin', label: '皮肤', qwen_type: 'J', qwen_path: ['体格检查', '皮肤'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_eyes', label: '眼部', qwen_type: 'J', qwen_path: ['体格检查', '眼部'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_ears', label: '耳部', qwen_type: 'J', qwen_path: ['体格检查', '耳部'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_nose', label: '鼻部', qwen_type: 'J', qwen_path: ['体格检查', '鼻部'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_oral_cavity', label: '口腔', qwen_type: 'J', qwen_path: ['体格检查', '口腔'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_neck', label: '颈部', qwen_type: 'J', qwen_path: ['体格检查', '颈部'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_chest', label: '胸部', qwen_type: 'T', qwen_path: ['体格检查', '胸部'], review_control: 'text' },
      { field_key: 'pe_respiration', label: '呼吸', qwen_type: 'T', qwen_path: ['体格检查', '呼吸'], review_control: 'text' },
      { field_key: 'pe_heart_rhythm', label: '心律', qwen_type: 'T', qwen_path: ['体格检查', '心律'], review_control: 'text' },
      { field_key: 'pe_abdomen', label: '腹部', qwen_type: 'J', qwen_path: ['体格检查', '腹部'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_limbs', label: '四肢', qwen_type: 'J', qwen_path: ['体格检查', '四肢'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'pe_neurological', label: '神经', qwen_type: 'J', qwen_path: ['体格检查', '神经'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] }
    ]
  },
  {
    group_key: 'auxiliary_exam',
    group_label: '辅助检查',
    fields: [
      { field_key: 'aux_chest_ct', label: '胸部CT', qwen_type: 'T', qwen_path: ['辅助检查', '胸部CT'], review_control: 'text' },
      { field_key: 'aux_echocardiography', label: '心脏超声', qwen_type: 'T', qwen_path: ['辅助检查', '心脏超声'], review_control: 'text' },
      { field_key: 'aux_blood_gas', label: '血气', qwen_type: 'T', qwen_path: ['辅助检查', '血气'], review_control: 'text' },
      { field_key: 'aux_crp', label: 'CRP', qwen_type: 'T', qwen_path: ['辅助检查', 'CRP'], review_control: 'text' },
      { field_key: 'aux_blood_routine', label: '血常规', qwen_type: 'T', qwen_path: ['辅助检查', '血常规'], review_control: 'text' },
      { field_key: 'aux_electrolytes', label: '电解质', qwen_type: 'J', qwen_path: ['辅助检查', '电解质'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'aux_renal_function', label: '肾功', qwen_type: 'J', qwen_path: ['辅助检查', '肾功'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] },
      { field_key: 'aux_d_dimer', label: 'D2聚体', qwen_type: 'J', qwen_path: ['辅助检查', 'D2聚体'], review_control: 'judgement', options: ['正常', '异常', '未提及', '不确定'] }
    ]
  },
  {
    group_key: 'diagnosis',
    group_label: '诊断',
    fields: [
      { field_key: 'diagnosis_initial', label: '初步诊断', qwen_type: 'T', qwen_path: ['初步诊断'], review_control: 'text' },
      { field_key: 'diagnosis_final', label: '最终诊断', qwen_type: 'T', qwen_path: ['最终诊断'], review_control: 'text' }
    ]
  }
];

const FIELD_VALUES: Record<string, string> = {
  chief_complaint: '反复咳嗽、咳痰20年，加重3天，加重10天。',
  hpi_initial_onset: '20年前受凉后出现咳嗽、咳痰，痰为白色泡沫样，易咳出，伴活动后气促。',
  hpi_subsequent_onset: '10余天前受凉后再次出现咳嗽、咳痰，痰量较前增多，为黄色脓痰。',
  hpi_in_hospital_diagnosis: '门诊以慢性阻塞性肺疾病急性加重期收入院。',
  hpi_medications: '曾自行口服头孢克肟、阿莫西林等药物，症状无明显缓解。',
  hpi_recent_symptoms: '伴发热，体温最高38.5℃，活动后气促，休息后可缓解，无胸痛、咯血。',
  hpi_mental_sleep_appetite: '异常',
  hpi_stool: '大便正常',
  hpi_urination: '正常',
  hpi_weight_change: '体重无明显变化',
  pmh_heart_disease: '否认心脏病史',
  pmh_hypertension: '高血压病5年，最高血压160/100mmHg，长期口服缬沙坦氢氯噻嗪控制。',
  pmh_diabetes: '否认糖尿病史',
  pmh_hepatitis_b: '',
  pmh_bloody_stool: '否认便血',
  pmh_nephritis: '',
  pmh_blood_disease: '',
  pmh_coronary_heart_disease: '否认冠心病史',
  pmh_cerebral_infarction: '否认脑梗塞病史',
  pmh_surgery_history: '正常',
  pmh_transfusion_history: '正常',
  pmh_blood_product_history: '',
  pmh_allergy_history: '正常',
  personal_work: '退休',
  personal_smoking_history: '吸烟30年，约20支/日，已戒烟1年。',
  personal_drinking_history: '否认饮酒史',
  family_history: '父母已故，否认家族性遗传病史。',
  pe_vital_signs: '体温38.5℃，脉搏96次/分，呼吸22次/分，血压160/100mmHg。',
  pe_height_weight_bmi: '未提及',
  pe_skin: '正常',
  pe_eyes: '正常',
  pe_ears: '',
  pe_nose: '',
  pe_oral_cavity: '正常',
  pe_neck: '正常',
  pe_chest: '胸廓对称，双肺呼吸音粗。',
  pe_respiration: '双肺可闻及散在湿啰音。',
  pe_heart_rhythm: '心律齐，各瓣膜区未闻及明显杂音。',
  pe_abdomen: '正常',
  pe_limbs: '正常',
  pe_neurological: '正常',
  aux_chest_ct: '胸部CT提示慢性支气管炎、肺气肿改变。',
  aux_echocardiography: '未提及',
  aux_blood_gas: 'pH 7.42，PaO2 76mmHg，PaCO2 36mmHg。',
  aux_crp: 'CRP 升高',
  aux_blood_routine: '白细胞计数升高，中性粒细胞比例升高。',
  aux_electrolytes: '',
  aux_renal_function: '正常',
  aux_d_dimer: '',
  diagnosis_initial: '慢性阻塞性肺疾病急性加重期',
  diagnosis_final: '慢性阻塞性肺疾病急性加重期'
};

function judgementStatus(value: string): ReviewField['qwen_status'] {
  if (value === '正常') return 'normal';
  if (value === '异常') return 'abnormal';
  if (value === '不确定') return 'uncertain';
  return 'not_mentioned';
}

export function buildQwenV2ReviewResult(ocrText: string): ReviewResult {
  const fields = QWEN_V2_FIELD_GROUPS.flatMap((group) =>
    group.fields.map((fieldDef) => {
      const value = FIELD_VALUES[fieldDef.field_key] ?? '';
      const firstValue = value && value !== '未提及' ? ocrText.indexOf(value.slice(0, Math.min(8, value.length))) : -1;
      const field: ReviewField = {
        field_key: fieldDef.field_key,
        field_name: fieldDef.label,
        label: fieldDef.label,
        value,
        auto_value: value,
        final_value: value,
        status: 'unreviewed',
        qwen_type: fieldDef.qwen_type,
        qwen_path: fieldDef.qwen_path,
        review_control: fieldDef.review_control,
        options: fieldDef.options,
        extraction_status: value ? 'extracted' : 'not_found',
        evidence: firstValue >= 0
          ? [{ page_id: 'page_1', page_no: 1, text: value, start_offset: firstValue, end_offset: firstValue + value.length }]
          : []
      };
      if (fieldDef.qwen_type === 'J') {
        field.qwen_status = judgementStatus(value);
      }
      return field;
    })
  );

  return {
    ocr_text: ocrText,
    fields,
    field_groups: QWEN_V2_FIELD_GROUPS,
    pages: [{ page_id: 'page_1', page_no: 1, parsed_text: ocrText, preview_url: '/api/tasks/task_001/pages/page_1/image' }]
  };
}
