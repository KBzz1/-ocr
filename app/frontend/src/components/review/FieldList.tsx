import type { ReviewField } from '../../api/review';
import type { FieldStatus } from '../../styles/status';

type FieldListProps = {
  fields: ReviewField[];
  onChange: (fields: ReviewField[]) => void;
  getStatusLabel: (status: FieldStatus) => string;
};

function nextStatus(field: ReviewField, value: string): FieldStatus {
  return value === (field.final_value ?? field.value) ? field.status : 'modified';
}

export function FieldList({ fields, onChange, getStatusLabel }: FieldListProps) {
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

  function confirmField(fieldKey: string) {
    onChange(
      fields.map((field) =>
        field.field_key === fieldKey ? { ...field, status: 'confirmed' } : field
      )
    );
  }

  return (
    <div className="review-fields">
      {fields.map((field) => (
        <article className="review-field" key={field.field_key}>
          <div className="review-field__header">
            <label htmlFor={`review-field-${field.field_key}`}>{field.label ?? field.field_key}</label>
            <span className={`review-field-status review-field-status--${field.status}`}>
              {getStatusLabel(field.status)}
            </span>
          </div>
          <input
            id={`review-field-${field.field_key}`}
            value={field.value}
            aria-label={field.field_key}
            onChange={(event) => updateField(field.field_key, event.currentTarget.value)}
          />
          {field.candidate_value ? <p className="review-candidate">候选值：{field.candidate_value}</p> : null}
          <div className="review-field__actions">
            <button type="button" onClick={() => confirmField(field.field_key)}>
              确认
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
