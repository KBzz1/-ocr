import { apiRequest } from './client';
import type { TaskSummary } from './tasks';

export interface UploadedImage {
  page_id: string;
  task_id: string;
  page_no: number;
  preview_url?: string;
  image_width?: number | null;
  image_height?: number | null;
  uploaded_at: string;
}

export interface DocumentTypeOption {
  document_type: string;
  label: string;
  schema_version: string;
}

export interface TaskDocumentTypeUpdate {
  task_id: string;
  document_type: string;
  document_type_label?: string;
  schema_version?: string;
  prompt_version?: string;
}

export interface TaskUploadStatus {
  task_id: string;
  status: TaskSummary['status'];
  page_count: number;
  images: UploadedImage[];
  document_type?: string;
  document_type_label?: string;
  schema_version?: string;
  available_document_types?: DocumentTypeOption[];
}

export function buildTaskImageFormData(
  file: File,
  dimensions?: { image_width?: number; image_height?: number }
) {
  const body = new FormData();
  body.append('image', file);
  if (dimensions?.image_width) body.append('image_width', String(dimensions.image_width));
  if (dimensions?.image_height) body.append('image_height', String(dimensions.image_height));
  return body;
}

export function uploadTaskImage(
  taskId: string,
  token: string,
  file: File,
  dimensions?: { image_width?: number; image_height?: number }
) {
  const body = buildTaskImageFormData(file, dimensions);
  return apiRequest<UploadedImage>(
    `/api/mobile-upload/${encodeURIComponent(taskId)}/images?token=${encodeURIComponent(token)}`,
    {
      method: 'POST',
      body
    }
  );
}

export function getTaskUploadStatus(taskId: string, token: string) {
  return apiRequest<TaskUploadStatus>(
    `/api/mobile-upload/${encodeURIComponent(taskId)}?token=${encodeURIComponent(token)}`
  );
}

export function finishTaskUpload(taskId: string, token: string) {
  return apiRequest<TaskSummary>(
    `/api/mobile-upload/${encodeURIComponent(taskId)}/finish?token=${encodeURIComponent(token)}`,
    {
      method: 'POST'
    }
  );
}

export function updateTaskDocumentType(taskId: string, token: string, documentType: string) {
  return apiRequest<TaskDocumentTypeUpdate>(
    `/api/mobile-upload/${encodeURIComponent(taskId)}/document-type?token=${encodeURIComponent(token)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_type: documentType })
    }
  );
}
