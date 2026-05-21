import { useCallback, useEffect, useMemo, useState } from 'react';

import { ApiError } from '../api/client';
import { getSystemStatus, type SystemStatus as ApiSystemStatus } from '../api/system';
import { createTask, getTasks, type CreateTaskResult, type TaskSummary as ApiTaskSummary } from '../api/tasks';
import {
  buildSystemReminders,
  sortRecentTasks
} from '../state/workstationStore';
import { MOBILE_UPLOAD_PREFIX } from './routes';
import { ExportPlaceholder } from '../pages/export/ExportPlaceholder';
import { MobileCapturePage } from '../pages/mobile-capture/MobileCapturePage';
import { ReviewEntryPage } from '../pages/review/ReviewEntryPage';
import { ReviewPage } from '../pages/review/ReviewPage';
import { TasksPage } from '../pages/tasks/TasksPage';
import { WorkstationPage } from '../pages/workstation/WorkstationPage';
import { useSilentPolling } from '../hooks/useSilentPolling';
import type {
  SystemReminder,
  SystemStatus,
  TaskUploadSummary,
  TaskSummary,
  WorkstationPageData
} from '../pages/workstation/workstation.types';

const DASHBOARD_POLL_INTERVAL_MS = 5000;

function toSystemStatus(status: ApiSystemStatus | null, error: string | null): SystemStatus {
  if (error) {
    return {
      startup: 'error',
      message: error,
      items: [
        { id: 'startup', label: '启动状态', value: error, tone: 'danger' },
        { id: 'offline', label: '运行方式', value: '离线运行', tone: 'neutral' },
        { id: 'mobile', label: '手机采集', value: '暂不可用', tone: 'warning' }
      ]
    };
  }

  if (status?.status === 'running') {
    return {
      startup: 'running',
      items: [
        { id: 'startup', label: '启动状态', value: '系统已启动', tone: 'success' },
        { id: 'offline', label: '运行方式', value: '离线运行', tone: 'success' },
        { id: 'mobile', label: '手机采集', value: '手机采集可用', tone: 'success' }
      ]
    };
  }

  return {
    startup: 'offline',
    items: [
      { id: 'startup', label: '启动状态', value: '正在检查服务', tone: 'neutral' },
      { id: 'offline', label: '运行方式', value: '离线运行', tone: 'neutral' },
      { id: 'mobile', label: '手机采集', value: '等待服务就绪', tone: 'neutral' }
    ]
  };
}

function toTaskUploadSummary(task: CreateTaskResult | null): TaskUploadSummary | null {
  if (!task) return null;

  return {
    ...task,
    id: task.task_id,
    uploadedPages: 0,
    createdAtText: '刚刚'
  };
}

function toTaskSummary(task: ApiTaskSummary): TaskSummary {
  const totalFields = task.review_summary?.total_count ?? 0;
  const reviewedFields = task.review_summary?.confirmed_count ?? 0;
  const errorReason =
    task.status === 'failed'
      ? task.error_message || task.error_code || '处理失败，请重新处理'
      : null;

  return {
    id: task.task_id,
    createdAtText: formatDateTime(task.created_at),
    pageCount: task.page_count,
    status: task.status,
    reviewedFields,
    totalFields,
    errorReason
  };
}

function toReminders(tasks: ApiTaskSummary[]): SystemReminder[] {
  return buildSystemReminders(tasks).map((message, index) => {
    const isFailed = message.includes('处理失败');
    return {
      id: `reminder-${index}`,
      tone: isFailed ? 'warning' : 'info',
      title: isFailed ? '任务处理失败' : '系统提醒',
      timeText: '刚刚',
      message,
      actionLabel: isFailed ? '查看原因' : undefined
    };
  });
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function areTasksEqual(current: ApiTaskSummary[], next: ApiTaskSummary[]) {
  return JSON.stringify(current) === JSON.stringify(next);
}

function areSystemStatusesEqual(current: ApiSystemStatus | null, next: ApiSystemStatus | null) {
  return JSON.stringify(current) === JSON.stringify(next);
}

function useCurrentPathname() {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    function updatePathname() {
      setPathname(window.location.pathname);
    }

    window.addEventListener('popstate', updatePathname);
    return () => window.removeEventListener('popstate', updatePathname);
  }, []);

  return pathname;
}

function WorkstationApp() {
  const [systemStatus, setSystemStatus] = useState<ApiSystemStatus | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<ApiTaskSummary[]>([]);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [currentTask, setCurrentTask] = useState<CreateTaskResult | null>(null);
  const [isQrOpen, setIsQrOpen] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isRetryingSystem, setIsRetryingSystem] = useState(false);

  const loadDashboard = useCallback(async (mode: 'initial' | 'manual' | 'silent' = 'manual') => {
    const [statusResult, tasksResult] = await Promise.allSettled([
      getSystemStatus(),
      getTasks()
    ]);

    if (statusResult.status === 'fulfilled') {
      const status = statusResult.value;
      setSystemStatus((currentStatus) => (areSystemStatusesEqual(currentStatus, status) ? currentStatus : status));
      setSystemError(status.status === 'running' ? null : status.message ?? '系统状态异常');
    } else {
      if (mode !== 'silent') {
        setSystemStatus(null);
        setSystemError(getErrorMessage(statusResult.reason, '服务无响应'));
      }
    }

    if (tasksResult.status === 'fulfilled') {
      setTasks((currentTasks) => (areTasksEqual(currentTasks, tasksResult.value) ? currentTasks : tasksResult.value));
      setTaskError(null);
    } else {
      if (mode !== 'silent') {
        setTasks([]);
        setTaskError(getErrorMessage(tasksResult.reason, '任务列表加载失败'));
      }
    }
  }, []);

  useEffect(() => {
    void loadDashboard('initial');
  }, [loadDashboard]);

  useSilentPolling(() => loadDashboard('silent'), DASHBOARD_POLL_INTERVAL_MS);

  async function handleRetrySystem() {
    setIsRetryingSystem(true);
    await loadDashboard('manual');
    setIsRetryingSystem(false);
  }

  const pageData = useMemo<WorkstationPageData>(() => {
    const reminders = toReminders(tasks);
    if (taskError) {
      reminders.unshift({
        id: 'task-error',
        tone: 'warning',
        title: '任务列表加载失败',
        timeText: '刚刚',
        message: taskError
      });
    }

    return {
      systemStatus: toSystemStatus(systemStatus, systemError),
      currentTask: toTaskUploadSummary(currentTask),
      tasks: sortRecentTasks(tasks).map(toTaskSummary),
      reminders
    };
  }, [currentTask, systemError, systemStatus, taskError, tasks]);

  async function handleCreateSession() {
    setIsCreatingSession(true);
    setCreateError(null);
    setIsQrOpen(false);

    try {
      const task = await createTask();
      setCurrentTask(task);
      setIsQrOpen(true);
      await loadDashboard('manual');
    } catch (error) {
      setCurrentTask(null);
      setCreateError(
        error instanceof ApiError && error.status === 405
          ? '当前后端版本不支持新建任务，请重启服务后再试'
          : '创建任务失败，请重试'
      );
    } finally {
      setIsCreatingSession(false);
    }
  }

  return (
    <WorkstationPage
      data={pageData}
      isQrOpen={isQrOpen}
      isCreatingSession={isCreatingSession}
      createError={createError}
      isSystemReady={systemStatus?.status === 'running' && !systemError}
      isRetryingSystem={isRetryingSystem}
      onRetrySystem={handleRetrySystem}
      onNewCapture={handleCreateSession}
      onViewQr={() => setIsQrOpen(true)}
      onCloseQr={() => setIsQrOpen(false)}
      lanAddresses={systemStatus?.lan_addresses ?? []}
    />
  );
}

export function App() {
  const pathname = useCurrentPathname();

  if (pathname.startsWith(MOBILE_UPLOAD_PREFIX)) {
    return <MobileCapturePage />;
  }

  if (pathname === '/review' || pathname === '/review/') {
    return <ReviewEntryPage />;
  }

  if (/^\/tasks\/[^/]+\/review\/?$/.test(pathname)) {
    return <ReviewPage />;
  }

  if (/^\/tasks\/[^/]+\/export\/?$/.test(pathname)) {
    return <ExportPlaceholder />;
  }

  if (pathname === '/tasks' || pathname === '/tasks/') {
    return <TasksPage />;
  }

  return <WorkstationApp />;
}
