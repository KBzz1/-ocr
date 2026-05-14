import type { TaskStatus } from '../../pages/workstation/workstation.types';

const taskStatusText: Record<TaskStatus, string> = {
  created: '已创建',
  uploading: '上传中',
  uploaded: '上传完成',
  processing: '处理中',
  ready_for_review: '待审核',
  confirmed: '已确认',
  exported: '已导出',
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
