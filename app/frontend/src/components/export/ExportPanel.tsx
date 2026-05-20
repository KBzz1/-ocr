import { useState } from 'react';

import { ApiError } from '../../api/client';
import { exportTaskExcel, exportTaskJson } from '../../api/export';
import type { TaskStatus } from '../../api/tasks';
import { UserFriendlyError } from '../errors/UserFriendlyError';

type ExportFormat = 'json' | 'excel';

export interface ExportTaskView {
  task_id: string;
  status: TaskStatus;
  export_summary?: {
    formats?: string[];
    last_exported_at?: string | null;
  };
}

interface ExportPanelProps {
  task: ExportTaskView;
}

function toFileName(taskId: string, format: ExportFormat) {
  const safeTaskId = taskId.replace(/[^A-Za-z0-9_-]/g, '_') || 'task';
  return `${safeTaskId}.${format === 'json' ? 'json' : 'xlsx'}`;
}

function triggerDownload(blob: Blob, taskId: string, format: ExportFormat) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = toFileName(taskId, format);
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function getErrorCode(error: unknown) {
  if (error instanceof ApiError) return error.code;
  return 'EXPORT_FAILED';
}

export function ExportPanel({ task }: ExportPanelProps) {
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [lastExportText, setLastExportText] = useState(
    task.export_summary?.last_exported_at ? `最近导出：${task.export_summary.last_exported_at}` : '最近导出：暂无'
  );
  const canExport = task.status === 'review' || task.status === 'done';

  async function handleExport(format: ExportFormat) {
    if (!canExport || busyFormat) return;

    setBusyFormat(format);
    setErrorCode(null);
    try {
      const blob = format === 'json' ? await exportTaskJson(task.task_id) : await exportTaskExcel(task.task_id);
      triggerDownload(blob, task.task_id, format);
      setLastExportText(`最近导出：${format === 'json' ? 'JSON' : 'Excel'}`);
    } catch (error: unknown) {
      setErrorCode(getErrorCode(error));
    } finally {
      setBusyFormat(null);
    }
  }

  return (
    <section aria-label="导出结果">
      <header>
        <h2>导出结果</h2>
        <p>{lastExportText}</p>
      </header>
      {!canExport ? <p>待审核或已完成任务才可导出</p> : null}
      <div>
        <button
          type="button"
          disabled={!canExport || busyFormat !== null}
          onClick={() => void handleExport('json')}
        >
          {busyFormat === 'json' ? '导出中...' : '导出 JSON'}
        </button>
        <button
          type="button"
          disabled={!canExport || busyFormat !== null}
          onClick={() => void handleExport('excel')}
        >
          {busyFormat === 'excel' ? '导出中...' : '导出 Excel'}
        </button>
      </div>
      {errorCode ? <UserFriendlyError code={errorCode} title="导出失败" /> : null}
    </section>
  );
}
