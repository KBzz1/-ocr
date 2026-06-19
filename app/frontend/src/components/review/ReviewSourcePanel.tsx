import { useEffect, useRef, type RefObject } from 'react';

export const MAX_EVIDENCE_HIGHLIGHT_CHARS = 100;

export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable' | 'too_long' | 'unlocated';
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
  if (sourceMessage.evidenceText.length <= MAX_EVIDENCE_HIGHLIGHT_CHARS) return sourceMessage;
  return {
    kind: 'too_long',
    text: '来源片段过长（>100 字），不进行高亮，请人工核验',
  };
}

function renderTextWithHighlight(
  text: string,
  evidenceText: string | undefined,
  startIndex: number | undefined,
  markRef: RefObject<HTMLElement>,
) {
  if (!evidenceText) return text;
  if (evidenceText.length > MAX_EVIDENCE_HIGHLIGHT_CHARS) return text;
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
    if (slice && slice === rawText.substring(start, end)) {
      const highlight = slice.length <= MAX_EVIDENCE_HIGHLIGHT_CHARS ? slice : slice.slice(0, MAX_EVIDENCE_HIGHLIGHT_CHARS);
      if (rawText.slice(start, start + highlight.length) === highlight) {
        return { rawText, highlightText: highlight, startIndex: start };
      }
    }
  }

  if (text && rawText.includes(text)) {
    if (text.length <= MAX_EVIDENCE_HIGHLIGHT_CHARS) {
      return { rawText, highlightText: text, startIndex: rawText.indexOf(text) };
    }
    return null;
  }

  return null;
}

export function ReviewSourcePanel({ text, sourceMessage }: ReviewSourcePanelProps) {
  const markRef = useRef<HTMLElement>(null);
  const effectiveSourceMessage = resolveSourceMessage(sourceMessage);

  useEffect(() => {
    if (effectiveSourceMessage?.kind !== 'located') return;
    if (typeof markRef.current?.scrollIntoView !== 'function') return;
    markRef.current.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, [effectiveSourceMessage?.evidenceText, effectiveSourceMessage?.kind]);

  return (
    <div className="review-source">
      {effectiveSourceMessage ? <p className={`review-source__message review-source__message--${effectiveSourceMessage.kind}`}>{effectiveSourceMessage.text}</p> : null}
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
