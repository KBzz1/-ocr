import { useState, type PointerEvent } from 'react';

import type { CapturePageItem as PageItem } from './mobileCapture.types';
import { CapturePageItem } from './CapturePageItem';

interface CapturePageListProps {
  pages: PageItem[];
  canDelete?: boolean;
  canReorder?: boolean;
  onDelete?: (page: PageItem) => void;
  onReorder?: (fromIndex: number, toIndex: number) => void;
}

export function CapturePageList({
  pages,
  canDelete = false,
  canReorder = false,
  onDelete,
  onReorder
}: CapturePageListProps) {
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);

  function getTargetIndex(clientX: number, clientY: number) {
    const target = document.elementFromPoint(clientX, clientY);
    const item = target?.closest<HTMLElement>('[data-page-index]');
    if (!item?.dataset.pageIndex) return null;
    const index = Number(item.dataset.pageIndex);
    return Number.isInteger(index) ? index : null;
  }

  function clearDrag(event: PointerEvent<HTMLButtonElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    setDraggingIndex(null);
  }

  function handleReorderPointerDown(event: PointerEvent<HTMLButtonElement>, index: number) {
    if (!canReorder || !onReorder || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDraggingIndex(index);
  }

  function handleReorderPointerMove(event: PointerEvent<HTMLOListElement>) {
    if (draggingIndex === null || !onReorder) return;
    const targetIndex = getTargetIndex(event.clientX, event.clientY);
    if (targetIndex === null || targetIndex === draggingIndex) return;
    onReorder(draggingIndex, targetIndex);
    setDraggingIndex(targetIndex);
  }

  return (
    <section className="page-list" aria-label="已上传图片列表">
      <div className="page-list__header">
        <div>
          <h2>图片列表</h2>
        </div>
      </div>
      {pages.length === 0 ? (
        <div className="page-list__empty">
          <div>
            <strong>暂未上传图片</strong>
            <p>上传后可在这里查看页序和文件名</p>
          </div>
        </div>
      ) : (
        <ol className="page-list__items" onPointerMove={handleReorderPointerMove}>
          {pages.map((page, index) => (
            <CapturePageItem
              key={page.localId}
              page={page}
              index={index}
              canDelete={canDelete}
              canReorder={canReorder}
              isDragging={draggingIndex === index}
              onDelete={onDelete}
              onReorderPointerDown={handleReorderPointerDown}
              onReorderPointerEnd={clearDrag}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
