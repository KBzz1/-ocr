import { ApiError, parseErrorBody } from './client';

async function parseBlobError(response: Response, fallbackMessage: string, fallbackCode = 'EXPORT_FAILED'): Promise<ApiError> {
  try {
    const body = (await response.json()) as unknown;
    return parseErrorBody(body, response.status, fallbackMessage, fallbackCode);
  } catch {
    return new ApiError(fallbackMessage, fallbackCode, response.status);
  }
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
    throw await parseBlobError(response, '导出失败');
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
    throw await parseBlobError(response, '批量导出失败');
  }

  return response.blob();
}

export type BatchExcelTemplate = {
  document_type: string;
  label: string;
};

export type BatchExcelSkippedItem = {
  task_id: string;
  reason: string;
};

export type BatchExcelReport = {
  format: 'batch_excel';
  export_id: string;
  filename: string;
  download_url: string;
  candidate_count: number;
  exported_count: number;
  skipped_count: number;
  skipped: BatchExcelSkippedItem[];
};

export async function fetchBatchExcelTemplates(): Promise<BatchExcelTemplate[]> {
  const response = await fetch(new URL('/api/tasks/export/batch-excel/templates', window.location.origin).toString());
  if (!response.ok) {
    throw await parseBlobError(response, '获取导出模板失败');
  }
  const body = (await response.json()) as { data: { templates: BatchExcelTemplate[] } };
  return body.data.templates;
}

export async function exportTasksBatchExcel(documentType: string): Promise<BatchExcelReport> {
  const response = await fetch(new URL('/api/tasks/export/batch-excel', window.location.origin).toString(), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ document_type: documentType })
  });
  if (!response.ok) {
    throw await parseBlobError(response, '批量导出失败');
  }
  const body = (await response.json()) as { data: BatchExcelReport };
  return body.data;
}

export async function downloadBatchExcel(exportId: string): Promise<Blob> {
  const response = await fetch(
    new URL(`/api/tasks/export/batch-excel/${encodeURIComponent(exportId)}`, window.location.origin).toString()
  );
  if (!response.ok) {
    throw await parseBlobError(response, '下载导出文件失败');
  }
  return response.blob();
}
