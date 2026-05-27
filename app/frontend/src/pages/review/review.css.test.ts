import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const currentDir = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(currentDir, 'review.css'), 'utf8');

describe('review workspace layout css contract', () => {
  it('uses 字段校对 as the visible field panel title without generated 人工审核 prefix', () => {
    expect(css).not.toContain('content: "人工审核与"');
  });

  it('lets field cards expand fully while the OCR text box scrolls within a matched panel height', () => {
    expect(css).toContain('grid-template-columns: minmax(300px, 0.36fr) minmax(680px, 1fr);');
    expect(css).toContain('align-items: start;');
    expect(css).toContain('.review-panel--ocr {\n  align-self: start;\n  display: flex;\n  flex-direction: column;\n  height: var(--review-ocr-panel-height, min(640px, 72vh));\n  min-height: 0;');
    expect(css).toContain('.review-source {\n  flex: 1;\n  min-height: 0;\n  height: auto;');
    expect(css).toContain('.review-source pre {\n  height: 100%;\n  min-height: 0;');
    expect(css).toContain('overflow: auto;');
    expect(css).toContain('.review-panel--fields .field-cards {\n  height: auto;\n  max-height: none;\n  overflow: visible;');
  });
});
