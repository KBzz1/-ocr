export type SourceMessage = {
  kind: 'located' | 'missing' | 'unavailable';
  text: string;
  evidenceText?: string;
};

type ReviewSourcePanelProps = {
  text: string;
  sourceMessage: SourceMessage | null;
};

function renderTextWithHighlight(text: string, evidenceText?: string) {
  if (!evidenceText) return text;
  const index = text.indexOf(evidenceText);
  if (index < 0) return text;

  return (
    <>
      {text.slice(0, index)}
      <mark>{evidenceText}</mark>
      {text.slice(index + evidenceText.length)}
    </>
  );
}

export function ReviewSourcePanel({ text, sourceMessage }: ReviewSourcePanelProps) {
  return (
    <div className="review-source">
      {sourceMessage ? <p className={`review-source__message review-source__message--${sourceMessage.kind}`}>{sourceMessage.text}</p> : null}
      <pre aria-label="合并 OCR 文本">{renderTextWithHighlight(text, sourceMessage?.evidenceText)}</pre>
    </div>
  );
}
