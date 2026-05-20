import type { ReviewField } from '../../api/review';
import type { FieldStatus } from '../../styles/status';

type FieldListProps = {
  fields: ReviewField[];
  selectedFieldKey: string | null;
  onChange: (fields: ReviewField[]) => void;
  onFocusField: (field: ReviewField) => void;
  getStatusLabel: (status: FieldStatus) => string;
};

function nextStatus(field: ReviewField, value: string): FieldStatus {
  return value === (field.final_value ?? field.value) ? field.status : 'modified';
}

export function FieldList({ fields, selectedFieldKey, onChange, onFocusField, getStatusLabel }: FieldListProps) {
  if (fields.length === 0) {
    return <p className="review-empty">后端未返回可审核字段</p>;
  }

  function updateField(fieldKey: string, value: string) {
    onChange(
      fields.map((field) =>
        field.field_key === fieldKey
          ? { ...field, value, final_value: value, status: nextStatus(field, value) }
          : field
      )
    );
  }

  return (
    <div className="review-fields">
      {fields.map((field) => {
        const sourcePageNo = field.evidence?.find((item) => item.page_no)?.page_no;
        const isSelected = field.field_key === selectedFieldKey;

        return (
          <article className={`review-field${isSelected ? ' is-selected' : ''}`} key={field.field_key}>
            <div className="review-field__header">
              <label htmlFor={`review-field-${field.field_key}`}>{field.label ?? field.field_key}</label>
              <span className={`review-field-status review-field-status--${field.status}`}>
                {getStatusLabel(field.status)}
              </span>
            </div>
            <textarea
              id={`review-field-${field.field_key}`}
              value={field.value}
              aria-label={field.field_key}
              onChange={(event) => updateField(field.field_key, event.currentTarget.value)}
              onFocus={() => onFocusField(field)}
            />
            {field.candidate_value ? <p className="review-candidate">候选值：{field.candidate_value}</p> : null}
            {sourcePageNo ? <p className="review-field__evidence">来源：第 {sourcePageNo} 页</p> : null}
          </article>
        );
      })}
    </div>
  );
}
