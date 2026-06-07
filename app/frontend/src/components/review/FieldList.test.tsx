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
});
