import { useCallback, useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { deleteTask, getTasks, type TaskStatus, type TaskSummary } from '../../api/tasks';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { TaskList } from '../../components/tasks/TaskList';
import { CaptureQrDialog } from '../../components/workstation/CaptureQrDialog';
import { useSilentPolling } from '../../hooks/useSilentPolling';
import type { TaskUploadSummary } from '../workstation/workstation.types';
import '../../components/tasks/tasks.css';

const TASK_POLL_INTERVAL_MS = 5000;
const visibleTaskFilters: Array<TaskStatus | 'all'> = ['all', 'uploading', 'review', 'done', 'failed'];

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function getInitialStatusFilter(): TaskStatus | 'all' {
  const status = new URLSearchParams(window.location.search).get('status');
  return visibleTaskFilters.includes(status as TaskStatus) ? (status as TaskStatus) : 'all';
}

function areTasksEqual(current: TaskSummary[], next: TaskSummary[]) {
  return JSON.stringify(current) === JSON.stringify(next);
}

function toTaskUploadSummary(task: TaskSummary): TaskUploadSummary {
  return {
    task_id: task.task_id,
    display_name: task.display_name ?? task.task_id,
    status: 'uploading',
    upload_token: task.upload_token ?? '',
    mobile_upload_url: task.mobile_upload_url ?? '',
    id: task.task_id,
    displayName: task.display_name ?? task.task_id,
    uploadedPages: task.page_count,
    createdAtText: '继续上传'
  };
}

export function TasksPage() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [activeFilter, setActiveFilter] = useState<TaskStatus | 'all'>(getInitialStatusFilter);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [retryingTaskId, setRetryingTaskId] = useState<string | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TaskSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [qrTask, setQrTask] = useState<TaskUploadSummary | null>(null);

  const loadTasks = useCallback(async (mode: 'initial' | 'refresh' | 'silent' = 'refresh') => {
    if (mode === 'initial') {
      setIsLoading(true);
    } else if (mode === 'refresh') {
      setIsRefreshing(true);
    }
    if (mode !== 'silent') {
      setError(null);
    }

    try {
      const nextTasks = await getTasks();
      setTasks((currentTasks) => (areTasksEqual(currentTasks, nextTasks) ? currentTasks : nextTasks));
      setError(null);
    } catch (loadError: unknown) {
      if (mode !== 'silent') {
        setError(getErrorMessage(loadError, '任务列表加载失败，请刷新重试'));
      }
    } finally {
      if (mode === 'initial') {
        setIsLoading(false);
      } else if (mode === 'refresh') {
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadTasks('initial');
  }, [loadTasks]);

  useSilentPolling(() => loadTasks('silent'), TASK_POLL_INTERVAL_MS);

  async function handleRefresh() {
    await loadTasks('refresh');
  }

  function handleTaskStatusChange(taskId: string, patch: Partial<TaskSummary> & { status: TaskStatus }) {
    setRetryingTaskId(taskId);
    setTasks((currentTasks) =>
      currentTasks.map((task) =>
        task.task_id === taskId
          ? {
              ...task,
              ...patch,
              error_code: patch.status === 'processing' ? null : patch.error_code ?? task.error_code,
              error_message: patch.status === 'processing' ? null : patch.error_message ?? task.error_message
            }
          : task
      )
    );
    setRetryingTaskId(null);
  }

  function handleDeleteTask(task: TaskSummary) {
    setError(null);
    setDeleteTarget(task);
  }

  function handleCancelDelete() {
    setDeleteTarget(null);
  }

  async function handleConfirmDelete(task: TaskSummary) {
    setDeletingTaskId(task.task_id);
    setDeleteTarget(null);
    try {
      await deleteTask(task.task_id);
      setTasks((currentTasks) => currentTasks.filter((t) => t.task_id !== task.task_id));
      setError(null);
    } catch (deleteError: unknown) {
      setError(getErrorMessage(deleteError, '删除任务失败，请稍后重试'));
    } finally {
      setDeletingTaskId(null);
    }
  }

  function handleFilterChange(filter: TaskStatus | 'all') {
    setActiveFilter(filter);

    const nextUrl = filter === 'all' ? '/tasks' : `/tasks?status=${encodeURIComponent(filter)}`;
    window.history.replaceState({}, '', nextUrl);
  }

  return (
    <WorkstationLayout
      activeRouteId="tasks"
      headerKicker=""
      headerTitle=""
    >
      <main className="tasks-page" aria-label="任务列表页">
        <header className="tasks-page__header">
          <button
            className="tasks-refresh-button"
            disabled={isLoading || isRefreshing}
            type="button"
            onClick={() => void handleRefresh()}
          >
            {isRefreshing ? '刷新中' : '刷新'}
          </button>
        </header>

        <div className="tasks-page__content">
          <p className={error ? 'tasks-page__status tasks-page__error' : 'tasks-page__status'}>
            {error ?? (isLoading ? '正在加载任务' : `共 ${tasks.length} 个任务`)}
          </p>

          <TaskList
            activeFilter={activeFilter}
            retryingTaskId={retryingTaskId}
            deletingTaskId={deletingTaskId}
            deleteTarget={deleteTarget}
            tasks={tasks}
            onFilterChange={handleFilterChange}
            onTaskStatusChange={handleTaskStatusChange}
            onDeleteTask={handleDeleteTask}
            onCancelDelete={handleCancelDelete}
            onConfirmDelete={handleConfirmDelete}
            onViewUploadQr={(task) => setQrTask(toTaskUploadSummary(task))}
          />
        </div>
      </main>

      <CaptureQrDialog
        isOpen={Boolean(qrTask)}
        task={qrTask}
        onClose={() => setQrTask(null)}
      />
    </WorkstationLayout>
  );
}

export const TasksPlaceholder = TasksPage;
