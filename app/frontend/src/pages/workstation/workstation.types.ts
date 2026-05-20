import type { CreateTaskResult, TaskStatus } from '../../api/tasks';

export type { TaskStatus };

export type SystemStatus = {
  startup: 'running' | 'error' | 'offline';
  message?: string;
  items: Array<{
    id: string;
    label: string;
    value: string;
    tone: 'success' | 'warning' | 'danger' | 'neutral';
  }>;
};

export type TaskUploadSummary = CreateTaskResult & {
  id: string;
  uploadedPages: number;
  createdAtText: string;
};

export type TaskSummary = {
  id: string;
  createdAtText: string;
  pageCount: number;
  status: TaskStatus;
  reviewedFields: number;
  totalFields: number;
  errorReason?: string | null;
};

export type ReminderTone = 'warning' | 'info' | 'success';

export type SystemReminder = {
  id: string;
  tone: ReminderTone;
  title: string;
  timeText: string;
  message: string;
  actionLabel?: string;
};

export type WorkstationFixtures = {
  systemStatus: SystemStatus;
  currentTask: TaskUploadSummary | null;
  tasks: TaskSummary[];
  reminders: SystemReminder[];
};

export type WorkstationPageData = WorkstationFixtures;
