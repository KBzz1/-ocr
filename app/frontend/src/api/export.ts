import { ApiError } from './client';

async function downloadTaskExport(taskId: string, format: 'json' | 'excel') {
  const response = await fetch(
    new URL(`/api/tasks/${encodeURIComponent(taskId)}/export/${format}`, window.location.origin)
      .toString(),
    {
      headers: {
        Accept:
          format === 'json'
            ? 'application/json'
            : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }
    }
  );

  if (!response.ok) {
    throw new ApiError('导出失败', 'EXPORT_FAILED', response.status);
  }

  return response.blob();
}

export function exportTaskJson(taskId: string) {
  return downloadTaskExport(taskId, 'json');
}

export function exportTaskExcel(taskId: string) {
  return downloadTaskExport(taskId, 'excel');
}
