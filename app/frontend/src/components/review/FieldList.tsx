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
    <div className="review-fields-table-wrap">
      <table className="review-fields-table">
        <thead>
          <tr>
            <th>字段</th>
            <th>人工值</th>
            <th>候选值</th>
            <th>来源</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => {
            const sourcePageNo = field.evidence?.find((item) => item.page_no)?.page_no;
            const isSelected = field.field_key === selectedFieldKey;

            return (
              <tr className={isSelected ? 'is-selected' : ''} key={field.field_key}>
                <th scope="row">
                  <label htmlFor={`review-field-${field.field_key}`}>{field.label ?? field.field_key}</label>
                </th>
                <td>
                  <textarea
                    id={`review-field-${field.field_key}`}
                    rows={2}
                    value={field.value}
                    aria-label={field.field_key}
                    onChange={(event) => updateField(field.field_key, event.currentTarget.value)}
                    onFocus={() => onFocusField(field)}
                  />
                </td>
                <td>{field.candidate_value ? <span className="review-candidate">{field.candidate_value}</span> : <span className="review-muted">-</span>}</td>
                <td>{sourcePageNo ? <span className="review-field__evidence">第 {sourcePageNo} 页</span> : <span className="review-muted">-</span>}</td>
                <td>
                  <span className={`review-field-status review-field-status--${field.status}`}>
                    {getStatusLabel(field.status)}
                  </span>
                  {field.verification_status === 'suspicious' && <span className="field-risk">需重点核验</span>}
                  {field.quality_flags?.map((flag, idx) => (
                    <small key={`${flag.flag}-${idx}`} className="field-risk-detail">{flag.message}</small>
                  ))}
                  {field.ocr_correction?.applied && (
                    <small className="field-ocr-correction">
                      OCR: {field.ocr_correction.raw} -&gt; {field.ocr_correction.normalized}，{field.ocr_correction.reason}
                    </small>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
