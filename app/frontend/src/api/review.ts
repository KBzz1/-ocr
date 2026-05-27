import { apiRequest } from './client';
import type { TaskStatus } from './tasks';
import type { FieldStatus } from '../styles/status';

export interface ReviewEvidence {
  page_id?: string;
  page_no?: number;
  text?: string;
  bounding_box?: Array<{
    x: number;
    y: number;
  }>;
}

export interface ReviewField {
  field_key: string;
  label?: string;
  field_name?: string;
  value: string;
  status: FieldStatus;
  evidence?: ReviewEvidence[];
  candidate_value?: string;
  auto_value?: string;
  final_value?: string;
  extraction_status?: string;
  verification_status?: string;
  quality_flags?: Array<{ flag: string; severity: string; message: string }>;
  ocr_correction?: {
    applied: boolean;
    raw: string;
    normalized: string;
    reason: string;
  };
}

export interface FieldGroupDef {
  group_key: string;
  group_label: string;
  fields: Array<{ field_key: string; label: string }>;
}

export interface ReviewResult {
  fields: ReviewField[];
  ocr_text?: string;
  pages?: Array<{ page_id: string; page_no: number; preview_url?: string; parsed_text?: string; image_url?: string }>;
  field_groups?: FieldGroupDef[];
}

export interface ReviewPayload {
  task_id: string;
  status: TaskStatus;
  review_result: ReviewResult;
}

export interface SaveReviewFieldInput {
  final_value: string;
  status: FieldStatus;
}

export interface SaveReviewFieldResult {
  field_key: string;
  final_value: string;
  status: FieldStatus;
}

function normalizeEvidence(raw: unknown): ReviewEvidence[] {
  if (Array.isArray(raw)) return raw;
  if (typeof raw === 'string' && raw.length > 0) return [{ text: raw }];
  return [];
}

function normalizeReviewField(field: ReviewField): ReviewField {
  const label = field.label ?? field.field_name;
  const candidateValue = field.candidate_value ?? field.auto_value;
  const value = field.value ?? (field.final_value === '' ? undefined : field.final_value) ?? candidateValue ?? '';
  return {
    ...field,
    label,
    value,
    candidate_value: candidateValue,
    final_value: value,
    evidence: normalizeEvidence(field.evidence)
  };
}

function normalizeReviewPayload(data: unknown): ReviewPayload {
  const value = data as Partial<ReviewPayload> & Partial<ReviewResult> & { task_id?: string; status?: TaskStatus };
  const reviewResult = value.review_result ?? {
    fields: value.fields ?? [],
    ocr_text: value.ocr_text,
    pages: value.pages
  };
  return {
    task_id: value.task_id ?? '',
    status: value.status ?? 'review',
    review_result: {
      ...reviewResult,
      fields: (reviewResult.fields ?? []).map(normalizeReviewField)
    }
  };
}

export async function getReview(taskId: string) {
  const data = await apiRequest<unknown>(`/api/tasks/${encodeURIComponent(taskId)}/review`);
  return normalizeReviewPayload(data);
}

export async function saveReview(taskId: string, fields: ReviewField[]) {
  const data = await apiRequest<unknown>(`/api/tasks/${encodeURIComponent(taskId)}/review`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ fields })
  });
  return normalizeReviewPayload(data);
}

export async function getReviewResult(taskId: string) {
  const data = await getReview(taskId);
  return {
    task_id: data.task_id,
    fields: data.review_result.fields,
    summary: { unreviewed: 0, confirmed: 0, modified: 0 }
  };
}

export async function saveReviewField(
  taskId: string,
  fieldKey: string,
  input: SaveReviewFieldInput
) {
  const current = await getReview(taskId);
  const fields = current.review_result.fields.map((field) =>
    field.field_key === fieldKey
      ? { ...field, value: input.final_value, final_value: input.final_value, status: input.status }
      : field
  );
  await saveReview(taskId, fields);
  return { field_key: fieldKey, final_value: input.final_value, status: input.status };
}

export async function reopenReview(taskId: string) {
  return apiRequest<unknown>(`/api/tasks/${encodeURIComponent(taskId)}/review/reopen`, {
    method: 'POST'
  });
}
