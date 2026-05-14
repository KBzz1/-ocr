import type { CapturePageItem as PageItem } from './mobileCapture.types';

interface CapturePageItemProps {
  page: PageItem;
  index: number;
  isReadOnly: boolean;
  dragDisabled: boolean;
  onDelete: (page: PageItem) => void;
  onRetry: (page: PageItem) => void;
  onSupplement: (page: PageItem) => void;
  onRequad: (page: PageItem) => void;
  onDragStart: (index: number) => void;
  onDragOver: (event: React.DragEvent, index: number) => void;
  onDrop: (index: number) => void;
}

export function CapturePageItem({
  page,
  index,
  isReadOnly,
  dragDisabled,
  onDelete,
  onRetry,
  onSupplement,
  onRequad,
  onDragStart,
  onDragOver,
  onDrop
}: CapturePageItemProps) {
  const isFailed = page.status === 'failed';
  const isUploading = page.status === 'uploading';

  return (
    <li
      className="page-item"
      aria-label={`第 ${index + 1} 页 ${isFailed ? '上传失败' : '已上传'}`}
      onDragOver={(event) => onDragOver(event, index)}
      onDrop={() => onDrop(index)}
    >
      <button
        className="page-item__drag"
        type="button"
        aria-label={`拖拽第 ${index + 1} 页`}
        draggable={!isReadOnly && !dragDisabled}
        disabled={isReadOnly || dragDisabled}
        onDragStart={() => onDragStart(index)}
      >
        ⋮⋮
      </button>
      <div className="page-item__thumb">
        {page.previewUrl ? <img src={page.previewUrl} alt={`第 ${index + 1} 页缩略图`} /> : '缩略图'}
      </div>
      <div className="page-item__content">
        <h3>第 {index + 1} 页</h3>
        <span className={`page-item__status is-${page.status}`}>
          {isFailed ? '上传失败' : isUploading ? '上传中' : '已上传'}
        </span>
        {page.pageId ? <span hidden>{page.pageId}</span> : null}
        {!isReadOnly ? (
          <div className="page-item__actions">
            {isFailed ? (
              <>
                <button className="page-action is-primary" type="button" onClick={() => onRetry(page)} aria-label={`重试第 ${index + 1} 页`}>
                  重试
                </button>
                <button className="page-action is-delete" type="button" onClick={() => onDelete(page)} aria-label={`删除第 ${index + 1} 页`}>
                  删除
                </button>
              </>
            ) : isUploading ? null : (
              <>
                <button className="page-action is-blue" type="button" onClick={() => onSupplement(page)} aria-label={`补拍第 ${index + 1} 页`}>
                  补拍
                </button>
                <button className="page-action is-orange" type="button" onClick={() => onRequad(page)} aria-label={`重新框选第 ${index + 1} 页`}>
                  重新框选
                </button>
                <button className="page-action is-delete" type="button" onClick={() => onDelete(page)} aria-label={`删除第 ${index + 1} 页`}>
                  删除
                </button>
              </>
            )}
          </div>
        ) : null}
      </div>
    </li>
  );
}
