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

type PatientInfo = {
  name?: string;
  gender?: string;
  age?: string;
  department?: string;
  bedNo?: string;
};

type ReviewOcrFloatingWindowProps = {
  text: string;
  sourceMessage: SourceMessage | null;
  selectedFieldLabel?: string;
  patientInfo?: PatientInfo | null;
  onClose: () => void;
  initialRect?: WindowRect;
  viewportSize?: ViewportSize;
};

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

function getDefaultRect(viewport: ViewportSize): WindowRect {
  const width = Math.min(1072, Math.max(MIN_WIDTH, viewport.width - 320));
  const height = Math.min(893, Math.max(MIN_HEIGHT, viewport.height - 120));
  return {
    left: Math.max(24, Math.round((viewport.width - width) / 2)),
    top: Math.max(48, Math.round((viewport.height - height) / 2)),
    width,
    height,
  };
}

function parsePatientInfo(text: string): PatientInfo {
  const info: PatientInfo = {};
  const find = (pattern: RegExp) => {
    const match = text.match(pattern);
    return match ? match[1].trim() : undefined;
  };
  info.name = find(/姓\s*名[：:]\s*([^\s,，\n]+)/);
  info.gender = find(/性\s*别[：:]\s*([^\s,，\n]+)/);
  info.age = find(/年\s*龄[：:]\s*([^\s,，\n]+)/);
  info.department = find(/(?:科\s*室|科\s*别)[：:]\s*([^\n]+)/);
  info.bedNo = find(/床\s*号[：:]\s*([^\s,，\n]+)/);
  return info;
}

export function ReviewOcrFloatingWindow({
  text,
  sourceMessage,
  selectedFieldLabel,
  patientInfo,
  onClose,
  initialRect,
  viewportSize,
}: ReviewOcrFloatingWindowProps) {
  const viewport = useMemo(() => getViewportSize(viewportSize), [viewportSize]);
  const [rect, setRect] = useState<WindowRect>(() => clampRect(initialRect ?? getDefaultRect(viewport), viewport));
  const dragRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);
  const resizeRef = useRef<{ startX: number; startY: number; startRect: WindowRect } | null>(null);
  const [returnToHighlight, setReturnToHighlight] = useState<(() => void) | null>(null);

  const title = selectedFieldLabel ? `${selectedFieldLabel} · OCR 原文` : 'OCR 原文';

  const resolvedPatientInfo = useMemo<PatientInfo>(() => {
    if (patientInfo) return patientInfo;
    return parsePatientInfo(text);
  }, [patientInfo, text]);

  const patientInfoChips = useMemo(() => {
    const items: Array<{ label: string; value: string }> = [];
    if (resolvedPatientInfo.name) items.push({ label: '姓名', value: resolvedPatientInfo.name });
    if (resolvedPatientInfo.gender) items.push({ label: '性别', value: resolvedPatientInfo.gender });
    if (resolvedPatientInfo.age) items.push({ label: '年龄', value: resolvedPatientInfo.age });
    if (resolvedPatientInfo.department) items.push({ label: '科室', value: resolvedPatientInfo.department });
    if (resolvedPatientInfo.bedNo) items.push({ label: '床号', value: resolvedPatientInfo.bedNo });
    return items;
  }, [resolvedPatientInfo]);

  const resetRect = useCallback(() => {
    const nextViewport = getViewportSize(viewportSize);
    setRect(clampRect(initialRect ?? getDefaultRect(nextViewport), nextViewport));
  }, [initialRect, viewportSize]);

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
          <span className="review-ocr-window__title-main">{title}</span>
        </div>
        <div className="review-ocr-window__actions">
          <button
            type="button"
            className="review-ocr-window__action review-ocr-window__action--info"
            aria-label="OCR 原文信息"
            title="OCR 原文信息"
            onClick={() => undefined}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.2" />
              <line x1="7" y1="6" x2="7" y2="10" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              <circle cx="7" cy="4.2" r="0.8" fill="currentColor" />
            </svg>
          </button>
          <button
            type="button"
            className="review-ocr-window__action review-ocr-window__action--reset"
            aria-label="恢复默认窗口大小和位置"
            title="恢复默认窗口大小和位置"
            onClick={resetRect}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <rect x="2.5" y="2.5" width="9" height="9" rx="1.4" fill="none" stroke="currentColor" strokeWidth="1.2" />
              <line x1="2.5" y1="6" x2="11.5" y2="6" stroke="currentColor" strokeWidth="1.2" />
            </svg>
          </button>
          <button
            type="button"
            className="review-ocr-window__action review-ocr-window__action--close"
            aria-label="关闭 OCR 原文窗口"
            title="关闭 OCR 原文窗口"
            onClick={onClose}
          >
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <line x1="2.5" y1="2.5" x2="9.5" y2="9.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
              <line x1="9.5" y1="2.5" x2="2.5" y2="9.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      </header>
      {patientInfoChips.length > 0 ? (
        <div className="review-ocr-window__fieldbar" aria-label="患者信息">
          {patientInfoChips.map((chip) => (
            <span key={chip.label} className="review-ocr-window__fieldchip">
              <span className="review-ocr-window__fieldchip-label">{chip.label}</span>
              <span className="review-ocr-window__fieldchip-value">{chip.value}</span>
            </span>
          ))}
        </div>
      ) : null}
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
