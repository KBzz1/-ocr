import type { TaskStatus, TaskSummary } from '../../api/tasks';
import { cancelTaskProcessing, retryTaskProcessing } from '../../api/tasks';
import { buildReviewPath, buildTaskExportPath } from '../../app/routes';
import { taskStatusMeta } from '../../styles/status';

const statusFilters: Array<{ label: string; value: TaskStatus | 'all' }> = [
  { label: '全部', value: 'all' },
  { label: taskStatusMeta.uploading.label, value: 'uploading' },
  { label: taskStatusMeta.review.label, value: 'review' },
  { label: taskStatusMeta.done.label, value: 'done' },
  { label: taskStatusMeta.failed.label, value: 'failed' }
];

const reviewStatusLabels: Record<string, string> = {
  unreviewed: '未审核',
  confirmed: '已确认',
  modified: '已修改'
};

type TaskListProps = {
  tasks: TaskSummary[];
  activeFilter: TaskStatus | 'all';
  retryingTaskId: string | null;
  onFilterChange: (filter: TaskStatus | 'all') => void;
  onTaskStatusChange: (taskId: string, patch: Partial<TaskSummary> & { status: TaskStatus }) => void;
  onViewUploadQr?: (task: TaskSummary) => void;
};

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  return `${year}/${month}/${day} ${hour}:${minute}`;
}

function getReviewLabel(task: TaskSummary) {
  const status = task.review_summary?.status;
  if (status && reviewStatusLabels[status]) return reviewStatusLabels[status];

  const confirmed = task.review_summary?.confirmed_count ?? 0;
  const total = task.review_summary?.total_count ?? 0;
  if (total > 0 && confirmed >= total) return '已确认';
  return '未审核';
}

function getErrorSummary(task: TaskSummary) {
  if (task.status !== 'failed') return '';
  return task.error_message || task.error_code || '处理失败，请重新处理';
}

function getProcessingProgress(task: TaskSummary) {
  const summary = task.processing_summary;
  if (!summary) {
    return { label: '等待处理', progress: 10 };
  }

  return {
    label: summary.label || '等待处理',
    progress: Math.max(0, Math.min(100, summary.progress_percent))
  };
}

export function TaskList({
  tasks,
  activeFilter,
  retryingTaskId,
  onFilterChange,
  onTaskStatusChange,
  onViewUploadQr
}: TaskListProps) {
  const visibleTasks =
    activeFilter === 'all' ? tasks : tasks.filter((task) => task.status === activeFilter);

  async function handleRetry(taskId: string) {
    const result = await retryTaskProcessing(taskId);
    onTaskStatusChange(taskId, result);
  }

  async function handleCancelProcessing(taskId: string) {
    const result = await cancelTaskProcessing(taskId);
    onTaskStatusChange(taskId, result);
  }

  return (
    <section className="task-list-panel" aria-labelledby="task-list-title">
      <div className="task-list-panel__toolbar">
        <h2 id="task-list-title">任务管理</h2>

        <div className="task-list-filters" aria-label="任务状态筛选">
          {statusFilters.map((filter) => (
            <button
              aria-pressed={activeFilter === filter.value}
              className={activeFilter === filter.value ? 'task-list-filter is-active' : 'task-list-filter'}
              key={filter.value}
              type="button"
              onClick={() => onFilterChange(filter.value)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {visibleTasks.length === 0 ? (
        <div className="task-list-empty">
          <strong>暂无任务</strong>
          <span>新建采集后，任务会显示在这里。</span>
        </div>
      ) : (
        <div className="task-list-table-wrap">
          <table className="task-list-table" aria-label="任务列表">
            <thead>
              <tr>
                <th>任务编号</th>
                <th>创建时间</th>
                <th>页数</th>
                <th>处理状态</th>
                <th>审核状态</th>
                <th>失败原因</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleTasks.map((task) => {
                const status = taskStatusMeta[task.status];
                const errorSummary = getErrorSummary(task);
                const isRetrying = retryingTaskId === task.task_id;
                const processingProgress = task.status === 'processing' ? getProcessingProgress(task) : null;

                return (
                  <tr key={task.task_id}>
                    <td className="task-list-table__id">{task.task_id}</td>
                    <td>{formatDateTime(task.created_at)}</td>
                    <td>{task.page_count} 页</td>
                    <td>
                      <div className="task-status-cell">
                        {task.status === 'processing' ? null : (
                          <span className={`task-status task-status--${status.tone}`}>
                            {status.label}
                          </span>
                        )}
                        {task.status === 'processing' ? (
                          <div className="task-processing-progress">
                            <span className="task-processing-progress__label">{processingProgress?.label}</span>
                            <span
                              className="task-processing-progress__bar"
                              role="progressbar"
                              aria-label="处理进度"
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-valuenow={processingProgress?.progress}
                            >
                              <span style={{ width: `${processingProgress?.progress ?? 0}%` }} />
                            </span>
                          </div>
                        ) : null}
                      </div>
                    </td>
                    <td>{getReviewLabel(task)}</td>
                    <td>
                      {errorSummary ? (
                        <details className="task-error-details">
                          <summary>{errorSummary}</summary>
                          <p>{errorSummary}</p>
                        </details>
                      ) : (
                        <span className="task-list-muted">无</span>
                      )}
                    </td>
                    <td>
                      <div className="task-list-actions">
                        {task.status === 'uploading' ? (
                          <button
                            className="task-list-action"
                            disabled={!task.mobile_upload_url || !onViewUploadQr}
                            type="button"
                            onClick={() => onViewUploadQr?.(task)}
                          >
                            查看二维码
                          </button>
                        ) : null}
                        {task.status === 'processing' ? (
                          <button
                            className="task-list-action task-list-action--warning"
                            disabled={isRetrying}
                            type="button"
                            onClick={() => void handleCancelProcessing(task.task_id)}
                          >
                            取消处理
                          </button>
                        ) : null}
                        {task.status === 'review' ? (
                          <a className="task-list-action" href={buildReviewPath(task.task_id)}>
                            进入审核
                          </a>
                        ) : null}
                        {task.status === 'review' || task.status === 'done' ? (
                          <a className="task-list-action" href={buildTaskExportPath(task.task_id)}>
                            导出
                          </a>
                        ) : null}
                        {task.status === 'done' ? (
                          <a className="task-list-action" href={buildReviewPath(task.task_id)}>
                            查看结果
                          </a>
                        ) : null}
                        {task.status === 'failed' ? (
                          <button
                            className="task-list-action task-list-action--warning"
                            disabled={isRetrying}
                            type="button"
                            onClick={() => void handleRetry(task.task_id)}
                          >
                            {isRetrying ? '提交中' : '重新处理'}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
