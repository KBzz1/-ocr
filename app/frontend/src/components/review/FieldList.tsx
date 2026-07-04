import { useLayoutEffect, useRef } from 'react';
import type { ReviewField, FieldGroupDef, QwenJudgementStatus } from '../../api/review';
import type { FieldStatus } from '../../styles/status';

type FieldListProps = {
  fields: ReviewField[];
  fieldGroups?: FieldGroupDef[];
  selectedFieldKey: string | null;
  onChange: (fields: ReviewField[]) => void;
  onFocusField: (field: ReviewField) => void;
  onToggleReviewed: (field: ReviewField) => void;
  readOnly?: boolean;
};

function buildEmptyFieldStub(fieldKey: string, label: string): ReviewField {
  return {
    field_key: fieldKey,
    field_name: label,
    label,
    value: '',
    status: 'unreviewed' as FieldStatus
  };
}

function mergeFieldDefinitionMetadata(field: ReviewField, fieldDef: FieldGroupDef['fields'][number]): ReviewField {
  return {
    ...field,
    field_name: field.field_name ?? fieldDef.label,
    label: field.label ?? fieldDef.label,
    qwen_type: field.qwen_type ?? fieldDef.qwen_type,
    qwen_path: field.qwen_path ?? fieldDef.qwen_path,
    review_control: field.review_control ?? fieldDef.review_control,
    options: field.options ?? fieldDef.options,
  };
}

function groupFields(
  fields: ReviewField[],
  fieldGroups: FieldGroupDef[] | undefined,
  includeAllSchemaFields = false,
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
        groupFields.push(mergeFieldDefinitionMetadata(field, fdef));
        usedKeys.add(fdef.field_key);
      } else if (includeAllSchemaFields) {
        groupFields.push(mergeFieldDefinitionMetadata(buildEmptyFieldStub(fdef.field_key, fdef.label), fdef));
      }
    }
    if (groupFields.length > 0 || includeAllSchemaFields) {
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

function getFieldLayoutClass(field: ReviewField, value: string) {
  const label = field.field_name ?? field.label ?? field.field_key;
  if (value.length > 56 || value.includes('\n')) return 'field-card__item--long';
  if (field.qwen_type === 'J' || field.review_control === 'judgement') return 'field-card__item--medium';
  if (value.length > 22 || label.length > 6) return 'field-card__item--medium';
  return 'field-card__item--short';
}

const QWEN_J_OPTIONS = [
  { value: '正常', status: 'normal', label: '正常' },
  { value: '异常', status: 'abnormal', label: '异常' },
  { value: '', status: 'not_mentioned', label: '未提及' },
] as const;

function getQwenStatusFromValue(value: string): QwenJudgementStatus {
  if (value === '正常') return 'normal';
  if (value === '异常') return 'abnormal';
  if (value === '不确定') return 'uncertain';
  if (value === '') return 'not_mentioned';
  return 'uncertain';
}

// 医生可见的"重点核验"来自后端给出的 attention_* 或字段复核状态;
// 不再根据内部 quality_flags 的标识名推断,以免内部审计名泄漏到 UI。
function getAttentionMessage(field: ReviewField): string | null {
  const text = field.attention_message?.trim();
  if (field.attention_required) return text || '需要重点核验，请核对原文';
  if (field.verification_status === 'suspicious') return text || '结果可疑，请核对原文';
  if (field.verification_status === 'failed') return text || '复核未通过，请核对原文';
  return null;
}

// not_found 字段默认是安静状态:空值时显示"未提及",不展示黄色感叹号。
// 注意:字段被后端明确标注为需要重点核验时,即便 extraction_status 是 not_found,
// 仍然展示重点核验提示。
function isQuietNotFound(field: ReviewField) {
  if (getAttentionMessage(field) !== null) return false;
  if (field.extraction_status !== 'not_found') return false;
  const value = (field.final_value ?? field.auto_value ?? field.value ?? '').toString().trim();
  return value.length === 0;
}

type DiagnosisItem = {
  index: string;
  text: string;
};

function isDiagnosisField(field: ReviewField) {
  return field.field_key === 'diagnosis_initial' || field.field_key === 'diagnosis_final';
}

function parseDiagnosisItems(value: string): DiagnosisItem[] {
  const matches = Array.from(value.matchAll(/(?:^|\s+)(\d+)[.、．]?\s*/g));
  if (matches.length <= 1) return [];
  return matches.map((match, index) => {
    const next = matches[index + 1];
    const start = (match.index ?? 0) + match[0].length;
    const end = next?.index ?? value.length;
    return {
      index: match[1],
      text: value.slice(start, end).trim(),
    };
  }).filter((item) => item.text.length > 0);
}

function formatDiagnosisItems(items: DiagnosisItem[]) {
  return items.map((item) => `${item.index}${item.text}`).join('\n');
}

function AutoGrowTextarea({
  field,
  value,
  onChange,
  onFocus,
  label,
  readOnly = false,
}: {
  field: ReviewField;
  value: string;
  onChange: (value: string) => void;
  onFocus: () => void;
  label: string;
  readOnly?: boolean;
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
      aria-label={`${label} 字段`}
      readOnly={readOnly}
      onChange={(e) => onChange(e.currentTarget.value)}
      onFocus={onFocus}
    />
  );
}

function DiagnosisListEditor({
  items,
  label,
  readOnly,
  onChange,
  onFocus,
}: {
  items: DiagnosisItem[];
  label: string;
  readOnly: boolean;
  onChange: (value: string) => void;
  onFocus: () => void;
}) {
  return (
    <div className="field-card__diagnosis-list" role="list" aria-label={`${label} 诊断列表`}>
      {items.map((item, itemIndex) => (
        <label key={`${item.index}-${itemIndex}`} className="field-card__diagnosis-item">
          <span className="field-card__diagnosis-index" aria-hidden="true">{item.index}</span>
          <input
            className="field-card__diagnosis-input"
            value={item.text}
            readOnly={readOnly}
            aria-label={`${label} 第 ${item.index} 项`}
            onFocus={onFocus}
            onChange={(event) => {
              const nextItems = items.map((current, currentIndex) =>
                currentIndex === itemIndex ? { ...current, text: event.currentTarget.value } : current
              );
              onChange(formatDiagnosisItems(nextItems));
            }}
          />
        </label>
      ))}
    </div>
  );
}

export function FieldList({
  fields,
  fieldGroups,
  selectedFieldKey,
  onChange,
  onFocusField,
  onToggleReviewed,
  readOnly = false,
}: FieldListProps) {
  if (fields.length === 0 && !(fieldGroups && fieldGroups.length > 0)) {
    return <p className="review-empty">后端未返回可审核字段</p>;
  }

  const groups = groupFields(fields, fieldGroups, readOnly);

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

  function updateQwenJudgementField(fieldKey: string, value: string, qwenStatus: NonNullable<ReviewField['qwen_status']>) {
    onChange(
      fields.map((f) =>
        f.field_key === fieldKey
          ? {
              ...f,
              value,
              final_value: value,
              qwen_status: qwenStatus,
              extraction_status: qwenStatus === 'not_mentioned' ? ('not_found' as const) : f.extraction_status,
              status: value === (f.final_value ?? f.auto_value ?? '') ? f.status : ('modified' as const),
            }
          : f,
      ),
    );
  }

  return (
    <div className="field-cards">
      {groups.map((group) => {
        const hideDuplicateFieldLabel =
          group.fields.length === 1 && (group.fields[0]?.field_name ?? group.fields[0]?.label ?? '') === group.groupLabel;

        return (
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
                const isJudgementField = field.qwen_type === 'J' || field.review_control === 'judgement';
                const currentJudgementStatus = field.qwen_status ?? getQwenStatusFromValue(value);
                const isUncertainJudgement = isJudgementField && currentJudgementStatus === 'uncertain';
                const quietNotFound = isQuietNotFound(field);
                const diagnosisItems = isDiagnosisField(field) ? parseDiagnosisItems(value) : [];
                const showDiagnosisItems = !quietNotFound && !isJudgementField && diagnosisItems.length > 1;
                const attentionMessage = getAttentionMessage(field);
                const isAttention = attentionMessage !== null;
                const attentionAriaLabel = `重点核验：${attentionMessage ?? ''}`;
                const reviewCheck = (
                  <button
                    type="button"
                    className="field-card__review-check"
                    aria-label={`${isReviewed ? '取消审核' : '审核'} ${fieldLabel}`}
                    aria-pressed={isReviewed}
                    disabled={readOnly}
                    onClick={(event) => {
                      event.stopPropagation();
                      onFocusField(field);
                      onToggleReviewed(field);
                    }}
                  >
                    {isReviewed ? '✓' : ''}
                  </button>
                );

                return (
                  <div
                    key={field.field_key}
                    className={`field-card__item ${getFieldLayoutClass(field, value)}${isSelected ? ' is-focused' : ''}${isSuspicious ? ' is-suspicious' : ''}${isReviewed ? ' is-reviewed' : ''}${quietNotFound ? ' is-not-found' : ''}${isAttention ? ' is-attention' : ''}`}
                    data-testid={`review-field-card-${field.field_key}`}
                    onClick={() => onFocusField(field)}
                  >
                    {!hideDuplicateFieldLabel ? (
                      <div className="field-card__topline">
                        <label
                          className="field-card__label"
                          htmlFor={`review-field-${field.field_key}`}
                        >
                          {fieldLabel}
                        </label>
                        {isAttention ? (
                          <span
                            className="field-card__flag"
                            aria-label={attentionAriaLabel}
                            data-tooltip={attentionMessage ?? ''}
                            tabIndex={0}
                          >
                            !
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    {isAttention ? (
                      hideDuplicateFieldLabel ? (
                        <div className="field-card__topline">
                          <span
                            className="field-card__flag"
                            aria-label={attentionAriaLabel}
                            data-tooltip={attentionMessage ?? ''}
                            tabIndex={0}
                          >
                            !
                          </span>
                        </div>
                      ) : null
                    ) : null}
                    <div className={`field-card__value-row${isJudgementField ? ' field-card__value-row--judgement' : ''}${showDiagnosisItems ? ' field-card__value-row--diagnosis' : ''}`}>
                      {quietNotFound ? (
                        <div
                          id={`review-field-${field.field_key}`}
                          className="field-card__placeholder"
                          role="textbox"
                          aria-readonly="true"
                          aria-label={`${fieldLabel} 未提及`}
                          data-placeholder="未提及"
                          onClick={() => onFocusField(field)}
                        >
                          未提及
                        </div>
                      ) : isJudgementField ? (
                        <div className="field-card__judgement" role="group" aria-label={`${fieldLabel} 状态`}>
                          {QWEN_J_OPTIONS.map((option) => {
                            const pressed = !isUncertainJudgement && currentJudgementStatus === option.status;
                            return (
                              <button
                                key={option.status}
                                type="button"
                                className="field-card__judgement-option"
                                aria-label={`${option.label} ${fieldLabel}`}
                                aria-pressed={pressed}
                                disabled={readOnly}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onFocusField(field);
                                  updateQwenJudgementField(field.field_key, option.value, option.status);
                                }}
                              >
                                <span className="field-card__judgement-dot" aria-hidden="true" />
                                <span>{option.label}</span>
                              </button>
                            );
                          })}
                          {reviewCheck}
                        </div>
                      ) : showDiagnosisItems ? (
                        <DiagnosisListEditor
                          items={diagnosisItems}
                          label={fieldLabel}
                          readOnly={readOnly}
                          onChange={(nextValue) => updateField(field.field_key, nextValue)}
                          onFocus={() => onFocusField(field)}
                        />
                      ) : (
                        <AutoGrowTextarea
                          field={field}
                          value={value}
                          label={fieldLabel}
                          onChange={(nextValue) => updateField(field.field_key, nextValue)}
                          onFocus={() => onFocusField(field)}
                          readOnly={readOnly}
                        />
                      )}
                      {isJudgementField ? (
                        isUncertainJudgement ? (
                          <span
                            className="field-card__judgement-warning"
                            aria-label={`${fieldLabel} 不确定，请核对原文`}
                            title="不确定，请核对原文"
                          >
                            !
                          </span>
                        ) : (
                          <span className="field-card__judgement-warning field-card__judgement-warning--empty" aria-hidden="true" />
                        )
                      ) : null}
                      {!isJudgementField ? reviewCheck : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
