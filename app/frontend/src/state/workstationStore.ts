import type { TaskStatus, TaskSummary } from '../api/tasks';
import { taskStatusMeta } from '../styles/status';

export interface TaskOverviewItem {
  key: TaskStatus;
  label: string;
  count: number;
}

const overviewStatuses: TaskStatus[] = ['uploading', 'processing', 'review', 'done', 'failed'];

export function buildTaskOverview(tasks: TaskSummary[]): TaskOverviewItem[] {
  return overviewStatuses.map((status) => ({
    key: status,
    label: taskStatusMeta[status].label,
    count: tasks.filter((task) => task.status === status).length
  }));
}

export function sortRecentTasks(tasks: TaskSummary[]) {
  return [...tasks]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 6);
}

export function buildSystemReminders(tasks: TaskSummary[]) {
  const reminders: string[] = [];
  const failedTask = tasks.find((task) => task.status === 'failed');

  if (failedTask) {
    reminders.push(`任务 ${failedTask.display_name ?? failedTask.task_id} 处理失败，请查看原因后重新处理。`);
  }

  return reminders;
}
