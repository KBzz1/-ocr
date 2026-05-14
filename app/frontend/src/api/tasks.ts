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

interface TaskListResponse {
  tasks: TaskSummary[];
}

export async function getTasks() {
  const data = await apiRequest<TaskListResponse>('/api/tasks');
  return data.tasks;
}
