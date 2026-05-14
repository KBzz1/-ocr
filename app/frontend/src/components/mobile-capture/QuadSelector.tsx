import { useId, useMemo, useRef } from 'react';

import type { QuadPoint } from '../../api/captureSessions';

export type QuadCorner = 'tl' | 'tr' | 'br' | 'bl';

const cornerOrder: QuadCorner[] = ['tl', 'tr', 'br', 'bl'];

export type QuadPointsByCorner = Record<QuadCorner, QuadPoint>;

export function createDefaultQuad(width: number, height: number): QuadPointsByCorner {
  const insetX = Math.round(width * 0.1);
  const insetY = Math.round(height * 0.1);

  return {
    tl: { x: insetX, y: insetY },
    tr: { x: width - insetX, y: insetY },
    br: { x: width - insetX, y: height - insetY },
    bl: { x: insetX, y: height - insetY }
  };
}

export function quadToArray(points: QuadPointsByCorner) {
  return cornerOrder.map((corner) => points[corner]);
}

function orientation(a: QuadPoint, b: QuadPoint, c: QuadPoint) {
  return (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
}

function segmentsIntersect(a: QuadPoint, b: QuadPoint, c: QuadPoint, d: QuadPoint) {
  const first = orientation(a, b, c);
  const second = orientation(a, b, d);
  const third = orientation(c, d, a);
  const fourth = orientation(c, d, b);

  return first * second < 0 && third * fourth < 0;
}

export function isValidQuad(points: QuadPointsByCorner) {
  return (
    !segmentsIntersect(points.tl, points.tr, points.br, points.bl) &&
    !segmentsIntersect(points.tr, points.br, points.bl, points.tl)
  );
}

interface QuadSelectorProps {
  width: number;
  height: number;
  points: QuadPointsByCorner;
  onChange: (next: QuadPointsByCorner) => void;
}

export function QuadSelector({ width, height, points, onChange }: QuadSelectorProps) {
  const maskId = useId();
  const polygonPoints = useMemo(
    () => quadToArray(points).map((point) => `${point.x},${point.y}`).join(' '),
    [points]
  );

  const svgRef = useRef<SVGSVGElement>(null);
  const activeCornerRef = useRef<QuadCorner | null>(null);

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value));
  }

  function eventToPoint(event: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return {
      x: clamp(Math.round(((event.clientX - rect.left) / rect.width) * width), 0, width),
      y: clamp(Math.round(((event.clientY - rect.top) / rect.height) * height), 0, height)
    };
  }

  function nearestCorner(point: { x: number; y: number }) {
    return cornerOrder.reduce((nearest, corner) => {
      const current = points[corner];
      const nearestPoint = points[nearest];
      const currentDistance = (current.x - point.x) ** 2 + (current.y - point.y) ** 2;
      const nearestDistance = (nearestPoint.x - point.x) ** 2 + (nearestPoint.y - point.y) ** 2;
      return currentDistance < nearestDistance ? corner : nearest;
    }, cornerOrder[0]);
  }

  function handlePointerDown(event: React.PointerEvent<SVGSVGElement>) {
    const point = eventToPoint(event);
    if (!point) return;
    const corner = nearestCorner(point);
    activeCornerRef.current = corner;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!activeCornerRef.current) return;
    const point = eventToPoint(event);
    if (!point) return;
    onChange({ ...points, [activeCornerRef.current]: point });
  }

  function handlePointerEnd(event: React.PointerEvent<SVGSVGElement>) {
    if (activeCornerRef.current) {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
    activeCornerRef.current = null;
  }

  return (
    <div className="quad-selector" aria-label="四边形框选区域">
      <svg
        ref={svgRef}
        className="quad-selector__overlay"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="四边形框选叠加层"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerEnd}
        onPointerCancel={handlePointerEnd}
      >
        <defs>
          <mask id={maskId}>
            <rect width={width} height={height} fill="white" />
            <polygon points={polygonPoints} fill="black" />
          </mask>
        </defs>
        <rect width={width} height={height} fill="rgba(15, 23, 42, 0.36)" mask={`url(#${maskId})`} />
        <polygon
          points={polygonPoints}
          fill="rgba(37, 99, 235, 0.08)"
          stroke="#1167f2"
          strokeWidth="5"
        />
        {cornerOrder.map((corner) => (
          <circle
            key={corner}
            cx={points[corner].x}
            cy={points[corner].y}
            r="18"
            fill="#1167f2"
            stroke="#ffffff"
            strokeWidth="5"
          />
        ))}
      </svg>
    </div>
  );
}
