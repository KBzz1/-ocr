export type CapturePageStatus = 'pending' | 'uploaded' | 'uploading' | 'failed';

export interface CapturePageItem {
  localId: string;
  pageId?: string;
  taskId: string;
  pageNo: number;
  status: CapturePageStatus;
  previewUrl?: string;
  fileName?: string;
  file?: File;
  errorMessage?: string;
}
