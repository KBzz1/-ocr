import { useLayoutEffect, useRef } from 'react';
import type { ReviewField } from '../../api/review';

type FieldGroupDef = {
  group_key: string;
  group_label: string;
  fields: Array<{ field_key: string; label: string }>;
};

type FieldListProps = {
  fields: ReviewField[];
  fieldGroups?: FieldGroupDef[];
  selectedFieldKey: string | null;
  onChange: (fields: ReviewField[]) => void;
  onFocusField: (field: ReviewField) => void;
  onToggleReviewed: (field: ReviewField) => void;
};

function groupFields(
  fields: ReviewField[],
  fieldGroups: FieldGroupDef[] | undefined,
): Array<{ groupKey: string; groupLabel: string; fields: ReviewField[] }> {
  if (!fieldGroups || fieldGroups.length === 0) {
    return [{ groupKey: '_all', groupLabel: '全部字段', fields }];
  }

  const fieldMap = new Map<string, ReviewField>();
  for (const f of fields) {
    fieldMap.set(f.field_key, f);
  }

  const usedKeys = new Set<string>();
  const groups: Array<{ groupKey: string; groupLabel: string; fields: ReviewField[] }> = [];

  for (const group of fieldGroups) {
    const groupFields: ReviewField[] = [];
    for (const fdef of group.fields) {
      const field = fieldMap.get(fdef.field_key);
      if (field) {
        groupFields.push({ ...field, field_name: fdef.label || field.field_name });
        usedKeys.add(fdef.field_key);
      }
    }
    if (groupFields.length > 0) {
      groups.push({ groupKey: group.group_key, groupLabel: group.group_label, fields: groupFields });
    }
  }

  const orphans: ReviewField[] = [];
  for (const f of fields) {
    if (!usedKeys.has(f.field_key)) {
      orphans.push(f);
    }
  }
  if (orphans.length > 0) {
    groups.push({ groupKey: '_other', groupLabel: '其他', fields: orphans });
  }

  return groups;
}

function getFieldValueLengthClass(value: string) {
  if (value.length > 56 || value.includes('\n')) return 'field-card__item--long';
  if (value.length > 18) return 'field-card__item--medium';
  return 'field-card__item--short';
}

const evidenceRiskFlags = new Set([
  'value_not_in_evidence',
  'missing_evidence',
  'evidence_missing',
  'evidence_not_found',
  'source_not_found',
]);

const ocrRiskFlags = new Set([
  'ocr_label_ambiguity',
  'unit_symbol_ambiguity',
  'ocr_numeric_conflict',
  'low_ocr_quality',
  'llm_review_suspicious',
  'llm_review_failed',
]);

function getInitialExtractedSnippet(field: ReviewField) {
  return (field.candidate_value ?? field.auto_value ?? field.final_value ?? field.value ?? '').trim();
}

function hasEvidenceText(field: ReviewField) {
  return (field.evidence ?? []).some((evidence) => (evidence.text ?? '').trim().length > 0);
}

function isRiskFlag(
  flag: { flag: string; message: string },
  flagSet: Set<string>,
  keywords: string[],
) {
  const flagName = flag.flag.toLowerCase();
  const message = flag.message.toLowerCase();
  return (
    flagSet.has(flag.flag) ||
    keywords.some((kw) => flagName.includes(kw) || message.includes(kw))
  );
}

function isEvidenceRiskFlag(flag: { flag: string; message: string }) {
  return isRiskFlag(flag, evidenceRiskFlags, [
    'evidence',
    'source',
    '未找到证据',
    '未能在 evidence',
    '无 evidence',
  ]);
}

function isOcrRiskFlag(flag: { flag: string; message: string }) {
  return isRiskFlag(flag, ocrRiskFlags, ['ocr', '错读', '纠偏']);
}

function shouldShowRiskFlag(field: ReviewField) {
  const flags = field.quality_flags ?? [];
  if (flags.some(isEvidenceRiskFlag)) return true;
  if (flags.some(isOcrRiskFlag)) return true;
  if (flags.length > 0) return false;
  return (
    field.verification_status === 'suspicious' &&
    getInitialExtractedSnippet(field).length > 0 &&
    !hasEvidenceText(field)
  );
}

function getFieldRiskDescription(field: ReviewField) {
  const flags = field.quality_flags ?? [];
  const ocrFlag = flags.find(isOcrRiskFlag);
  if (ocrFlag) {
    return ocrFlag.message || 'OCR 结果需重点核验';
  }
  const snippet = getInitialExtractedSnippet(field);
  return snippet ? `未找到证据；最开始提取片段：${snippet}` : '未找到证据';
}

function AutoGrowTextarea({
  field,
  value,
  onChange,
  onFocus,
}: {
  field: ReviewField;
  value: string;
  onChange: (value: string) => void;
  onFocus: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.max(el.scrollHeight, 34)}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      id={`review-field-${field.field_key}`}
      className="field-card__input"
      rows={1}
      value={value}
      aria-label={field.field_key}
      onChange={(e) => onChange(e.currentTarget.value)}
      onFocus={onFocus}
    />
  );
}

export function FieldList({
  fields,
  fieldGroups,
  selectedFieldKey,
  onChange,
  onFocusField,
  onToggleReviewed,
}: FieldListProps) {
  if (fields.length === 0) {
    return <p className="review-empty">后端未返回可审核字段</p>;
  }

  const groups = groupFields(fields, fieldGroups);

  function updateField(fieldKey: string, value: string) {
    onChange(
      fields.map((f) =>
        f.field_key === fieldKey
          ? {
              ...f,
              value,
              final_value: value,
              status: value === (f.final_value ?? f.auto_value ?? '') ? f.status : ('modified' as const),
            }
          : f,
      ),
    );
  }

  return (
    <div className="field-cards">
      {groups.map((group) => (
        <section key={group.groupKey} className="field-card" aria-label={group.groupLabel}>
          <header className="field-card__header">
            <h3>{group.groupLabel}</h3>
            <span>{group.fields.length} 个字段</span>
          </header>

          <div className="field-card__body">
            {group.fields.map((field) => {
              const isSuspicious = field.verification_status === 'suspicious';
              const isSelected = field.field_key === selectedFieldKey;
              const isReviewed = field.status === 'confirmed';
              const value = field.final_value ?? field.auto_value ?? '';
              const fieldLabel = field.field_name ?? field.label ?? field.field_key;
              const riskDescription = shouldShowRiskFlag(field) ? getFieldRiskDescription(field) : null;

              return (
                <div
                  key={field.field_key}
                  className={`field-card__item ${getFieldValueLengthClass(value)}${isSelected ? ' is-focused' : ''}${isSuspicious ? ' is-suspicious' : ''}${isReviewed ? ' is-reviewed' : ''}`}
                  data-testid={`review-field-card-${field.field_key}`}
                  onClick={() => onFocusField(field)}
                >
                  <div className="field-card__topline">
                    <label
                      className="field-card__label"
                      htmlFor={`review-field-${field.field_key}`}
                    >
                      {fieldLabel}
                    </label>
                    {riskDescription ? (
                      <span
                        className="field-card__flag"
                        aria-label={`重点核验：${riskDescription}`}
                        data-tooltip={riskDescription}
                        tabIndex={0}
                      >
                        !
                      </span>
                    ) : null}
                  </div>
                  <div className="field-card__value-row">
                    <AutoGrowTextarea
                      field={field}
                      value={value}
                      onChange={(nextValue) => updateField(field.field_key, nextValue)}
                      onFocus={() => onFocusField(field)}
                    />
                    <button
                      type="button"
                      className="field-card__review-check"
                      aria-label={`${isReviewed ? '取消审核' : '审核'} ${fieldLabel}`}
                      aria-pressed={isReviewed}
                      onClick={(event) => {
                        event.stopPropagation();
                        onFocusField(field);
                        onToggleReviewed(field);
                      }}
                    >
                      {isReviewed ? '✓' : ''}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
