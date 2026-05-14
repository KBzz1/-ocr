import type { ReviewField } from '../../api/review';
import type { FieldStatus } from '../../styles/status';

type FieldListProps = {
  fields: ReviewField[];
  savingFields: Record<string, boolean>;
  onEvidence: (field: ReviewField) => void;
  onSave: (field: ReviewField, value: string) => void;
  onStatus: (field: ReviewField, status: FieldStatus) => void;
  getStatusLabel: (status: FieldStatus) => string;
};

function getEvidenceLabel(field: ReviewField) {
  const evidence = field.evidence[0];
  if (!evidence) return null;
  return `来源：第${evidence.page_no ?? '?'}页 ${evidence.text ?? ''}`.trim();
}

export function FieldList({
  fields,
  savingFields,
  onEvidence,
  onSave,
  onStatus,
  getStatusLabel
}: FieldListProps) {
  if (fields.length === 0) {
    return <p className="review-empty">后端未返回可审核字段</p>;
  }

  return (
    <div className="review-fields">
      {fields.map((field) => {
        const evidenceLabel = getEvidenceLabel(field);
        return (
          <article className="review-field" key={field.field_key}>
            <div className="review-field__header">
              <label htmlFor={`review-field-${field.field_key}`}>{field.label}</label>
              <span className={`review-field-status review-field-status--${field.status}`}>
                {getStatusLabel(field.status)}
              </span>
            </div>
            <textarea
              id={`review-field-${field.field_key}`}
              defaultValue={field.final_value}
              aria-label={field.label}
              disabled={savingFields[field.field_key]}
              onBlur={(event) => {
                if (event.currentTarget.value !== field.final_value) {
                  onSave(field, event.currentTarget.value);
                }
              }}
            />
            <p className="review-candidate">候选值：{field.candidate_value || '空'}</p>
            <div className="review-field__evidence">
              {evidenceLabel ? (
                <span>{evidenceLabel}</span>
              ) : (
                <>
                  <span>未定位来源</span>
                  <span>需人工确认</span>
                </>
              )}
              <button type="button" onClick={() => onEvidence(field)}>
                查看{field.label}来源
              </button>
            </div>
            <div className="review-field__actions">
              <button type="button" onClick={() => onStatus(field, 'confirmed')}>
                确认
              </button>
              <button type="button" onClick={() => onStatus(field, 'suspicious')}>
                标记存疑
              </button>
              <button type="button" onClick={() => onSave(field, '')}>
                清空
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}
