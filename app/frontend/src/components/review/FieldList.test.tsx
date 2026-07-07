import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FieldList } from './FieldList';
import type { ReviewField, FieldGroupDef } from '../../api/review';

function makeField(overrides: Partial<ReviewField> = {}): ReviewField {
  return {
    field_key: 'patient_name',
    label: '姓名',
    field_name: '姓名',
    value: '张三',
    status: 'unreviewed',
    ...overrides
  };
}

const baseGroups: FieldGroupDef[] = [
  {
    group_key: 'basic',
    group_label: '基本信息',
    fields: [
      { field_key: 'patient_name', label: '姓名' },
      { field_key: 'gender', label: '性别' }
    ]
  }
];

describe('FieldList', () => {
  it('renders all schema fields including empty ones when readOnly is true', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    render(
      <FieldList
        fields={[makeField()]}
        fieldGroups={baseGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
        readOnly
      />
    );

    const basicGroup = screen.getByLabelText('基本信息');
    expect(within(basicGroup).getByText('姓名')).toBeTruthy();
    expect(within(basicGroup).getByText('性别')).toBeTruthy();
    expect(within(basicGroup).getByText('2 个字段')).toBeTruthy();
  });

  it('disables textarea and review check button when readOnly is true', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    render(
      <FieldList
        fields={[makeField()]}
        fieldGroups={baseGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
        readOnly
      />
    );

    const textarea = screen.getByLabelText('姓名 字段') as HTMLTextAreaElement;
    expect(textarea.readOnly).toBe(true);

    const reviewButton = screen.getByRole('button', { name: '审核 姓名' }) as HTMLButtonElement;
    expect(reviewButton.disabled).toBe(true);
  });

  it('does not emit onChange or onToggleReviewed when readOnly is true', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    render(
      <FieldList
        fields={[makeField()]}
        fieldGroups={baseGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
        readOnly
      />
    );

    const textarea = screen.getByLabelText('姓名 字段') as HTMLTextAreaElement;
    await user.type(textarea, '李四');
    expect(onChange).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '审核 姓名' }));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('still allows onFocusField when readOnly is true', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    render(
      <FieldList
        fields={[makeField()]}
        fieldGroups={baseGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
        readOnly
      />
    );

    const card = screen.getByTestId('review-field-card-patient_name');
    await user.click(card);
    expect(onFocus).toHaveBeenCalledWith(expect.objectContaining({ field_key: 'patient_name' }));
  });

  it('renders_single_field_section_without_duplicate_label', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const singleFieldGroups: FieldGroupDef[] = [
      { group_key: 'chief_complaint', group_label: '主诉', fields: [{ field_key: 'chief_complaint', label: '主诉' }] }
    ];
    render(
      <FieldList
        fields={[makeField({
          field_key: 'chief_complaint',
          field_name: '主诉',
          label: '主诉',
          value: '头痛三天',
          auto_value: '头痛三天',
          final_value: '头痛三天'
        })]}
        fieldGroups={singleFieldGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    // Section title visible
    expect(screen.getByLabelText('主诉')).toBeTruthy();
    const textarea = screen.getByLabelText('主诉 字段') as HTMLTextAreaElement;
    expect(textarea.value).toBe('头痛三天');
    // The topline label element should NOT exist as a duplicate text node
    // (group title in <h3> is the only visible 主诉 label; the topline <label> is hidden)
    const section = screen.getByLabelText('主诉');
    const labelElements = section.querySelectorAll('.field-card__label');
    expect(labelElements.length).toBe(0);
    const reviewCheck = screen.getByRole('button', { name: '审核 主诉' });
    expect(reviewCheck.closest('.field-card__text-editor')).toBeTruthy();
  });

  it('renders_not_found_as_unmentioned_without_yellow_flag', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const groups: FieldGroupDef[] = [
      { group_key: 'past_history', group_label: '既往史', fields: [{ field_key: 'past_history', label: '既往史' }] }
    ];
    render(
      <FieldList
        fields={[makeField({
          field_key: 'past_history',
          field_name: '既往史',
          label: '既往史',
          value: '',
          extraction_status: 'not_found',
          attention_required: false
        })]}
        fieldGroups={groups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    // 未提及 copy visible (either as visible text or as placeholder)
    const section = screen.getByLabelText('既往史');
    const text = section.textContent ?? '';
    expect(text).toContain('未提及');
    // No yellow exclamation risk flag rendered for this card
    expect(section.querySelector('.field-card__flag')).toBeNull();
    expect(section.querySelector('[aria-label^="重点核验"]')).toBeNull();
    expect(screen.queryByLabelText(/重点核验/)).toBeNull();
    const reviewCheck = screen.getByRole('button', { name: '审核 既往史' });
    expect(reviewCheck.closest('.field-card__text-editor')).toBeTruthy();
    expect(reviewCheck.closest('.field-card__text-editor--placeholder')).toBeTruthy();
  });

  it('renders_attention_as_yellow_exclamation_only', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const groups: FieldGroupDef[] = [
      { group_key: 'temperature', group_label: '体温', fields: [{ field_key: 'temperature', label: '体温' }] }
    ];
    render(
      <FieldList
        fields={[makeField({
          field_key: 'temperature',
          field_name: '体温',
          label: '体温',
          value: '37.0℃',
          attention_required: true,
          attention_message: '结果不确定，请核对原文'
        })]}
        fieldGroups={groups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    const flag = screen.getByLabelText('重点核验：结果不确定，请核对原文');
    expect(flag).toBeTruthy();
    expect(flag.textContent).toBe('!');
    // flag should be inside the field card, not just floating
    expect(flag.closest('.field-card__item')).toBeTruthy();
  });

  it('renders_qwen_j_field_as_status_segmented_control', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const groups: FieldGroupDef[] = [
      {
        group_key: 'history_of_present_illness',
        group_label: '现病史',
        fields: [
          {
            field_key: 'hpi_mental_sleep_appetite',
            label: '精神睡眠食欲',
            qwen_type: 'J',
            qwen_path: ['现病史', '精神睡眠食欲']
          }
        ]
      }
    ];

    render(
      <FieldList
        fields={[makeField({
          field_key: 'hpi_mental_sleep_appetite',
          field_name: '精神睡眠食欲',
          label: '精神睡眠食欲',
          value: '异常',
          final_value: '异常',
          qwen_type: 'J',
          qwen_status: 'abnormal',
          qwen_path: ['现病史', '精神睡眠食欲']
        })]}
        fieldGroups={groups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    expect(screen.queryByRole('group', { name: '精神睡眠食欲 状态' })).toBeNull();
    const abnormalInput = screen.getByLabelText('精神睡眠食欲 字段') as HTMLTextAreaElement;
    expect(abnormalInput.value).toBe('异常');
    const reviewCheck = screen.getByRole('button', { name: '审核 精神睡眠食欲' });
    expect(reviewCheck.closest('.field-card__abnormal-editor')).toBeTruthy();

    fireEvent.change(abnormalInput, { target: { value: '精神食欲欠佳' } });

    expect(onChange).toHaveBeenCalledTimes(1);
    const updater = onChange.mock.calls[0][0] as (prev: ReviewField[]) => ReviewField[];
    const result = updater([
      makeField({
        field_key: 'hpi_mental_sleep_appetite',
        field_name: '精神睡眠食欲',
        label: '精神睡眠食欲',
        value: '异常',
        final_value: '异常',
        qwen_type: 'J',
        qwen_status: 'abnormal',
        qwen_path: ['现病史', '精神睡眠食欲']
      })
    ]);
    expect(result[0]).toEqual(expect.objectContaining({
      field_key: 'hpi_mental_sleep_appetite',
      final_value: '精神食欲欠佳',
      value: '精神食欲欠佳',
      qwen_status: 'abnormal',
      status: 'modified'
    }));
  });

  it('renders_qwen_j_field_from_field_group_definition_when_field_lacks_metadata', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'hpi_mental_sleep_appetite',
          field_name: '精神睡眠食欲',
          label: '精神睡眠食欲',
          value: '异常',
          final_value: '异常',
          qwen_status: 'abnormal'
        })]}
        fieldGroups={[
          {
            group_key: 'history_of_present_illness',
            group_label: '现病史',
            fields: [
              {
                field_key: 'hpi_mental_sleep_appetite',
                label: '精神睡眠食欲',
                qwen_type: 'J',
                qwen_path: ['现病史', '精神睡眠食欲'],
                review_control: 'judgement',
                options: ['正常', '异常', '未提及', '不确定']
              }
            ]
          }
        ]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    expect(screen.queryByRole('group', { name: '精神睡眠食欲 状态' })).toBeNull();
    expect((screen.getByLabelText('精神睡眠食欲 字段') as HTMLTextAreaElement).value).toBe('异常');
    expect(screen.queryByRole('button', { name: '不确定 精神睡眠食欲' })).toBeNull();
  });

  it('renders_not_found_qwen_j_field_as_unmentioned_segmented_control', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pmh_blood_disease',
          field_name: '血液病',
          label: '血液病',
          value: '',
          final_value: '',
          extraction_status: 'not_found',
          qwen_status: 'not_mentioned'
        })]}
        fieldGroups={[
          {
            group_key: 'past_history',
            group_label: '既往史',
            fields: [
              {
                field_key: 'pmh_blood_disease',
                label: '血液病',
                qwen_type: 'J',
                qwen_path: ['既往史', '血液病'],
                review_control: 'judgement',
                options: ['正常', '异常', '未提及', '不确定']
              }
            ]
          }
        ]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    const group = screen.getByRole('group', { name: '血液病 状态' });
    expect(group.classList.contains('is-not-mentioned')).toBe(true);
    expect(screen.getByRole('button', { name: '正常 血液病' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '异常 血液病' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '未提及 血液病' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.queryByLabelText('血液病 未提及')).toBeNull();
    expect(screen.queryByLabelText('血液病 字段')).toBeNull();
  });

  it('switches_unmentioned_qwen_j_field_to_empty_editor_when_abnormal_is_clicked', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pmh_blood_disease',
          field_name: '血液病',
          label: '血液病',
          value: '',
          final_value: '',
          extraction_status: 'not_found',
          qwen_type: 'J',
          qwen_status: 'not_mentioned'
        })]}
        fieldGroups={[{
          group_key: 'past_history',
          group_label: '既往史',
          fields: [{ field_key: 'pmh_blood_disease', label: '血液病', qwen_type: 'J', review_control: 'judgement' }]
        }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    await user.click(screen.getByRole('button', { name: '异常 血液病' }));

    expect(onChange).toHaveBeenCalledTimes(1);
    const updater2 = onChange.mock.calls[0][0] as (prev: ReviewField[]) => ReviewField[];
    const result2 = updater2([
      makeField({
        field_key: 'pmh_blood_disease',
        field_name: '血液病',
        label: '血液病',
        value: '',
        final_value: '',
        extraction_status: 'not_found',
        qwen_type: 'J',
        qwen_status: 'not_mentioned'
      })
    ]);
    expect(result2[0]).toEqual(expect.objectContaining({
      field_key: 'pmh_blood_disease',
      final_value: '',
      value: '',
      qwen_status: 'abnormal',
      extraction_status: 'extracted',
      status: 'modified'
    }));
  });

  it('changes_empty_abnormal_qwen_j_editor_to_unmentioned_on_blur', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pmh_blood_disease',
          field_name: '血液病',
          label: '血液病',
          value: '',
          final_value: '',
          extraction_status: 'extracted',
          qwen_type: 'J',
          qwen_status: 'abnormal'
        })]}
        fieldGroups={[{
          group_key: 'past_history',
          group_label: '既往史',
          fields: [{ field_key: 'pmh_blood_disease', label: '血液病', qwen_type: 'J', review_control: 'judgement' }]
        }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    fireEvent.blur(screen.getByLabelText('血液病 字段'));

    expect(onChange).toHaveBeenCalledTimes(1);
    const updater3 = onChange.mock.calls[0][0] as (prev: ReviewField[]) => ReviewField[];
    const result3 = updater3([
      makeField({
        field_key: 'pmh_blood_disease',
        field_name: '血液病',
        label: '血液病',
        value: '',
        final_value: '',
        extraction_status: 'extracted',
        qwen_type: 'J',
        qwen_status: 'abnormal'
      })
    ]);
    expect(result3[0]).toEqual(expect.objectContaining({
      field_key: 'pmh_blood_disease',
      final_value: '',
      value: '',
      qwen_status: 'not_mentioned',
      extraction_status: 'not_found',
      status: 'modified'
    }));
  });

  it('keeps_abnormal_qwen_j_editor_value_on_non_empty_blur', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pmh_blood_disease',
          field_name: '血液病',
          label: '血液病',
          value: '贫血',
          final_value: '贫血',
          extraction_status: 'extracted',
          qwen_type: 'J',
          qwen_status: 'abnormal'
        })]}
        fieldGroups={[{
          group_key: 'past_history',
          group_label: '既往史',
          fields: [{ field_key: 'pmh_blood_disease', label: '血液病', qwen_type: 'J', review_control: 'judgement' }]
        }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    fireEvent.blur(screen.getByLabelText('血液病 字段'));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders_uncertain_qwen_j_field_as_unselected_with_warning', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pe_ears',
          field_name: '耳部',
          label: '耳部',
          value: '不确定',
          final_value: '不确定',
          qwen_type: 'J',
          qwen_status: 'uncertain'
        })]}
        fieldGroups={[{ group_key: 'physical_exam', group_label: '体格检查', fields: [{ field_key: 'pe_ears', label: '耳部', qwen_type: 'J' }] }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    expect(screen.queryByRole('button', { name: '不确定 耳部' })).toBeNull();
    expect(screen.getByLabelText('耳部 不确定，请核对原文')).toBeTruthy();
    expect(screen.getByRole('button', { name: '正常 耳部' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: '异常 耳部' }).getAttribute('aria-pressed')).toBe('false');
    expect(screen.getByRole('button', { name: '未提及 耳部' }).getAttribute('aria-pressed')).toBe('false');
  });

  it('renders_numbered_diagnoses_as_separate_editable_items', async () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'diagnosis_final',
          field_name: '最终诊断',
          label: '最终诊断',
          value: '1慢性阻塞性肺疾病急性加重 2Ⅱ型呼吸衰竭 3高血压2级中危',
          final_value: '1慢性阻塞性肺疾病急性加重 2Ⅱ型呼吸衰竭 3高血压2级中危'
        })]}
        fieldGroups={[{ group_key: 'diagnosis', group_label: '诊断', fields: [{ field_key: 'diagnosis_final', label: '最终诊断' }] }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    expect(screen.getByLabelText('最终诊断 诊断列表')).toBeTruthy();
    expect(screen.getByTestId('review-field-card-diagnosis_final').classList.contains('field-card__item--diagnosis')).toBe(true);
    expect(screen.getByLabelText('最终诊断 第 1 项')).toHaveProperty('value', '慢性阻塞性肺疾病急性加重');
    expect(screen.getByLabelText('最终诊断 第 2 项')).toHaveProperty('value', 'Ⅱ型呼吸衰竭');
    expect(screen.getByLabelText('最终诊断 第 3 项')).toHaveProperty('value', '高血压2级中危');

    fireEvent.change(screen.getByLabelText('最终诊断 第 2 项'), { target: { value: '慢性呼吸衰竭' } });
    expect(onChange).toHaveBeenCalled();
    const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    const updater4 = lastCall as (prev: ReviewField[]) => ReviewField[];
    const result4 = updater4([
      makeField({
        field_key: 'diagnosis_final',
        field_name: '最终诊断',
        label: '最终诊断',
        value: '1慢性阻塞性肺疾病急性加重 2Ⅱ型呼吸衰竭 3高血压2级中危',
        final_value: '1慢性阻塞性肺疾病急性加重 2Ⅱ型呼吸衰竭 3高血压2级中危'
      })
    ]);
    expect(result4[0]).toEqual(expect.objectContaining({
      field_key: 'diagnosis_final',
      final_value: '1慢性阻塞性肺疾病急性加重\n2慢性呼吸衰竭\n3高血压2级中危',
      status: 'modified'
    }));
  });

  it('renders_escaped_newline_numbered_diagnoses_as_separate_editable_items', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'diagnosis_initial',
          field_name: '初步诊断',
          label: '初步诊断',
          value: '1.慢性阻塞性肺病伴有急性加重\\n2.冠状动脉粥样硬化性心脏病待诊\\n3.高血压2级很高危',
          final_value: '1.慢性阻塞性肺病伴有急性加重\\n2.冠状动脉粥样硬化性心脏病待诊\\n3.高血压2级很高危'
        })]}
        fieldGroups={[{ group_key: 'diagnosis', group_label: '诊断', fields: [{ field_key: 'diagnosis_initial', label: '初步诊断' }] }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    expect(screen.getByLabelText('初步诊断 诊断列表')).toBeTruthy();
    expect(screen.getByTestId('review-field-card-diagnosis_initial').classList.contains('field-card__item--diagnosis')).toBe(true);
    expect(screen.getByLabelText('初步诊断 第 1 项')).toHaveProperty('value', '慢性阻塞性肺病伴有急性加重');
    expect(screen.getByLabelText('初步诊断 第 2 项')).toHaveProperty('value', '冠状动脉粥样硬化性心脏病待诊');
    expect(screen.getByLabelText('初步诊断 第 3 项')).toHaveProperty('value', '高血压2级很高危');
    expect(screen.queryByLabelText('初步诊断 字段')).toBeNull();
  });

  it('disables_qwen_j_control_when_read_only', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();

    render(
      <FieldList
        fields={[makeField({
          field_key: 'pe_skin',
          field_name: '皮肤',
          label: '皮肤',
          value: '正常',
          final_value: '正常',
          qwen_type: 'J',
          qwen_status: 'normal'
        })]}
        fieldGroups={[{ group_key: 'physical_exam', group_label: '体格检查', fields: [{ field_key: 'pe_skin', label: '皮肤', qwen_type: 'J' }] }]}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
        readOnly
      />
    );

    const normal = screen.getByRole('button', { name: '正常 皮肤' }) as HTMLButtonElement;
    expect(normal.disabled).toBe(true);
    await user.click(normal);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('groups_parameter_fields_with_units_outside_value_inputs', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const fieldGroups: FieldGroupDef[] = [
      {
        group_key: 'physical_exam',
        group_label: '体格检查',
        fields: [
          { field_key: 'pe_temperature', label: '体温', parameter_group: '生命体征', parameter_columns: 8, unit: '℃' },
          { field_key: 'pe_pulse', label: '脉搏', parameter_group: '生命体征', parameter_columns: 8, unit: '次/分' },
          { field_key: 'pe_respiration_rate', label: '呼吸', parameter_group: '生命体征', parameter_columns: 8, unit: '次/分' },
          { field_key: 'pe_blood_pressure', label: '血压', parameter_group: '生命体征', parameter_columns: 8, unit: 'mmHg' },
        ],
      },
    ];

    render(
      <FieldList
        fields={[
          makeField({ field_key: 'pe_temperature', value: '36.7', final_value: '36.7', parameter_columns: 4 }),
          makeField({ field_key: 'pe_pulse', value: '99', final_value: '99' }),
          makeField({ field_key: 'pe_respiration_rate', value: '21', final_value: '21' }),
          makeField({ field_key: 'pe_blood_pressure', value: '142/87', final_value: '142/87' }),
        ]}
        fieldGroups={fieldGroups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    const group = screen.getByTestId('review-parameter-group-生命体征');
    expect(group.getAttribute('data-columns')).toBe('8');
    expect(group.textContent).toContain('生命体征');
    expect(screen.getByLabelText('体温 字段')).toHaveProperty('value', '36.7');
    expect(screen.getByTestId('review-field-card-pe_temperature').textContent).toContain('℃');
    expect(screen.getByTestId('review-field-card-pe_blood_pressure').textContent).toContain('mmHg');
  });

  it('does_not_render_internal_quality_flag_names', () => {
    const onChange = vi.fn();
    const onFocus = vi.fn();
    const onToggle = vi.fn();
    const groups: FieldGroupDef[] = [
      { group_key: 'temperature', group_label: '体温', fields: [{ field_key: 'temperature', label: '体温' }] }
    ];
    render(
      <FieldList
        fields={[makeField({
          field_key: 'temperature',
          field_name: '体温',
          label: '体温',
          value: '37.0℃',
          quality_flags: [
            { flag: 'source_section_not_found', severity: 'warning', message: 'section lookup failed' },
            { flag: 'evidence_missing_fallback', severity: 'warning', message: 'used original_value fallback' },
            { flag: 'source_hint=auto', severity: 'warning', message: 'auto hint applied' }
          ]
        })]}
        fieldGroups={groups}
        selectedFieldKey={null}
        onChange={onChange}
        onFocusField={onFocus}
        onToggleReviewed={onToggle}
      />
    );

    const card = screen.getByTestId('review-field-card-temperature');
    const text = card.textContent ?? '';
    expect(text).not.toContain('source_section_not_found');
    expect(text).not.toContain('evidence_missing_fallback');
    expect(text).not.toContain('source_hint=');
    // also not in the document body
    const bodyText = document.body.textContent ?? '';
    expect(bodyText).not.toContain('source_section_not_found');
    expect(bodyText).not.toContain('evidence_missing_fallback');
    expect(bodyText).not.toContain('source_hint=');
  });

  it('functional_updater_prevents_data_loss_on_rapid_consecutive_updates', () => {
    // 快速连续调用 updateField 不应丢失前一次修改
    const initial: ReviewField[] = [
      makeField({ field_key: 'f1', value: 'a', final_value: 'a' }),
      makeField({ field_key: 'f2', value: 'x', final_value: 'x' }),
    ];

    // 模拟连续两次快速更新(在同一次渲染闭包内)
    // 第一次:更新 f1 为 'b'
    const mid = ((prev: ReviewField[]) =>
      prev.map((f) => (f.field_key === 'f1' ? { ...f, value: 'b', final_value: 'b', status: 'modified' as const } : f))
    )(initial);
    // 第二次:基于第一次结果更新 f2 为 'y' — 使用 functional updater 不会丢失 f1='b'
    const final = ((prev: ReviewField[]) =>
      prev.map((f) => (f.field_key === 'f2' ? { ...f, value: 'y', final_value: 'y', status: 'modified' as const } : f))
    )(mid);

    // 最终结果应同时包含两次修改
    expect(final.find((f) => f.field_key === 'f1')?.final_value).toBe('b');
    expect(final.find((f) => f.field_key === 'f2')?.final_value).toBe('y');
  });
});
