import { useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { getTasks, type TaskSummary } from '../../api/tasks';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { ReviewPage } from './ReviewPage';

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function selectTaskForDetail(tasks: TaskSummary[]) {
  return tasks.find((task) => task.status === 'review') ?? tasks[0] ?? null;
}

export function ReviewEntryPage() {
  const [task, setTask] = useState<TaskSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    getTasks()
      .then((tasks) => {
        if (!isCurrent) return;
        setTask(selectTaskForDetail(tasks));
        setMessage(null);
      })
      .catch((error: unknown) => {
        if (!isCurrent) return;
        setMessage(getErrorMessage(error, '待审核任务加载失败，请稍后重试'));
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  if (isLoading) {
    return (
      <WorkstationLayout activeRouteId="review" headerKicker="任务详情" headerTitle="任务详情">
        <main className="review-page" aria-label="任务详情页">正在加载任务信息</main>
      </WorkstationLayout>
    );
  }

  if (!task) {
    if (message) {
      return (
        <WorkstationLayout activeRouteId="review" headerKicker="任务详情" headerTitle="任务详情">
          <main className="review-page" aria-label="任务详情页">
            <p role="alert" className="review-alert review-alert--danger">{message}</p>
          </main>
        </WorkstationLayout>
      );
    }

    return (
      <WorkstationLayout activeRouteId="review" headerKicker="任务详情" headerTitle="任务详情">
        <main className="review-page" aria-label="任务详情页">
          <section className="review-readonly-panel" aria-label="任务当前状态">
            <h2>暂无任务可查看</h2>
            <p>当前没有可打开的真实任务，请先新建采集或在任务管理中选择任务。</p>
          </section>
        </main>
      </WorkstationLayout>
    );
  }

  return <ReviewPage taskId={task.task_id} />;
}
