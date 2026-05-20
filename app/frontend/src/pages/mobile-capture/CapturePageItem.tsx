import type { CapturePageItem as PageItem } from './mobileCapture.types';

interface CapturePageItemProps {
  page: PageItem;
  index: number;
}

export function CapturePageItem({ page, index }: CapturePageItemProps) {
  const isFailed = page.status === 'failed';
  const isUploading = page.status === 'uploading';

  return (
    <li className="page-item" aria-label={`第 ${index + 1} 页 ${isFailed ? '上传失败' : '已上传'}`}>
      <div className="page-item__thumb">
        {page.previewUrl ? <img src={page.previewUrl} alt={`第 ${index + 1} 页缩略图`} /> : '缩略图'}
      </div>
      <div className="page-item__content">
        <h3>第 {index + 1} 页</h3>
        <span className={`page-item__status is-${page.status}`}>
          {isFailed ? '上传失败' : isUploading ? '上传中' : '已上传'}
        </span>
        {page.fileName ? <span>{page.fileName}</span> : null}
        {page.errorMessage ? <span role="alert">{page.errorMessage}</span> : null}
        {page.pageId ? <span data-page-id={page.pageId} hidden>{page.pageId}</span> : null}
      </div>
    </li>
  );
}
