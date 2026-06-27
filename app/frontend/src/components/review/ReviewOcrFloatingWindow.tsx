import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ReviewSourcePanel, type SourceMessage } from './ReviewSourcePanel';

type WindowRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type ViewportSize = {
  width: number;
  height: number;
};

type ReviewOcrFloatingWindowProps = {
  text: string;
  sourceMessage: SourceMessage | null;
  selectedFieldLabel?: string;
  onClose: () => void;
  initialRect?: WindowRect;
  viewportSize?: ViewportSize;
};

const DEFAULT_RECT: WindowRect = { left: 340, top: 140, width: 520, height: 340 };
const MIN_WIDTH = 360;
const MIN_HEIGHT = 240;

function getViewportSize(override?: ViewportSize): ViewportSize {
  if (override) return override;
  if (typeof window === 'undefined') return { width: 1280, height: 800 };
  return {
    width: window.innerWidth || 1280,
    height: window.innerHeight || 800,
  };
}

function clampRect(rect: WindowRect, viewport: ViewportSize): WindowRect {
  const width = Math.min(Math.max(rect.width, MIN_WIDTH), viewport.width);
  const height = Math.min(Math.max(rect.height, MIN_HEIGHT), viewport.height);
  const maxLeft = Math.max(0, viewport.width - width);
  const maxTop = Math.max(0, viewport.height - height);
  return {
    left: Math.min(Math.max(rect.left, 0), maxLeft),
    top: Math.min(Math.max(rect.top, 0), maxTop),
    width,
    height,
  };
}

export function ReviewOcrFloatingWindow({
  text,
  sourceMessage,
  selectedFieldLabel,
  onClose,
  initialRect = DEFAULT_RECT,
  viewportSize,
}: ReviewOcrFloatingWindowProps) {
  const viewport = useMemo(() => getViewportSize(viewportSize), [viewportSize]);
  const [rect, setRect] = useState<WindowRect>(() => clampRect(initialRect, viewport));
  const dragRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);
  const [returnToHighlight, setReturnToHighlight] = useState<(() => void) | null>(null);

  const title = selectedFieldLabel ? `${selectedFieldLabel} OCR 原文` : 'OCR 原文';

  const resetRect = useCallback(() => {
    setRect(clampRect(DEFAULT_RECT, getViewportSize(viewportSize)));
  }, [viewportSize]);

  useEffect(() => {
    function handleMouseMove(event: MouseEvent) {
      if (dragRef.current) {
        const { startX, startY, startRect } = dragRef.current;
        setRect(clampRect({
          ...startRect,
          left: startRect.left + event.clientX - startX,
          top: startRect.top + event.clientY - startY,
        }, getViewportSize(viewportSize)));
      }

      if (resizeRef.current) {
        const { startX, startY, startRect } = resizeRef.current;
        setRect(clampRect({
          ...startRect,
          width: startRect.width + event.clientX - startX,
          height: startRect.height + event.clientY - startY,
        }, getViewportSize(viewportSize)));
      }
    }

    function handleMouseUp() {
      dragRef.current = null;
      resizeRef.current = null;
    }

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [viewportSize]);

  return (
    <section
      aria-label={title}
      className="review-ocr-window"
      role="dialog"
      style={{
        left: `${rect.left}px`,
        top: `${rect.top}px`,
        width: `${rect.width}px`,
        height: `${rect.height}px`,
      }}
    >
      <header
        className="review-ocr-window__titlebar"
        data-testid="ocr-window-drag-handle"
        onMouseDown={(event) => {
          if (event.button !== 0) return;
          dragRef.current = { startX: event.clientX, startY: event.clientY, startRect: rect };
        }}
      >
        <div className="review-ocr-window__title">
          <span>{selectedFieldLabel ?? 'OCR'}</span>
          <strong>OCR 原文</strong>
        </div>
        <div className="review-ocr-window__actions">
          <button
            type="button"
            aria-label="回到当前字段原文"
            title="回到当前字段原文"
            onClick={() => returnToHighlight?.()}
          >
            ↺
          </button>
          <button type="button" aria-label="恢复默认窗口大小和位置" title="恢复默认窗口大小和位置" onClick={resetRect}>
            ◱
          </button>
          <button type="button" aria-label="关闭 OCR 原文窗口" title="关闭 OCR 原文窗口" onClick={onClose}>
            ×
          </button>
        </div>
      </header>
      <div className="review-ocr-window__body">
        <ReviewSourcePanel
          text={text}
          sourceMessage={sourceMessage}
          hideLocatedMessage
          onReturnToHighlightReady={(callback) => setReturnToHighlight(() => callback)}
        />
      </div>
      <button
        type="button"
        aria-label="调整 OCR 原文窗口大小"
        className="review-ocr-window__resize"
        data-testid="ocr-window-resize-handle"
        onMouseDown={(event) => {
          if (event.button !== 0) return;
          resizeRef.current = { startX: event.clientX, startY: event.clientY, startRect: rect };
        }}
      />
    </section>
  );
}
