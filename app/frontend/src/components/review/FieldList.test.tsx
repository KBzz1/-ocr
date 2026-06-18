import { render, screen, within } from '@testing-library/react';
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

    const textarea = screen.getByLabelText('patient_name') as HTMLTextAreaElement;
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

    const textarea = screen.getByLabelText('patient_name') as HTMLTextAreaElement;
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
    // Textarea accessible label still points at chief_complaint
    const textarea = screen.getByLabelText('chief_complaint') as HTMLTextAreaElement;
    expect(textarea.value).toBe('头痛三天');
    // The topline label element should NOT exist as a duplicate text node
    // (group title in <h3> is the only visible 主诉 label; the topline <label> is hidden)
    const section = screen.getByLabelText('主诉');
    const labelElements = section.querySelectorAll('.field-card__label');
    expect(labelElements.length).toBe(0);
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
});
