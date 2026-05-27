import { useEffect, useRef, type RefObject } from 'react';

export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable';
  text: string;
  evidenceText?: string;
};

type ReviewSourcePanelProps = {
  text: string;
  sourceMessage: SourceMessage | null;
};

function renderTextWithHighlight(text: string, evidenceText: string | undefined, markRef: RefObject<HTMLElement>) {
  if (!evidenceText) return text;
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

  useEffect(() => {
    if (sourceMessage?.kind !== 'located') return;
    if (typeof markRef.current?.scrollIntoView !== 'function') return;
    markRef.current.scrollIntoView({ block: 'center', inline: 'nearest' });
  }, [sourceMessage?.evidenceText, sourceMessage?.kind]);

  return (
    <div className="review-source">
      {sourceMessage ? <p className={`review-source__message review-source__message--${sourceMessage.kind}`}>{sourceMessage.text}</p> : null}
      <pre aria-label="合并 OCR 文本">{renderTextWithHighlight(text, sourceMessage?.evidenceText, markRef)}</pre>
    </div>
  );
}
