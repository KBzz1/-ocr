import type { QuadPointsByCorner } from '../../components/mobile-capture/QuadSelector';

export type CapturePageStatus = 'uploaded' | 'uploading' | 'failed';

export interface CapturePageItem {
  localId: string;
  pageId?: string;
  pageNo: number;
  status: CapturePageStatus;
  previewUrl?: string;
  file?: File;
  width: number;
  height: number;
  quad: QuadPointsByCorner;
}
