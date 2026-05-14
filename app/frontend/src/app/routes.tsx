export type AppRoute = {
  id: 'workstation' | 'mobile-capture' | 'tasks' | 'review' | 'exports';
  label: string;
  path: string;
};

export const routes: AppRoute[] = [
  { id: 'workstation', label: '工作台总览', path: '/' },
  { id: 'mobile-capture', label: '手机采集', path: '/capture' },
  { id: 'tasks', label: '任务管理', path: '/tasks' },
  { id: 'review', label: '人工审核', path: '/review' },
  { id: 'exports', label: '导出记录', path: '/exports' }
];
