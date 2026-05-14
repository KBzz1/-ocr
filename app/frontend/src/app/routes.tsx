export type AppRoute = {
  id: 'workstation' | 'mobileCapture' | 'tasks' | 'review' | 'export';
  label: string;
  path: string;
};

export const appRoutes = {
  workstation: { id: 'workstation', label: '工作台总览', path: '/' },
  mobileCapture: { id: 'mobileCapture', label: '手机采集', path: '/mobile/sessions/:sessionId' },
  tasks: { id: 'tasks', label: '任务管理', path: '/tasks' },
  review: { id: 'review', label: '人工审核', path: '/tasks/:taskId/review' },
  export: { id: 'export', label: '导出结果', path: '/tasks/:taskId/export' }
} as const satisfies Record<string, AppRoute>;

export const routes: AppRoute[] = [
  appRoutes.workstation,
  appRoutes.mobileCapture,
  appRoutes.tasks,
  appRoutes.review,
  appRoutes.export
];

function encodeSegment(value: string) {
  return encodeURIComponent(value);
}

export function buildMobileSessionPath(sessionId: string) {
  return `/mobile/sessions/${encodeSegment(sessionId)}`;
}

export function buildReviewPath(taskId: string) {
  return `/tasks/${encodeSegment(taskId)}/review`;
}

export function buildTaskExportPath(taskId: string) {
  return `/tasks/${encodeSegment(taskId)}/export`;
}
