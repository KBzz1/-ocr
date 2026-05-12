import json
import math

from ..errors import AppError, ErrorCode


def validate_quad_points(
    quad_points_raw: str | None,
    image_width: int,
    image_height: int,
    min_area_ratio: float = 0.01,
) -> list | None:
    """校验 quad_points。合法返回坐标列表，缺失返回 None，非法抛出 AppError。"""
    if quad_points_raw is None or quad_points_raw == "":
        return None

    try:
        points = json.loads(quad_points_raw)
    except (json.JSONDecodeError, TypeError):
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)

    if not isinstance(points, list) or len(points) != 4:
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)

    for pt in points:
        if not isinstance(pt, list) or len(pt) != 2:
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
        x, y = pt
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
        if math.isnan(x) or math.isnan(y) or math.isinf(x) or math.isinf(y):
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
        if x < 0 or y < 0 or x > image_width or y > image_height:
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)

    # self-intersection check: non-adjacent edges
    # edges: 0-1, 1-2, 2-3, 3-0; check (0-1 vs 2-3) and (1-2 vs 3-0)
    if (_segments_intersect(points[0], points[1], points[2], points[3]) or
            _segments_intersect(points[1], points[2], points[3], points[0])):
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)

    area = _polygon_area(points)
    if area < image_width * image_height * min_area_ratio:
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)

    return points


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def _segments_intersect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d1 = _cross(x4 - x3, y4 - y3, x1 - x3, y1 - y3)
    d2 = _cross(x4 - x3, y4 - y3, x2 - x3, y2 - y3)
    d3 = _cross(x2 - x1, y2 - y1, x3 - x1, y3 - y1)
    d4 = _cross(x2 - x1, y2 - y1, x4 - x1, y4 - y1)
    return ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0))


def _polygon_area(points):
    n = len(points)
    area = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
