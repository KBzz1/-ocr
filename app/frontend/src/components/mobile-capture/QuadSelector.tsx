import { useId, useMemo } from 'react';

import type { QuadPoint } from '../../api/captureSessions';

export type QuadCorner = 'tl' | 'tr' | 'br' | 'bl';

const cornerLabels: Record<QuadCorner, string> = {
  tl: '左上角',
  tr: '右上角',
  br: '右下角',
  bl: '左下角'
};

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

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
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

  function updateCorner(corner: QuadCorner, axis: 'x' | 'y', value: number) {
    onChange({
      ...points,
      [corner]: {
        ...points[corner],
        [axis]: clamp(value, 0, axis === 'x' ? width : height)
      }
    });
  }

  return (
    <div className="quad-selector" aria-label="四边形框选区域">
      <svg
        className="quad-selector__overlay"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="四边形框选叠加层"
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

      <div className="quad-selector__controls" aria-label="角点坐标">
        {cornerOrder.map((corner) => (
          <fieldset key={corner}>
            <legend>{cornerLabels[corner]}</legend>
            <label>
              X
              <input
                type="range"
                min="0"
                max={width}
                value={points[corner].x}
                aria-label={`${cornerLabels[corner]} X 坐标`}
                onChange={(event) => updateCorner(corner, 'x', Number(event.currentTarget.value))}
              />
            </label>
            <label>
              Y
              <input
                type="number"
                min="0"
                max={height}
                value={points[corner].y}
                aria-label={`${cornerLabels[corner]} Y 坐标`}
                onChange={(event) => updateCorner(corner, 'y', Number(event.currentTarget.value))}
              />
            </label>
          </fieldset>
        ))}
      </div>
    </div>
  );
}
