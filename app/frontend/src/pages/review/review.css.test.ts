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

  it('keeps review field controls aligned to stable full-width grid tracks', () => {
    expect(css).toContain(".field-card__item[data-testid='review-field-card-diagnosis_initial']");
    expect(css).toContain(".field-card__item[data-testid='review-field-card-diagnosis_final']");
    expect(css).toContain("grid-column: 1 / -1;");
    expect(css).toContain('.field-card__value-row {\n  position: relative;\n  width: 100%;\n  min-width: 0;');
    expect(css).toContain('.field-card__value-row--judgement {\n  display: grid;\n  grid-template-columns: minmax(0, 1fr);');
    expect(css).toContain('.field-card__text-editor,\n.field-card__abnormal-editor {\n  box-sizing: border-box;');
    expect(css).toContain('.field-card__judgement-warning {\n  position: absolute;');
    expect(css).toContain('.field-card__diagnosis-input {\n  width: 100%;\n  box-sizing: border-box;');
  });

  it('supports dense one-row parameter groups for vitals and blood gas', () => {
    expect(css).toContain(".field-card__parameter-set[data-columns='6'] .field-card__parameter-grid");
    expect(css).toContain('grid-template-columns: repeat(6, minmax(0, 1fr));');
    expect(css).toContain(".field-card__parameter-set[data-columns='8'] .field-card__parameter-grid");
    expect(css).toContain('grid-template-columns: repeat(8, minmax(0, 1fr));');
  });
});
