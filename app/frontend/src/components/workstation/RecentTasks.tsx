import type { TaskStatus, TaskSummary } from '../../pages/workstation/workstation.types';
import { StatusBadge } from '../common/StatusBadge';

function getTaskActions(status: TaskStatus) {
  if (status === 'ready_for_review') return ['开始审核'];
  if (status === 'processing' || status === 'created' || status === 'uploading' || status === 'uploaded') {
    return ['查看进度'];
  }
  if (status === 'failed') return ['查看原因', '重新处理'];
  if (status === 'confirmed') return ['导出结果'];
  return ['查看结果'];
}

type RecentTasksProps = {
  tasks: TaskSummary[];
};

export function RecentTasks({ tasks }: RecentTasksProps) {
  return (
    <section className="recent-tasks" aria-labelledby="recent-tasks-title">
      <div className="panel-title-row recent-tasks__header">
        <h2 id="recent-tasks-title">最近任务</h2>
        <button className="link-action" type="button">
          全部任务
        </button>
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
                <th>任务编号</th>
                <th>创建时间</th>
                <th>页数</th>
                <th>当前状态</th>
                <th>审核进度</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const progress =
                  task.totalFields > 0 ? Math.round((task.reviewedFields / task.totalFields) * 100) : 0;

                return (
                  <tr key={task.id}>
                    <td className="recent-tasks__id">{task.id}</td>
                    <td>{task.createdAtText}</td>
                    <td>{task.pageCount} 页</td>
                    <td>
                      <StatusBadge status={task.status} />
                    </td>
                    <td>
                      <div className="progress-cell">
                        <span className="progress-bar" aria-hidden="true">
                          <span style={{ width: `${progress}%` }} />
                        </span>
                        <span>
                          {task.reviewedFields}/{task.totalFields}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="task-actions">
                        {getTaskActions(task.status).map((label) => (
                          <button
                            className={task.status === 'failed' ? 'warning-action' : 'secondary-action'}
                            key={label}
                            type="button"
                          >
                            {label}
                          </button>
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
