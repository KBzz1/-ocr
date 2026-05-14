import { apiRequest } from './client';

export type TaskStatus =
  | 'created'
  | 'uploading'
  | 'uploaded'
  | 'processing'
  | 'ready_for_review'
  | 'confirmed'
  | 'exported'
  | 'failed';

export interface TaskSummary {
  task_id: string;
  session_id?: string;
  status: TaskStatus;
  created_at: string;
  page_count: number;
  error_code?: string | null;
  error_message?: string | null;
  review_summary?: {
    status?: string | null;
    confirmed_count?: number;
    total_count?: number;
  };
  export_summary?: {
    formats?: string[];
  };
}

export type TaskDetail = TaskSummary & {
  pages?: Array<{
    page_id: string;
    page_no?: number;
    page_index?: number;
    status?: string;
  }>;
  status_history?: Array<{
    status: TaskStatus;
    changed_at: string;
    message?: string;
  }>;
};

export interface TaskRetryResult {
  task_id: string;
  status: TaskStatus;
}

interface TaskListResponse {
  tasks: TaskSummary[];
}

export async function getTasks() {
  const data = await apiRequest<TaskListResponse>('/api/tasks');
  return data.tasks;
}

export function getTaskDetail(taskId: string) {
  return apiRequest<TaskDetail>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function retryTaskProcessing(taskId: string) {
  return apiRequest<TaskRetryResult>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
    method: 'POST'
  });
}
