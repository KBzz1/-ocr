export type TaskStatus =
  | 'created'
  | 'uploading'
  | 'uploaded'
  | 'processing'
  | 'ready_for_review'
  | 'confirmed'
  | 'exported'
  | 'failed';

export type CaptureSessionStatus = 'active' | 'expired' | 'locked' | 'cancelled';

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

export type CaptureSessionSummary = {
  id: string;
  status: CaptureSessionStatus;
  uploadedPages: number;
  remainingTimeText: string;
  createdAtText: string;
  qrCodeValue?: string;
};

export type TaskSummary = {
  id: string;
  createdAtText: string;
  pageCount: number;
  status: TaskStatus;
  reviewedFields: number;
  totalFields: number;
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
  currentSession: CaptureSessionSummary | null;
  tasks: TaskSummary[];
  reminders: SystemReminder[];
};

export type WorkstationPageData = WorkstationFixtures;
