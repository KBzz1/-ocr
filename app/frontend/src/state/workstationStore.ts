import type { CaptureSession } from '../api/captureSessions';
import type { TaskStatus, TaskSummary } from '../api/tasks';
import { taskStatusMeta } from '../styles/status';

export interface TaskOverviewItem {
  key: TaskStatus;
  label: string;
  count: number;
}

const overviewStatuses: TaskStatus[] = [
  'ready_for_review',
  'processing',
  'failed',
  'exported'
];

export function buildTaskOverview(tasks: TaskSummary[]): TaskOverviewItem[] {
  return overviewStatuses.map((status) => ({
    key: status,
    label: status === 'failed' ? '处理失败' : taskStatusMeta[status].label,
    count: tasks.filter((task) => task.status === status).length
  }));
}

export function sortRecentTasks(tasks: TaskSummary[]) {
  return [...tasks]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 6);
}

export function formatRemainingTime(session: CaptureSession | null, now = Date.now()) {
  if (!session || session.status !== 'active') {
    return '不可继续上传';
  }

  const diffMs = Date.parse(session.expires_at) - now;
  if (!Number.isFinite(diffMs) || diffMs <= 0) {
    return '已过期';
  }

  const minutes = Math.ceil(diffMs / 60000);
  return `${minutes} 分钟`;
}

export function buildSystemReminders(tasks: TaskSummary[], session: CaptureSession | null) {
  const reminders: string[] = [];
  const failedTask = tasks.find((task) => task.status === 'failed');

  if (failedTask) {
    reminders.push(`任务 ${failedTask.task_id} 处理失败，请查看原因后重新处理。`);
  }

  if (session?.status === 'expired') {
    reminders.push('采集会话已过期，请重新生成二维码。');
  }

  return reminders;
}
