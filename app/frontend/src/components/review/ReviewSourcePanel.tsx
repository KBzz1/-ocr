import { useEffect, useRef, type RefObject } from 'react';

export const MAX_EVIDENCE_HIGHLIGHT_CHARS = 100;

export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable' | 'too_long';
  text: string;
  evidenceText?: string;
};

type ReviewSourcePanelProps = {
  text: string;
  sourceMessage: SourceMessage | null;
};

function resolveSourceMessage(sourceMessage: SourceMessage | null): SourceMessage | null {
  if (!sourceMessage?.evidenceText) return sourceMessage;
  if (sourceMessage.evidenceText.length <= MAX_EVIDENCE_HIGHLIGHT_CHARS) return sourceMessage;
  return {
    kind: 'too_long',
    text: '来源片段过长（>100 字），不进行高亮，请人工核验',
  };
}

function renderTextWithHighlight(text: string, evidenceText: string | undefined, markRef: RefObject<HTMLElement>) {
  if (!evidenceText) return text;
  if (evidenceText.length > MAX_EVIDENCE_HIGHLIGHT_CHARS) return text;
  const index = text.indexOf(evidenceText);
  if (index < 0) return text;

  return (
    <>
      {text.slice(0, index)}
      <mark ref={markRef}>{evidenceText}</mark>
      {text.slice(index + evidenceText.length)}
    </>
  );
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
      <pre aria-label="合并 OCR 文本">{renderTextWithHighlight(text, effectiveSourceMessage?.evidenceText, markRef)}</pre>
    </div>
  );
}
