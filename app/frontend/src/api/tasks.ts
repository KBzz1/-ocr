import { apiRequest } from './client';

export type TaskStatus = 'uploading' | 'processing' | 'review' | 'done' | 'failed';

export interface CreateTaskResult {
  task_id: string;
  display_name: string;
  status: 'uploading';
  upload_token: string;
  mobile_upload_url: string;
}

export interface TaskSummary {
  task_id: string;
  display_name: string;
  status: TaskStatus;
  created_at: string;
  updated_at?: string;
  page_count: number;
  processing_summary?: {
    stage: string;
    status: string;
    label: string;
    progress_percent: number;
    page_count?: number;
    started_at?: string | null;
    updated_at?: string | null;
    elapsed_seconds?: number;
  } | null;
  upload_token?: string;
  mobile_upload_url?: string;
  error_code?: string | null;
  error_message?: string | null;
  review_summary?: {
    status?: string | null;
    confirmed_count?: number;
    total_count?: number;
  };
  export_summary?: {
    last_exported_at?: string | null;
    formats?: string[];
    files?: Array<{ format: string; relative_path: string }>;
  };
}

export type TaskDetail = TaskSummary & {
  pages?: Array<{
    page_id: string;
    page_no?: number;
    page_index?: number;
    status?: string;
  }>;
  images?: Array<{
    page_id: string;
    page_no?: number;
    preview_url?: string;
    image_url?: string;
    original_image_path?: string;
  }>;
  status_history?: Array<{
    status?: TaskStatus;
    from_status?: TaskStatus | null;
    to_status?: TaskStatus;
    changed_at: string;
    message?: string;
    reason?: string;
  }>;
};

export interface TaskRetryResult {
  task_id: string;
  status: TaskStatus;
  error_code?: string | null;
  error_message?: string | null;
}

export interface TaskReextractResult {
  task_id: string;
  status: 'review';
  run_id: string;
  source: 'ocr_text_only';
  schema_version?: string;
  prompt_version?: string;
  candidate_count: number;
}

interface TaskListResponse {
  tasks: Array<Omit<TaskSummary, 'status'> & { status: string }>;
}

function normalizeTaskStatus(status: string): TaskStatus {
  if (status === 'uploading' || status === 'processing' || status === 'review' || status === 'done' || status === 'failed') {
    return status;
  }
  if (status === 'ready_for_review') return 'review';
  if (status === 'confirmed' || status === 'exported') return 'done';
  return 'uploading';
}

function normalizeTaskSummary(task: Omit<TaskSummary, 'status'> & { status: string }): TaskSummary {
  return {
    ...task,
    status: normalizeTaskStatus(task.status)
  };
}

function shouldShowTask(task: TaskSummary) {
  return !(task.status === 'uploading' && task.page_count === 0);
}

export async function getTasks() {
  const data = await apiRequest<TaskListResponse>('/api/tasks');
  return data.tasks.map(normalizeTaskSummary).filter(shouldShowTask);
}

export function createTask() {
  return apiRequest<CreateTaskResult>('/api/tasks', { method: 'POST' });
}

export function getTaskDetail(taskId: string) {
  return apiRequest<TaskDetail>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function processTask(taskId: string) {
  return apiRequest<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/process`, {
    method: 'POST'
  });
}

export function completeTask(taskId: string) {
  return apiRequest<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/complete`, {
    method: 'POST'
  });
}

export function retryTaskProcessing(taskId: string) {
  return processTask(taskId) as Promise<TaskRetryResult>;
}

export function reextractTaskFromOcr(taskId: string) {
  return apiRequest<TaskReextractResult>(`/api/tasks/${encodeURIComponent(taskId)}/reextract`, {
    method: 'POST'
  });
}

export function cancelTaskProcessing(taskId: string) {
  return apiRequest<TaskRetryResult>(`/api/tasks/${encodeURIComponent(taskId)}/cancel-processing`, {
    method: 'POST'
  });
}

export function renameTask(taskId: string, displayName: string) {
  return apiRequest<TaskSummary>(`/api/tasks/${encodeURIComponent(taskId)}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ display_name: displayName })
  });
}

export interface DeleteTaskResult {
  task_id: string;
  deleted: boolean;
}

export function deleteTask(taskId: string) {
  return apiRequest<DeleteTaskResult>(`/api/tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE'
  });
}
