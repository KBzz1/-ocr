import { useCallback, useEffect, useRef, type RefObject } from 'react';

export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable' | 'unlocated';
  text: string;
  evidenceText?: string;
  startIndex?: number;
};

export type EvidenceLocation = {
  rawText: string;
  highlightText: string;
  startIndex: number;
};

type ReviewSourcePanelProps = {
  text: string;
  sourceMessage: SourceMessage | null;
  onReturnToHighlightReady?: (callback: () => void) => void;
  hideLocatedMessage?: boolean;
};

function resolveSourceMessage(sourceMessage: SourceMessage | null): SourceMessage | null {
  if (!sourceMessage) return sourceMessage;
  if (sourceMessage.kind !== 'located') return sourceMessage;
  if (!sourceMessage.evidenceText) {
    return {
      kind: 'unlocated',
      text: '来源片段未在 OCR 文本中定位，请核对',
    };
  }
  return sourceMessage;
}

function renderTextWithHighlight(
  text: string,
  evidenceText: string | undefined,
  startIndex: number | undefined,
  markRef: RefObject<HTMLElement>,
) {
  if (!evidenceText) return text;
  const offsetMatches =
    typeof startIndex === 'number' &&
    startIndex >= 0 &&
    text.slice(startIndex, startIndex + evidenceText.length) === evidenceText;
  const index = offsetMatches ? startIndex : text.indexOf(evidenceText);
  if (index < 0) return text;

  return (
    <>
      {text.slice(0, index)}
      <mark ref={markRef}>{evidenceText}</mark>
      {text.slice(index + evidenceText.length)}
    </>
  );
}

export function locateEvidence(
  rawText: string,
  evidence?: { text?: string; start_offset?: number; end_offset?: number }
): EvidenceLocation | null {
  if (!evidence) return null;

  const text = evidence.text;
  const start = evidence.start_offset;
  const end = evidence.end_offset;

  if (typeof start === 'number' && typeof end === 'number' && end > start) {
    const slice = rawText.slice(start, end);
    if (slice && (!text || slice === text)) {
      return { rawText, highlightText: slice, startIndex: start };
    }
  }

  return null;
}

export function ReviewSourcePanel({ text, sourceMessage, onReturnToHighlightReady, hideLocatedMessage = false }: ReviewSourcePanelProps) {
  const markRef = useRef<HTMLElement>(null);
  const effectiveSourceMessage = resolveSourceMessage(sourceMessage);
  const shouldRenderSourceMessage = Boolean(
    effectiveSourceMessage && (!hideLocatedMessage || effectiveSourceMessage.kind !== 'located')
  );

  const scrollToHighlight = useCallback(() => {
    if (effectiveSourceMessage?.kind !== 'located') return;
    if (typeof markRef.current?.scrollIntoView !== 'function') return;
    markRef.current.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, [effectiveSourceMessage?.kind, effectiveSourceMessage?.evidenceText]);

  useEffect(() => {
    scrollToHighlight();
  }, [scrollToHighlight]);

  useEffect(() => {
    onReturnToHighlightReady?.(scrollToHighlight);
  }, [onReturnToHighlightReady, scrollToHighlight]);

  return (
    <div className="review-source">
      {shouldRenderSourceMessage && effectiveSourceMessage ? <p className={`review-source__message review-source__message--${effectiveSourceMessage.kind}`}>{effectiveSourceMessage.text}</p> : null}
      <pre aria-label="合并 OCR 文本">
        {renderTextWithHighlight(
          text,
          effectiveSourceMessage?.evidenceText,
          effectiveSourceMessage?.startIndex,
          markRef,
        )}
      </pre>
    </div>
  );
}
