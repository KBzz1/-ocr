import { useMemo, useState } from 'react';

import { ApiError } from '../../api/client';
import { exportTaskExcel, exportTaskJson } from '../../api/export';
import { UserFriendlyError } from '../errors/UserFriendlyError';

type ExportFormat = 'json' | 'excel';
type ExportableStatus = 'confirmed' | 'exported' | string;

export interface ExportTaskView {
  task_id: string;
  status: ExportableStatus;
  review_summary?: {
    unreviewed?: number;
    suspicious?: number;
    empty?: number;
    missing_source?: number;
  };
  export_summary?: {
    formats?: string[];
    last_exported_at?: string | null;
    last_format?: string | null;
  };
}

interface ExportPanelProps {
  task: ExportTaskView;
}

interface LastExport {
  format: ExportFormat;
  exportedAt: string;
}

const formatLabels: Record<ExportFormat, string> = {
  json: 'JSON',
  excel: 'Excel'
};

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '时间未知';

  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
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

function getInitialLastExport(task: ExportTaskView): LastExport | null {
  const lastFormat = task.export_summary?.last_format;
  const lastExportedAt = task.export_summary?.last_exported_at;
  if ((lastFormat === 'json' || lastFormat === 'excel') && lastExportedAt) {
    return { format: lastFormat, exportedAt: lastExportedAt };
  }

  const latestFormat = task.export_summary?.formats?.at(-1);
  if ((latestFormat === 'json' || latestFormat === 'excel') && lastExportedAt) {
    return { format: latestFormat, exportedAt: lastExportedAt };
  }

  return null;
}

function getErrorCode(error: unknown) {
  if (error instanceof ApiError) return error.code;
  return 'EXPORT_FAILED';
}

export function ExportPanel({ task }: ExportPanelProps) {
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<LastExport | null>(() => getInitialLastExport(task));
  const isConfirmed = task.status === 'confirmed' || task.status === 'exported';
  const summary = task.review_summary ?? {};
  const hasReviewIssues =
    (summary.unreviewed ?? 0) > 0 ||
    (summary.suspicious ?? 0) > 0 ||
    (summary.empty ?? 0) > 0 ||
    (summary.missing_source ?? 0) > 0;
  const disabledReason = !isConfirmed ? '请先确认审核' : null;
  const statusText = useMemo(() => {
    if (lastExport) {
      return `最近导出：${formatLabels[lastExport.format]} ${formatDateTime(lastExport.exportedAt)}`;
    }

    return '最近导出：暂无';
  }, [lastExport]);

  async function handleExport(format: ExportFormat) {
    if (!isConfirmed || busyFormat) return;

    setBusyFormat(format);
    setErrorCode(null);

    try {
      const blob =
        format === 'json' ? await exportTaskJson(task.task_id) : await exportTaskExcel(task.task_id);
      triggerDownload(blob, task.task_id, format);
      setLastExport({ format, exportedAt: new Date().toISOString() });
    } catch (error: unknown) {
      setErrorCode(getErrorCode(error));
    } finally {
      setBusyFormat(null);
    }
  }

  return (
    <section aria-label="导出结果">
      <header>
        <h1>导出结果</h1>
        <p>{statusText}</p>
      </header>

      <div aria-label="导出前完整性提示">
        <span>未审核 {summary.unreviewed ?? 0}</span>
        <span>存疑 {summary.suspicious ?? 0}</span>
        <span>为空 {summary.empty ?? 0}</span>
        <span>未定位来源 {summary.missing_source ?? 0}</span>
      </div>

      {hasReviewIssues ? <p>导出前请处理仍需核验的字段。</p> : null}
      {disabledReason ? <p>{disabledReason}</p> : null}
      <p>已审核数据保留在本地任务中</p>

      <div>
        <button
          type="button"
          disabled={!isConfirmed || busyFormat !== null}
          onClick={() => void handleExport('json')}
          title={disabledReason ?? undefined}
        >
          {busyFormat === 'json' ? '导出中...' : '导出 JSON'}
        </button>
        <button
          type="button"
          disabled={!isConfirmed || busyFormat !== null}
          onClick={() => void handleExport('excel')}
          title={disabledReason ?? undefined}
        >
          {busyFormat === 'excel' ? '导出中...' : '导出 Excel'}
        </button>
      </div>

      {errorCode ? <UserFriendlyError code={errorCode} title="导出失败" /> : null}
    </section>
  );
}
