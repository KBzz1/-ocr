import { useEffect, useState } from 'react';

import { ApiError } from '../../api/client';
import { getTasks, type TaskSummary } from '../../api/tasks';
import { WorkstationLayout } from '../../components/layout/WorkstationLayout';
import { demoReviewPayload, demoReviewTaskId } from './demoReviewSample';
import { ReviewPage } from './ReviewPage';

function getErrorMessage(error: unknown, fallback: string) {
  return error instanceof ApiError ? error.message : fallback;
}

function selectReviewTask(tasks: TaskSummary[]) {
  return tasks.find((task) => task.status === 'review') ?? null;
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
        setTask(selectReviewTask(tasks));
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
      <WorkstationLayout activeRouteId="review" headerKicker="人工审核" headerTitle="待审核任务">
        <main className="review-page" aria-label="人工审核页">正在加载待审核任务</main>
      </WorkstationLayout>
    );
  }

  if (!task) {
    if (message) {
      return (
        <WorkstationLayout activeRouteId="review" headerKicker="人工审核" headerTitle="待审核任务">
          <main className="review-page" aria-label="人工审核页">
            <p role="alert" className="review-alert review-alert--danger">{message}</p>
          </main>
        </WorkstationLayout>
      );
    }

    return <ReviewPage taskId={demoReviewTaskId} demoPayload={demoReviewPayload} />;
  }

  return <ReviewPage taskId={task.task_id} />;
}
