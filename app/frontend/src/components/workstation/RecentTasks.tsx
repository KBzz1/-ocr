import type { TaskSummary } from '../../pages/workstation/workstation.types';
import { appRoutes, buildReviewPath, buildTaskExportPath } from '../../app/routes';
import { StatusBadge } from '../common/StatusBadge';

function getTaskActions(task: TaskSummary) {
  const taskListPath = appRoutes.tasks.path;
  const failedPath = `${taskListPath}?status=failed`;

  if (task.status === 'review') return [{ label: '进入审核', href: buildReviewPath(task.id) }];
  if (task.status === 'processing' || task.status === 'uploading') {
    return [{ label: '查看进度', href: taskListPath }];
  }
  if (task.status === 'failed') {
    return [
      { label: '查看原因', href: failedPath },
      { label: '重新处理', href: failedPath }
    ];
  }
  return [{ label: '导出', href: buildTaskExportPath(task.id) }];
}

type RecentTasksProps = {
  tasks: TaskSummary[];
};

export function RecentTasks({ tasks }: RecentTasksProps) {
  return (
    <section className="recent-tasks" aria-labelledby="recent-tasks-title">
      <div className="panel-title-row recent-tasks__header">
        <h2 id="recent-tasks-title">最近任务</h2>
        <a className="link-action" href={appRoutes.tasks.path}>
          全部任务
        </a>
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state">
          <strong>暂无任务</strong>
          <span>新建采集后，任务会显示在这里。</span>
        </div>
      ) : (
        <div className="recent-tasks__table-wrap">
          <table className="recent-tasks__table">
            <thead>
              <tr>
                <th>任务名称</th>
                <th>创建时间</th>
                <th>页数</th>
                <th>当前状态</th>
                <th>审核进度</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const isProcessing = task.status === 'processing';
                const progress = isProcessing
                  ? Math.max(0, Math.min(100, task.processingProgress ?? 10))
                  : task.totalFields > 0
                    ? Math.round((task.reviewedFields / task.totalFields) * 100)
                    : 0;

                return (
                  <tr key={task.id}>
                    <td className="recent-tasks__id">{task.displayName}</td>
                    <td>{task.createdAtText}</td>
                    <td>{task.pageCount} 页</td>
                    <td>
                      {isProcessing ? null : <StatusBadge status={task.status} />}
                    </td>
                    <td>
                      <div className="progress-cell">
                        <span className="progress-bar" aria-hidden="true">
                          <span style={{ width: `${progress}%` }} />
                        </span>
                        <span>
                          {isProcessing ? (task.processingLabel ?? '等待处理') : `${task.reviewedFields}/${task.totalFields}`}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="task-actions">
                        {getTaskActions(task).map((action) => (
                          <a
                            className={task.status === 'failed' ? 'warning-action' : 'secondary-action'}
                            href={action.href}
                            key={action.label}
                          >
                            {action.label}
                          </a>
                        ))}
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
