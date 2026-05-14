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
  label: string;
  candidate_value: string;
  final_value: string;
  status: FieldStatus;
  evidence: ReviewEvidence[];
}

export interface ReviewSummary {
  unreviewed: number;
  suspicious: number;
  empty: number;
  confirmed: number;
}

export interface ReviewResult {
  task_id: string;
  fields: ReviewField[];
  summary: ReviewSummary;
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

export interface ConfirmReviewResult {
  task_id: string;
  status: TaskStatus;
}

export function getReviewResult(taskId: string) {
  return apiRequest<ReviewResult>(`/api/tasks/${encodeURIComponent(taskId)}/review`);
}

export function saveReviewField(
  taskId: string,
  fieldKey: string,
  input: SaveReviewFieldInput
) {
  return apiRequest<SaveReviewFieldResult>(
    `/api/tasks/${encodeURIComponent(taskId)}/review/fields/${encodeURIComponent(fieldKey)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(input)
    }
  );
}

export function confirmReview(taskId: string) {
  return apiRequest<ConfirmReviewResult>(
    `/api/tasks/${encodeURIComponent(taskId)}/review/confirm`,
    { method: 'POST' }
  );
}
