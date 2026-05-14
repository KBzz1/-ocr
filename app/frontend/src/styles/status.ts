import type { CaptureSessionStatus } from '../api/captureSessions';
import type { TaskStatus } from '../api/tasks';

export type FieldStatus = 'unreviewed' | 'confirmed' | 'modified' | 'suspicious' | 'empty';
export type ExportStatus = 'not_exported' | 'exporting' | 'exported' | 'failed';

export const taskStatusMeta: Record<TaskStatus, {
  label: string;
  tone: 'neutral' | 'info' | 'processing' | 'success' | 'danger';
  action: string;
}> = {
  created: { label: '已创建', tone: 'neutral', action: '查看进度' },
  uploading: { label: '上传中', tone: 'info', action: '查看进度' },
  uploaded: { label: '上传完成', tone: 'info', action: '查看进度' },
  processing: { label: '处理中', tone: 'processing', action: '查看进度' },
  ready_for_review: { label: '待审核', tone: 'info', action: '开始审核' },
  confirmed: { label: '已确认', tone: 'success', action: '导出结果' },
  exported: { label: '已导出', tone: 'success', action: '查看结果' },
  failed: { label: '处理失败', tone: 'danger', action: '查看原因' }
};

export const sessionStatusMeta: Record<CaptureSessionStatus, {
  label: string;
  modalLabel: string;
}> = {
  active: { label: '采集中', modalLabel: '等待手机扫码' },
  expired: { label: '会话已过期', modalLabel: '会话已过期' },
  locked: { label: '已完成采集', modalLabel: '采集已完成' },
  cancelled: { label: '会话已取消', modalLabel: '会话已取消' }
};

export const fieldStatusMeta: Record<FieldStatus, {
  label: string;
  tone: 'neutral' | 'info' | 'success' | 'warning';
}> = {
  unreviewed: { label: '未审核', tone: 'neutral' },
  confirmed: { label: '已确认', tone: 'success' },
  modified: { label: '已修改', tone: 'info' },
  suspicious: { label: '存疑', tone: 'warning' },
  empty: { label: '为空', tone: 'warning' }
};

export const exportStatusMeta: Record<ExportStatus, {
  label: string;
  tone: 'neutral' | 'processing' | 'success' | 'danger';
}> = {
  not_exported: { label: '未导出', tone: 'neutral' },
  exporting: { label: '导出中', tone: 'processing' },
  exported: { label: '已导出', tone: 'success' },
  failed: { label: '导出失败', tone: 'danger' }
};
