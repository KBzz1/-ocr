import { useEffect, useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import { getTaskDetail, type TaskDetail } from '../../api/tasks';
import { ExportPanel } from '../../components/export/ExportPanel';
import { UserFriendlyError } from '../../components/errors/UserFriendlyError';

function readTaskIdFromPath() {
  const match = window.location.pathname.match(/^\/tasks\/([^/]+)\/export\/?$/);
  return match ? decodeURIComponent(match[1]) : '';
}

function getErrorCode(error: unknown) {
  return error instanceof ApiError ? error.code : 'UNKNOWN_ERROR';
}

function toExportTask(task: TaskDetail) {
  return {
    task_id: task.task_id,
    status: task.status,
    export_summary: {
      formats: task.export_summary?.formats ?? []
    }
  };
}

export function ExportPlaceholder() {
  const taskId = useMemo(readTaskIdFromPath, []);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  useEffect(() => {
    if (!taskId) {
      setErrorCode('INVALID_TASK_TRANSITION');
      return;
    }

    getTaskDetail(taskId)
      .then((nextTask) => {
        setTask(nextTask);
        setErrorCode(null);
      })
      .catch((error: unknown) => {
        setTask(null);
        setErrorCode(getErrorCode(error));
      });
  }, [taskId]);

  if (errorCode) {
    return (
      <main aria-label="导出页">
        <UserFriendlyError code={errorCode} message="任务导出信息加载失败" />
      </main>
    );
  }

  if (!task) {
    return <main aria-label="导出页">正在加载导出信息</main>;
  }

  return (
    <main aria-label="导出页">
      <ExportPanel task={toExportTask(task)} />
    </main>
  );
}
