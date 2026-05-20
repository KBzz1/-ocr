export type CapturePageStatus = 'uploaded' | 'uploading' | 'failed';

export interface CapturePageItem {
  localId: string;
  pageId?: string;
  taskId: string;
  pageNo: number;
  status: CapturePageStatus;
  previewUrl?: string;
  fileName?: string;
  errorMessage?: string;
}
