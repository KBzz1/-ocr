import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { ReviewOcrFloatingWindow } from './ReviewOcrFloatingWindow';

function renderWindow(overrides: Partial<ComponentProps<typeof ReviewOcrFloatingWindow>> = {}) {
  const onClose = vi.fn();
  const props: ComponentProps<typeof ReviewOcrFloatingWindow> = {
    text: '姓名：张三\n\n## 主诉\n反复咳嗽、咳痰15年，加重伴喘憋3天。',
    sourceMessage: {
      kind: 'located',
      text: '点击字段可定位原文',
      evidenceText: '反复咳嗽、咳痰15年',
      startIndex: '姓名：张三\n\n## 主诉\n'.length,
    },
    selectedFieldLabel: '主诉',
    onClose,
    ...overrides,
  };
  render(<ReviewOcrFloatingWindow {...props} />);
  return { onClose };
}

describe('ReviewOcrFloatingWindow', () => {
  it('renders complete OCR in a lightweight window without instructional chrome text', () => {
    renderWindow();

    expect(screen.getByRole('dialog', { name: '主诉 OCR 原文' })).toBeTruthy();
    expect(screen.getByText('主诉')).toBeTruthy();
    expect(screen.getByLabelText('合并 OCR 文本').textContent).toContain('姓名：张三');
    expect(screen.getByText('反复咳嗽、咳痰15年', { selector: 'mark' })).toBeTruthy();
    expect(screen.queryByText('点击字段可定位原文')).toBeNull();
    expect(screen.queryByText(/拖动标题栏/)).toBeNull();
    expect(screen.queryByText(/右下角缩放/)).toBeNull();
  });

  it('uses compact controls with accessible names', () => {
    const { onClose } = renderWindow();

    expect(screen.getByRole('button', { name: '回到当前字段原文' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '恢复默认窗口大小和位置' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '关闭 OCR 原文窗口' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('moves within the viewport when the title bar is dragged', () => {
    renderWindow();

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' }) as HTMLElement;
    const handle = screen.getByTestId('ocr-window-drag-handle');

    fireEvent.mouseDown(handle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 180, clientY: 150 });
    fireEvent.mouseUp(window);

    expect(dialog.style.left).toBe('420px');
    expect(dialog.style.top).toBe('190px');
  });

  it('clamps drag position so the window cannot be lost off screen', () => {
    renderWindow({
      viewportSize: { width: 800, height: 600 },
      initialRect: { left: 320, top: 140, width: 520, height: 340 },
    });

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' }) as HTMLElement;
    const handle = screen.getByTestId('ocr-window-drag-handle');

    fireEvent.mouseDown(handle, { clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 900, clientY: 900 });
    fireEvent.mouseUp(window);

    expect(dialog.style.left).toBe('280px');
    expect(dialog.style.top).toBe('260px');
  });

  it('resizes with the resize handle while preserving minimum dimensions', () => {
    renderWindow();

    const dialog = screen.getByRole('dialog', { name: '主诉 OCR 原文' }) as HTMLElement;
    const resizeHandle = screen.getByTestId('ocr-window-resize-handle');

    fireEvent.mouseDown(resizeHandle, { clientX: 840, clientY: 480 });
    fireEvent.mouseMove(window, { clientX: 900, clientY: 540 });
    fireEvent.mouseUp(window);

    expect(dialog.style.width).toBe('580px');
    expect(dialog.style.height).toBe('400px');

    fireEvent.mouseDown(resizeHandle, { clientX: 900, clientY: 540 });
    fireEvent.mouseMove(window, { clientX: 100, clientY: 100 });
    fireEvent.mouseUp(window);

    expect(dialog.style.width).toBe('360px');
    expect(dialog.style.height).toBe('240px');
  });
});
