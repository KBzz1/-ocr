import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { locateEvidence, ReviewSourcePanel } from './ReviewSourcePanel';

describe('ReviewSourcePanel', () => {
  it('locates evidence by offset when the same text appears more than once', () => {
    const rawText = '体温：36.7℃。\n复查体温：36.7℃。';
    const start = rawText.lastIndexOf('体温：36.7℃');

    const location = locateEvidence(rawText, {
      text: '体温：36.7℃',
      start_offset: start,
      end_offset: start + '体温：36.7℃'.length,
    });

    expect(location).toMatchObject({
      highlightText: '体温：36.7℃',
      startIndex: start,
    });
  });

  it('renders the highlight at the offset location instead of the first matching text', () => {
    const rawText = '体温：36.7℃。\n复查体温：36.7℃。';
    const start = rawText.lastIndexOf('体温：36.7℃');

    render(
      <ReviewSourcePanel
        text={rawText}
        sourceMessage={{
          kind: 'located',
          text: '点击字段可定位原文',
          evidenceText: '体温：36.7℃',
          startIndex: start,
        }}
      />,
    );

    const pre = screen.getByLabelText('合并 OCR 文本');
    const mark = pre.querySelector('mark');
    expect(mark?.textContent).toBe('体温：36.7℃');
    expect(Array.from(pre.childNodes)[0].textContent).toBe('体温：36.7℃。\n复查');
  });
});
