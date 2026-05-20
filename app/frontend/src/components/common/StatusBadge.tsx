import type { TaskStatus } from '../../pages/workstation/workstation.types';

const taskStatusText: Record<TaskStatus, string> = {
  uploading: '上传中',
  processing: '处理中',
  review: '待审核',
  done: '已完成',
  failed: '失败'
};

export function getTaskStatusText(status: TaskStatus) {
  return taskStatusText[status];
}

type StatusBadgeProps = {
  status: TaskStatus;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${status}`}>{taskStatusText[status]}</span>;
}
