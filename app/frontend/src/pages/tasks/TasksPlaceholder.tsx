import { useCallback, useEffect, useState } from 'react';

import { getApiErrorMessage } from '../../api/client';
import { exportTasksBatchZip } from '../../api/export';
import { deleteTask, getTasks, updateTaskMetadata, type TaskStatus, type TaskSummary } from '../../api/tasks';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { TaskList } from '../../components/tasks/TaskList';
import { CaptureQrDialog } from '../../components/workstation/CaptureQrDialog';
import { useSilentPolling } from '../../hooks/useSilentPolling';
import type { TaskUploadSummary } from '../workstation/workstation.types';
import '../../components/tasks/tasks.css';

const TASK_POLL_INTERVAL_MS = 5000;
const visibleTaskFilters: Array<TaskStatus | 'all'> = ['all', 'uploading', 'review', 'done', 'failed'];
const BATCH_ZIP_FILENAME = 'batch-review-export.zip';

type BatchExportSummary = {
  task_ids: string[];
  exported_at: string;
};

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // 释放 URL,让浏览器 GC;不立即 revoke,留给浏览器完成下载
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  const [rebindingTaskId, setRebindingTaskId] = useState<string | null>(null);
  const [rebindTarget, setRebindTarget] = useState<TaskSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [qrTask, setQrTask] = useState<TaskUploadSummary | null>(null);
  const [selectedTaskIds, setSelectedTaskIds] = useState<ReadonlySet<string>>(() => new Set());
  const [lastBatchExport, setLastBatchExport] = useState<BatchExportSummary | null>(null);
  const [isBatchExporting, setIsBatchExporting] = useState(false);

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
        setError(getApiErrorMessage(loadError, '任务列表加载失败，请刷新重试'));
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
      setError(getApiErrorMessage(deleteError, '删除任务失败，请稍后重试'));
    } finally {
      setDeletingTaskId(null);
    }
  }

  function handleRebindPatient(task: TaskSummary) {
    setError(null);
    setRebindTarget(task);
  }

  function handleCancelRebind() {
    setRebindTarget(null);
    setRebindingTaskId(null);
  }

  async function handleConfirmRebind(task: TaskSummary, patientId: string) {
    setRebindingTaskId(task.task_id);
    try {
      const updated = await updateTaskMetadata(task.task_id, { patient_id: patientId });
      setTasks((currentTasks) =>
        currentTasks.map((t) => (t.task_id === task.task_id ? { ...t, ...updated } : t))
      );
      setError(null);
      setRebindTarget(null);
    } catch (rebindError: unknown) {
      // 错误交给 RebindPatientDialog 内部展示,这里不写全局错误条
      throw rebindError;
    } finally {
      setRebindingTaskId(null);
    }
  }

  function handleFilterChange(filter: TaskStatus | 'all') {
    setActiveFilter(filter);

    const nextUrl = filter === 'all' ? '/tasks' : `/tasks?status=${encodeURIComponent(filter)}`;
    window.history.replaceState({}, '', nextUrl);
  }

  function handleToggleSelected(taskId: string) {
    setSelectedTaskIds((current) => {
      const next = new Set(current);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }

  async function handleBatchExport() {
    if (isBatchExporting || selectedTaskIds.size === 0) return;
    setIsBatchExporting(true);
    const ids = Array.from(selectedTaskIds);
    try {
      const blob = await exportTasksBatchZip(ids);
      triggerBlobDownload(blob, BATCH_ZIP_FILENAME);
      const now = new Date();
      const exportedAt = `${now.getFullYear()}/${String(now.getMonth() + 1).padStart(2, '0')}/${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      setLastBatchExport({ task_ids: ids, exported_at: exportedAt });
      setError(null);
    } catch (batchError: unknown) {
      setError(getApiErrorMessage(batchError, '批量导出失败,请稍后重试'));
    } finally {
      setIsBatchExporting(false);
    }
  }

  function handleDismissBatchSummary() {
    setLastBatchExport(null);
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

          <div className="tasks-batch-toolbar" role="toolbar" aria-label="批量操作">
            <button
              type="button"
              className="tasks-batch-export"
              disabled={selectedTaskIds.size === 0 || isBatchExporting}
              onClick={() => void handleBatchExport()}
            >
              {isBatchExporting ? '导出中' : `批量导出 (${selectedTaskIds.size})`}
            </button>
            {lastBatchExport ? (
              <div className="tasks-batch-summary" role="status">
                <span>
                  已导出 {lastBatchExport.task_ids.length} 个任务 · {lastBatchExport.exported_at}
                </span>
                <button
                  type="button"
                  aria-label="关闭批量导出摘要"
                  className="tasks-batch-summary__close"
                  onClick={handleDismissBatchSummary}
                >
                  ×
                </button>
              </div>
            ) : null}
          </div>

          <TaskList
            activeFilter={activeFilter}
            retryingTaskId={retryingTaskId}
            deletingTaskId={deletingTaskId}
            deleteTarget={deleteTarget}
            rebindingTaskId={rebindingTaskId}
            rebindTarget={rebindTarget}
            selectedTaskIds={selectedTaskIds}
            onToggleSelected={handleToggleSelected}
            tasks={tasks}
            onFilterChange={handleFilterChange}
            onTaskStatusChange={handleTaskStatusChange}
            onDeleteTask={handleDeleteTask}
            onCancelDelete={handleCancelDelete}
            onConfirmDelete={handleConfirmDelete}
            onRebindPatient={handleRebindPatient}
            onCancelRebind={handleCancelRebind}
            onConfirmRebind={handleConfirmRebind}
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
