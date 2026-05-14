import { useEffect, useMemo, useState } from 'react';

import { ApiError } from '../api/client';
import type { CaptureSession } from '../api/captureSessions';
import { createCaptureSession } from '../api/captureSessions';
import { getSystemStatus, type SystemStatus as ApiSystemStatus } from '../api/system';
import { getTasks, type TaskSummary as ApiTaskSummary } from '../api/tasks';
import {
  buildSystemReminders,
  formatRemainingTime,
  sortRecentTasks
} from '../state/workstationStore';
import { MOBILE_SESSION_PREFIX } from './routes';
import { MobileCapturePage } from '../pages/mobile-capture/MobileCapturePage';
import { WorkstationPage } from '../pages/workstation/WorkstationPage';
import type {
  CaptureSessionSummary,
  SystemReminder,
  SystemStatus,
  TaskSummary,
  WorkstationPageData
} from '../pages/workstation/workstation.types';

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

function toSessionSummary(session: CaptureSession | null): CaptureSessionSummary | null {
  if (!session) return null;

  return {
    id: session.session_id,
    status: session.status,
    uploadedPages: session.page_count,
    remainingTimeText: formatRemainingTime(session),
    createdAtText: formatDateTime(session.created_at),
    qrCodeValue: session.qr_code_url
  };
}

function toTaskSummary(task: ApiTaskSummary): TaskSummary {
  const totalFields = task.review_summary?.total_count ?? 0;
  const reviewedFields = task.review_summary?.confirmed_count ?? 0;

  return {
    id: task.task_id,
    createdAtText: formatDateTime(task.created_at),
    pageCount: task.page_count,
    status: task.status,
    reviewedFields,
    totalFields
  };
}

function toReminders(tasks: ApiTaskSummary[], session: CaptureSession | null): SystemReminder[] {
  return buildSystemReminders(tasks, session).map((message, index) => {
    const isFailed = message.includes('处理失败');
    const isExpired = message.includes('过期');
    return {
      id: `reminder-${index}`,
      tone: isFailed || isExpired ? 'warning' : 'info',
      title: isFailed ? '任务处理失败' : isExpired ? '采集会话过期' : '系统提醒',
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

function WorkstationApp() {
  const [systemStatus, setSystemStatus] = useState<ApiSystemStatus | null>(null);
  const [systemError, setSystemError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<ApiTaskSummary[]>([]);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<CaptureSession | null>(null);
  const [isQrOpen, setIsQrOpen] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  useEffect(() => {
    getSystemStatus()
      .then((status) => {
        setSystemStatus(status);
        setSystemError(status.status === 'running' ? null : status.message ?? '系统状态异常');
      })
      .catch((error: unknown) => {
        setSystemStatus(null);
        setSystemError(getErrorMessage(error, '服务无响应'));
      });

    getTasks()
      .then((nextTasks) => {
        setTasks(nextTasks);
        setTaskError(null);
      })
      .catch((error: unknown) => {
        setTasks([]);
        setTaskError(getErrorMessage(error, '任务列表加载失败'));
      });
  }, []);

  const pageData = useMemo<WorkstationPageData>(() => {
    const reminders = toReminders(tasks, currentSession);
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
      currentSession: toSessionSummary(currentSession),
      tasks: sortRecentTasks(tasks).map(toTaskSummary),
      reminders
    };
  }, [currentSession, systemError, systemStatus, taskError, tasks]);

  async function handleCreateSession() {
    setIsCreatingSession(true);
    setCreateError(null);
    setIsQrOpen(false);

    try {
      const session = await createCaptureSession();
      setCurrentSession(session);
      setIsQrOpen(true);
    } catch {
      setCurrentSession(null);
      setCreateError('创建采集会话失败，请重试');
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
      onNewCapture={handleCreateSession}
      onViewQr={() => setIsQrOpen(true)}
      onCloseQr={() => setIsQrOpen(false)}
      onRegenerateQr={handleCreateSession}
    />
  );
}

export function App() {
  if (window.location.pathname.startsWith(MOBILE_SESSION_PREFIX)) {
    return <MobileCapturePage />;
  }

  return <WorkstationApp />;
}
