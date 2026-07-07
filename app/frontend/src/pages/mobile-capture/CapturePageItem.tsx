import type { PointerEvent } from 'react';

import { assetUrls } from '../../assets';
import type { CapturePageItem as PageItem } from './mobileCapture.types';

interface CapturePageItemProps {
  page: PageItem;
  index: number;
  canDelete?: boolean;
  canReorder?: boolean;
  isDragging?: boolean;
  onDelete?: (page: PageItem) => void;
  onReorderPointerDown?: (event: PointerEvent<HTMLButtonElement>, index: number) => void;
  onReorderPointerEnd?: (event: PointerEvent<HTMLButtonElement>) => void;
}

function getStatusText(page: PageItem) {
  if (page.status === 'failed') return '上传失败';
  if (page.status === 'uploading') return '上传中';
  if (page.status === 'pending') return '待上传';
  return '已上传';
}

export function CapturePageItem({
  page,
  index,
  canDelete = false,
  canReorder = false,
  isDragging = false,
  onDelete,
  onReorderPointerDown,
  onReorderPointerEnd
}: CapturePageItemProps) {
  const statusText = getStatusText(page);
  const className = [
    'page-item',
    canReorder ? 'is-reorderable' : '',
    canDelete ? 'is-deletable' : '',
    isDragging ? 'is-dragging' : ''
  ].filter(Boolean).join(' ');

  return (
    <li className={className} aria-label={`第 ${index + 1} 页 ${statusText}`} data-page-index={index}>
      {canReorder ? (
        <button
          className="page-item__drag-handle"
          type="button"
          aria-label={`拖动第 ${index + 1} 页调整顺序`}
          onPointerDown={(event) => onReorderPointerDown?.(event, index)}
          onPointerUp={onReorderPointerEnd}
          onPointerCancel={onReorderPointerEnd}
          onLostPointerCapture={onReorderPointerEnd}
        >
          <img src={assetUrls.icons.actions.dragSort} alt="" aria-hidden="true" />
        </button>
      ) : null}
      <div className="page-item__thumb">
        {page.previewUrl ? <img src={page.previewUrl} alt={`第 ${index + 1} 页缩略图`} /> : '缩略图'}
      </div>
      <div className="page-item__content">
        <div className="page-item__title-row">
          <h3>第 {index + 1} 页</h3>
        </div>
        <span className={`page-item__status is-${page.status}`}>
          {statusText}
        </span>
        {page.fileName ? <span className="page-item__filename">{page.fileName}</span> : null}
        {page.errorMessage ? <span className="page-item__error" role="alert">{page.errorMessage}</span> : null}
        {page.pageId ? <span data-page-id={page.pageId} hidden>{page.pageId}</span> : null}
      </div>
      {canDelete ? (
        <button
          className="page-item__delete"
          type="button"
          onClick={() => onDelete?.(page)}
          aria-label={`删除第 ${index + 1} 页`}
        >
          <img src={assetUrls.icons.actions.delete} alt="" aria-hidden="true" />
        </button>
      ) : null}
    </li>
  );
}
