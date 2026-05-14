import { useState } from 'react';
import type { CapturePageItem as PageItem } from './mobileCapture.types';
import { CapturePageItem } from './CapturePageItem';

interface CapturePageListProps {
  pages: PageItem[];
  isReadOnly: boolean;
  onDelete: (page: PageItem) => void;
  onRetry: (page: PageItem) => void;
  onSupplement: (page: PageItem) => void;
  onRequad: (page: PageItem) => void;
  onReorder: (fromIndex: number, toIndex: number) => void;
}

export function CapturePageList({
  pages,
  isReadOnly,
  onDelete,
  onRetry,
  onSupplement,
  onRequad,
  onReorder
}: CapturePageListProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const dragDisabled = pages.some((page) => page.status !== 'uploaded');

  function handleDragOver(event: React.DragEvent, index: number) {
    if (dragIndex === null || dragIndex === index || dragDisabled) return;
    event.preventDefault();
  }

  function handleDrop(index: number) {
    if (dragIndex === null || dragIndex === index || dragDisabled) return;
    onReorder(dragIndex, index);
    setDragIndex(null);
  }

  return (
    <section className="page-list" aria-label="已采集页面列表">
      <div className="page-list__header">
        <div>
          <h2>页面列表</h2>
          <p>长按拖拽调整顺序</p>
        </div>
      </div>
      {pages.length === 0 ? (
        <div className="page-list__empty">
          <div>
            <strong>暂未上传页面</strong>
            <p>上传后可在这里查看、删除或调整顺序</p>
          </div>
        </div>
      ) : (
        <ol className="page-list__items">
          {pages.map((page, index) => (
            <CapturePageItem
              key={page.localId}
              page={page}
              index={index}
              isReadOnly={isReadOnly}
              dragDisabled={dragDisabled}
              onDelete={onDelete}
              onRetry={onRetry}
              onSupplement={onSupplement}
              onRequad={onRequad}
              onDragStart={setDragIndex}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
