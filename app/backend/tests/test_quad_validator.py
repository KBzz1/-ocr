import json
import pytest
from app.backend.errors import AppError, ErrorCode


class TestQuadValidator:
    def test_accepts_valid_quad(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]
        result = validate_quad_points(json.dumps(pts), 1920, 1080, min_area_ratio=0.01)
        assert result == pts

    def test_none_returns_none(self):
        from app.backend.services.quad_validator import validate_quad_points
        assert validate_quad_points(None, 1920, 1080, 0.01) is None

    def test_empty_string_returns_none(self):
        from app.backend.services.quad_validator import validate_quad_points
        assert validate_quad_points("", 1920, 1080, 0.01) is None

    def test_rejects_non_json(self):
        from app.backend.services.quad_validator import validate_quad_points
        with pytest.raises(AppError) as exc_info:
            validate_quad_points("not json", 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_three_points(self):
        from app.backend.services.quad_validator import validate_quad_points
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps([[0, 0], [1, 1], [2, 2]]), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_five_points(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_non_numeric(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [["a", 0], [1, 0], [1, 1], [0, 1]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_nan_inf(self):
        from app.backend.services.quad_validator import validate_quad_points
        for bad in [float('nan'), float('inf'), float('-inf')]:
            pts = [[bad, 0], [1, 0], [1, 1], [0, 1]]
            with pytest.raises(AppError) as exc_info:
                validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
            assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_negative_coordinates(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [[-1, 0], [1920, 0], [1920, 1080], [0, 1080]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_out_of_bounds(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [[0, 0], [1921, 0], [1920, 1080], [0, 1080]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_self_intersecting(self):
        from app.backend.services.quad_validator import validate_quad_points
        # diagonal crossing
        pts = [[0, 0], [1920, 1080], [1920, 0], [0, 1080]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_zero_area(self):
        from app.backend.services.quad_validator import validate_quad_points
        pts = [[100, 100], [100, 100], [100, 100], [100, 100]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code

    def test_rejects_area_below_min_ratio(self):
        from app.backend.services.quad_validator import validate_quad_points
        # only 2 pixels area, less than 1920*1080*0.01
        pts = [[0, 0], [2, 0], [2, 1], [0, 1]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code
