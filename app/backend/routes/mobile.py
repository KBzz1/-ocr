import json

from flask import Blueprint, current_app, request

from ..errors import AppError, ErrorCode
from ..responses import success
from . import _safe_event

mobile_bp = Blueprint("mobile", __name__)


def _service():
    return current_app.config["SESSION_SERVICE"]


def _page_service():
    return current_app.config["PAGE_SERVICE"]


def _parse_dimensions():
    image_width_str = request.form.get("image_width")
    image_height_str = request.form.get("image_height")
    if not image_width_str or not image_height_str:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image_width 或 image_height")

    try:
        return int(image_width_str), int(image_height_str)
    except (ValueError, TypeError):
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 和 image_height 必须为整数")


def _normalize_quad_points(points):
    """将 {x, y} 字典格式的四角点转为 [[x, y], ...] 列表格式。"""
    if points is None:
        return None
    if len(points) != 4:
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)
    normalized = []
    for pt in points:
        if isinstance(pt, dict):
            if "x" not in pt or "y" not in pt:
                raise AppError(ErrorCode.INVALID_QUAD_POINTS)
            normalized.append([pt["x"], pt["y"]])
        elif isinstance(pt, list):
            normalized.append(pt)
        else:
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
    return normalized


def _quad_points_to_dict(points):
    """将 [[x, y], ...] 列表格式转为 [{x, y}, ...] 字典格式用于 API 响应。"""
    if points is None:
        return None
    return [{"x": pt[0], "y": pt[1]} for pt in points]


@mobile_bp.route("/api/mobile/<session_id>/finish", methods=["POST"])
def finish_session(session_id):
    session = _service().finish(session_id)
    _safe_event(
        "session_finished",
        session_id=session_id,
        task_id=session["task_id"],
        page_count=len(session.get("pages", [])),
    )
    return success(
        data={
            "session_id": session["session_id"],
            "status": session["status"],
            "locked_at": session["locked_at"],
            "task_id": session["task_id"],
        }
    )


@mobile_bp.route("/api/mobile/<session_id>/pages", methods=["POST"])
def upload_page(session_id: str):
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_file = request.files["image"]
    image_data = image_file.read()

    image_width, image_height = _parse_dimensions()
    quad_points_raw = request.form.get("quad_points")
    if quad_points_raw:
        try:
            quad_points_parsed = json.loads(quad_points_raw)
        except (json.JSONDecodeError, TypeError):
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
        quad_points_normalized = _normalize_quad_points(quad_points_parsed)
        quad_points_raw = json.dumps(quad_points_normalized)

    updated = _service().add_page(session_id, upload_ref=None)
    page = updated["pages"][-1]
    created_page_id = page["page_id"]

    try:
        result = _page_service().save(
            session_id=session_id,
            page_id=created_page_id,
            page_no=page["page_no"],
            image_data=image_data,
            image_width=image_width,
            image_height=image_height,
            quad_points_raw=quad_points_raw,
        )
    except Exception:
        try:
            _service().remove_unuploaded_page(session_id, created_page_id)
        except Exception:
            pass
        raise

    _safe_event(
        "page_uploaded",
        session_id=session_id,
        page_id=result["page_id"],
        image_width=result.get("image_width"),
        image_height=result.get("image_height"),
    )
    return success(data=result, status=201)


@mobile_bp.route("/api/mobile/<session_id>/pages/<page_id>/quad", methods=["PUT"])
def update_page_quad(session_id: str, page_id: str):
    _service()._ensure_editable(_service().get(session_id))
    payload = request.get_json(silent=True) or {}
    quad_points = payload.get("quad_points")
    if quad_points is None:
        raise AppError(ErrorCode.INVALID_QUAD_POINTS)
    quad_points_normalized = _normalize_quad_points(quad_points)
    result = _page_service().update_quad(
        session_id=session_id,
        page_id=page_id,
        quad_points_raw=json.dumps(quad_points_normalized),
    )
    return success(
        data={
            "page_id": result["page_id"],
            "page_no": result["page_no"],
            "quad_points": _quad_points_to_dict(result.get("quad_points")),
            "quad_updated_at": result.get("quad_updated_at"),
        }
    )


@mobile_bp.route("/api/mobile/<session_id>/pages/<page_id>/image", methods=["PUT"])
def replace_page_image(session_id: str, page_id: str):
    _service()._ensure_editable(_service().get(session_id))
    if "image" not in request.files:
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_width, image_height = _parse_dimensions()
    image_data = request.files["image"].read()
    quad_points_raw = request.form.get("quad_points")
    if quad_points_raw:
        try:
            quad_points_parsed = json.loads(quad_points_raw)
        except (json.JSONDecodeError, TypeError):
            raise AppError(ErrorCode.INVALID_QUAD_POINTS)
        quad_points_normalized = _normalize_quad_points(quad_points_parsed)
        quad_points_raw = json.dumps(quad_points_normalized)
    result = _page_service().replace_image(
        session_id=session_id,
        page_id=page_id,
        image_data=image_data,
        image_width=image_width,
        image_height=image_height,
        quad_points_raw=quad_points_raw,
    )
    return success(data=result)
