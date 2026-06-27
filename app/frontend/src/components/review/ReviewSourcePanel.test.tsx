import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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

  it('renders a long locatable evidence unit without applying the old 100 character guard', () => {
    const evidenceText =
      '体格检查：体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg 身高：175cm 体重：74kg BMI：24.2kg/m²，双肺呼吸音稍低，未闻及明显湿啰音。';
    const rawText = `入院记录。\n${evidenceText}\n处理意见：继续观察。`;
    const start = rawText.indexOf(evidenceText);

    render(
      <ReviewSourcePanel
        text={rawText}
        sourceMessage={{
          kind: 'located',
          text: '点击字段可定位原文',
          evidenceText,
          startIndex: start,
        }}
      />,
    );

    const pre = screen.getByLabelText('合并 OCR 文本');
    expect(pre.querySelector('mark')?.textContent).toBe(evidenceText);
  });

  it('does not locate evidence text without a verified offset', () => {
    const rawText = '精神睡眠食欲差。主诉：反复咳嗽。精神睡眠食欲差。';

    const location = locateEvidence(rawText, {
      text: '精神睡眠食欲差。',
    });

    expect(location).toBeNull();
  });

  it('exposes a return-to-highlight callback when evidence is located', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    let callback: (() => void) | undefined;

    render(
      <ReviewSourcePanel
        text="主诉：反复咳嗽、咳痰15年"
        sourceMessage={{
          kind: 'located',
          text: '点击字段可定位原文',
          evidenceText: '反复咳嗽、咳痰15年',
          startIndex: 3,
        }}
        onReturnToHighlightReady={(nextCallback) => {
          callback = nextCallback;
        }}
      />,
    );

    callback?.();
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', inline: 'nearest' });
  });
});
