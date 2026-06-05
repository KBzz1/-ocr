import { ApiError } from './client';

async function parseErrorFromBlob(response: Response, fallback: string): Promise<ApiError> {
  try {
    const body = await response.clone().json();
    if (
      body &&
      typeof body === 'object' &&
      'error' in body &&
      body.error &&
      typeof body.error === 'object'
    ) {
      const errObj = body.error as { code?: string; message?: string; details?: Record<string, unknown> };
      return new ApiError(
        typeof errObj.message === 'string' ? errObj.message : fallback,
        typeof errObj.code === 'string' ? errObj.code : 'EXPORT_FAILED',
        response.status,
        typeof errObj.details === 'object' && errObj.details ? errObj.details : {}
      );
    }
  } catch {
    // body 解析失败,使用 fallback
  }
  return new ApiError(fallback, 'EXPORT_FAILED', response.status);
}

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
    throw await parseErrorFromBlob(response, '导出失败');
  }

  return response.blob();
}

export function exportTaskJson(taskId: string) {
  return downloadTaskExport(taskId, 'json');
}

export function exportTaskExcel(taskId: string) {
  return downloadTaskExport(taskId, 'excel');
}

export async function exportTasksBatchZip(taskIds: string[]) {
  const response = await fetch(new URL('/api/tasks/export/batch-zip', window.location.origin).toString(), {
    method: 'POST',
    headers: {
      Accept: 'application/zip',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ task_ids: taskIds })
  });

  if (!response.ok) {
    throw await parseErrorFromBlob(response, '批量导出失败');
  }

  return response.blob();
}
