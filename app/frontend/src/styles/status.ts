import type { CaptureSessionStatus } from '../api/captureSessions';
import type { TaskStatus } from '../api/tasks';

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
  failed: { label: '失败', tone: 'danger', action: '查看原因' }
};

export const sessionStatusMeta: Record<CaptureSessionStatus, {
  label: string;
  modalLabel: string;
}> = {
  active: { label: '会话进行中', modalLabel: '等待手机扫码' },
  expired: { label: '会话已过期', modalLabel: '会话已过期' },
  locked: { label: '采集已完成', modalLabel: '采集已完成' },
  cancelled: { label: '会话已取消', modalLabel: '会话已取消' }
};
