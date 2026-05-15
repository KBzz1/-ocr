import { useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { getTasks, type TaskStatus, type TaskSummary } from '../../api/tasks';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { TaskList } from '../../components/tasks/TaskList';
import '../../components/tasks/tasks.css';

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

export function TasksPlaceholder() {
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [activeFilter, setActiveFilter] = useState<TaskStatus | 'all'>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [retryingTaskId, setRetryingTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadTasks(mode: 'initial' | 'refresh' = 'refresh') {
    if (mode === 'initial') {
      setIsLoading(true);
    } else {
      setIsRefreshing(true);
    }
    setError(null);

    try {
      const nextTasks = await getTasks();
      setTasks(nextTasks);
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError, '任务列表加载失败，请刷新重试'));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void loadTasks('initial');
  }, []);

  async function handleRefresh() {
    await loadTasks('refresh');
  }

  function handleTaskStatusChange(taskId: string, status: TaskStatus) {
    setRetryingTaskId(taskId);
    setTasks((currentTasks) =>
      currentTasks.map((task) =>
        task.task_id === taskId
          ? { ...task, status, error_code: null, error_message: null }
          : task
      )
    );
    setRetryingTaskId(null);
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
            tasks={tasks}
            onFilterChange={setActiveFilter}
            onTaskStatusChange={handleTaskStatusChange}
          />
        </div>
      </main>
    </WorkstationLayout>
  );
}
