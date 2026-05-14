import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { createDefaultQuad, QuadSelector, type QuadPointsByCorner } from './QuadSelector';

function setSvgRect(element: Element) {
  Object.defineProperty(element, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({
      left: 0,
      top: 0,
      width: 100,
      height: 140,
      right: 100,
      bottom: 140,
      x: 0,
      y: 0,
      toJSON: () => {}
    })
  });
}

function pointer(type: string, x: number, y: number) {
  if (typeof PointerEvent === 'function') {
    return new PointerEvent(type, {
      bubbles: true,
      pointerId: 1,
      clientX: x,
      clientY: y
    });
  }

  const event = new Event(type, { bubbles: true }) as PointerEvent;
  Object.defineProperty(event, 'pointerId', { value: 1 });
  Object.defineProperty(event, 'clientX', { value: x });
  Object.defineProperty(event, 'clientY', { value: y });
  return event;
}

describe('QuadSelector', () => {
  it('updates the dragged corner and redraws the polygon', () => {
    const onChange = vi.fn();
    const points = createDefaultQuad(1000, 1400);
    render(<QuadSelector width={1000} height={1400} points={points} onChange={onChange} />);
    const overlay = screen.getByLabelText('四边形框选叠加层');
    setSvgRect(overlay);
    Object.defineProperty(overlay, 'setPointerCapture', { configurable: true, value: vi.fn() });
    Object.defineProperty(overlay, 'releasePointerCapture', { configurable: true, value: vi.fn() });

    overlay.dispatchEvent(pointer('pointerdown', 10, 14));
    overlay.dispatchEvent(pointer('pointermove', 20, 28));
    overlay.dispatchEvent(pointer('pointerup', 20, 28));

    expect(onChange).toHaveBeenCalledWith({
      ...points,
      tl: { x: 200, y: 280 }
    });
  });

  it('clamps dragged corners inside the image bounds', () => {
    const onChange = vi.fn();
    const points = createDefaultQuad(1000, 1400);
    render(<QuadSelector width={1000} height={1400} points={points} onChange={onChange} />);
    const overlay = screen.getByLabelText('四边形框选叠加层');
    setSvgRect(overlay);
    Object.defineProperty(overlay, 'setPointerCapture', { configurable: true, value: vi.fn() });
    Object.defineProperty(overlay, 'releasePointerCapture', { configurable: true, value: vi.fn() });

    overlay.dispatchEvent(pointer('pointerdown', 10, 14));
    overlay.dispatchEvent(pointer('pointermove', -50, 200));

    expect(onChange).toHaveBeenCalledWith({
      ...points,
      tl: { x: 0, y: 1400 }
    });
  });
});
