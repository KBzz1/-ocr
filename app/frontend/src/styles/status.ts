import type { TaskStatus } from '../api/tasks';

export type FieldStatus = 'unreviewed' | 'confirmed' | 'modified';
export type ExportStatus = 'not_exported' | 'exporting' | 'exported' | 'failed';

export const taskStatusMeta: Record<
  TaskStatus,
  {
    label: string;
    tone: 'neutral' | 'info' | 'processing' | 'success' | 'danger';
    action: string;
  }
> = {
  uploading: { label: '上传中', tone: 'info', action: '查看二维码' },
  processing: { label: '处理中', tone: 'processing', action: '查看进度' },
  review: { label: '待审核', tone: 'info', action: '进入审核' },
  done: { label: '已完成', tone: 'success', action: '导出' },
  failed: { label: '失败', tone: 'danger', action: '查看原因' }
};

export const fieldStatusMeta: Record<
  FieldStatus,
  {
    label: string;
    tone: 'neutral' | 'info' | 'success' | 'warning';
  }
> = {
  unreviewed: { label: '未审核', tone: 'neutral' },
  confirmed: { label: '已确认', tone: 'success' },
  modified: { label: '已修改', tone: 'info' }
};

export const exportStatusMeta: Record<
  ExportStatus,
  {
    label: string;
    tone: 'neutral' | 'processing' | 'success' | 'danger';
  }
> = {
  not_exported: { label: '未导出', tone: 'neutral' },
  exporting: { label: '导出中', tone: 'processing' },
  exported: { label: '已导出', tone: 'success' },
  failed: { label: '导出失败', tone: 'danger' }
};

export function getTaskStatusLabel(status: TaskStatus) {
  const meta = taskStatusMeta[status];
  if (!meta) throw new Error(`未知任务状态: ${String(status)}`);
  return meta.label;
}
