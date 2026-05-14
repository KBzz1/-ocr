import type { TaskStatus, TaskSummary } from '../../pages/workstation/workstation.types';
import { appRoutes } from '../../app/routes';

const overviewItems: Array<{
  status: TaskStatus;
  title: string;
  hint: string;
}> = [
  { status: 'ready_for_review', title: '待审核', hint: '待人工核验任务' },
  { status: 'processing', title: '处理中', hint: '本地解析进行中' },
  { status: 'failed', title: '处理失败', hint: '可查看原因并重试' },
  { status: 'exported', title: '已导出', hint: '结构化结果已生成' }
];

type TaskOverviewProps = {
  tasks: TaskSummary[];
};

export function TaskOverview({ tasks }: TaskOverviewProps) {
  return (
    <section className="task-overview" aria-label="任务概览">
      {overviewItems.map((item) => {
        const count = tasks.filter((task) => task.status === item.status).length;

        return (
          <a
            className={`overview-card overview-card--${item.status}`}
            href={`${appRoutes.tasks.path}?status=${item.status}`}
            key={item.status}
          >
            <span className="overview-card__label">{item.title}</span>
            <strong>{count}</strong>
            <span className="overview-card__hint">{item.hint}</span>
          </a>
        );
      })}
    </section>
  );
}
