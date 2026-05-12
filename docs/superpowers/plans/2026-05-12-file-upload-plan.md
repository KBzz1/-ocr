# 图片上传与文件管理（PR-BE-003）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现手机端图片上传到采集会话，包含文件安全校验、quad_points 校验、图片和元数据保存，并将会话页面项与上传文件关联。

**Architecture:** 在 PR-BE-002 SessionService 基础上扩展 `attach_page_upload` 方法。新建 `file_validator.py`（magic bytes 检测、大小校验、路径安全）、`quad_validator.py`（4 点几何校验）、`page_service.py`（协调校验→保存→写回 upload_ref）。路由层追加到 `mobile_bp` 的 `POST /api/mobile/<session_id>/pages`。`page_id` 和 `page_no` 由 `SessionService.add_page()` 分配，文件模块不自行生成。

**Tech Stack:** Flask, pytest, JsonStore (已有), uuid4, datetime(timezone.utc)

**依赖:** PR-BE-002 SessionService（`add_page`, `get`, `create` 等）。如果本分支尚未合并 PR-BE-002，需先执行 Task 0 搭建基线。

---

## 前置：搭建开发基线

### Task 0: 将 PR-BE-002 代码引入本分支

**文件来源:** `/home/kbzz1/manzufei_ocr/.claude/worktrees/backend-minimal-skeleton`

- [ ] **Step 1: 复制 SessionService 和测试**

```bash
SRC=/home/kbzz1/manzufei_ocr/.claude/worktrees/backend-minimal-skeleton
DST=/home/kbzz1/manzufei_ocr/.claude/worktrees/backend-file-upload

cp $SRC/app/backend/services/session_service.py $DST/app/backend/services/session_service.py
cp $SRC/app/backend/tests/test_session_service.py $DST/app/backend/tests/test_session_service.py
cp $SRC/app/backend/routes/capture_session.py $DST/app/backend/routes/capture_session.py
cp $SRC/app/backend/routes/mobile.py $DST/app/backend/routes/mobile.py
```

- [ ] **Step 2: 合并 config.py 变更**

将 PR-BE-002 的 `config.py` 中以下变更合并到本分支：
- `DEFAULT_CONFIG` 新增 `"capture_session_ttl_minutes": 30`
- `_flatten_config` 新增对 `sessions.capture_session_ttl_minutes` 的展平
- `_validate_config` 新增对该值为正整数的校验

同时 `default.yaml` 新增 sessions 段：

```yaml
sessions:
  capture_session_ttl_minutes: 30
```

- [ ] **Step 3: 合并 __init__.py 变更**

`create_backend_app()` 中新增：
- `JsonStore` 和 `SessionService` 初始化
- `app.config["SESSION_SERVICE"]` 挂载
- 注册 `capture_session_bp` 和 `mobile_bp`

- [ ] **Step 4: 运行已有测试确认基线正常**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/backend-file-upload
python -m pytest app/backend/tests/ -v
```

- [ ] **Step 5: 提交基线**

```bash
git add app/backend/services/session_service.py app/backend/tests/test_session_service.py \
        app/backend/config.py app/backend/__init__.py app/config/default.yaml \
        app/backend/routes/capture_session.py app/backend/routes/mobile.py
git commit -m "feat: 引入 PR-BE-002 采集会话管理代码基线"
```

---

## 阶段一：SessionService 扩展 + 错误码 + 配置

### Task 1: 新增 attach_page_upload 方法（TDD）

**Files:**
- Modify: `app/backend/services/session_service.py`
- Modify: `app/backend/tests/test_session_service.py`

- [ ] **Step 1: 写失败测试**

在 `test_session_service.py` 的 `TestSessionPages` 类末尾追加三个测试。第一个测试添加后运行确认 RED。

```python
def test_attach_page_upload_writes_upload_ref(self, tmp_path):
    service = make_service(tmp_path)
    session = service.create()
    service.add_page(session["session_id"])
    current = service.get(session["session_id"])
    page_id = current["pages"][0]["page_id"]

    updated = service.attach_page_upload(
        session["session_id"], page_id, "pages/sess-123/abc.json"
    )

    assert updated["pages"][0]["upload_ref"] == "pages/sess-123/abc.json"
```

```bash
python -m pytest app/backend/tests/test_session_service.py::TestSessionPages::test_attach_page_upload_writes_upload_ref -v
# 预期: FAIL — AttributeError: 'SessionService' object has no attribute 'attach_page_upload'
```

然后追加：

```python
def test_attach_page_upload_missing_session_raises_not_found(self, tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(AppError) as exc_info:
        service.attach_page_upload("missing", "p1", "ref")
    assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code


def test_attach_page_upload_missing_page_raises_not_found(self, tmp_path):
    service = make_service(tmp_path)
    session = service.create()
    with pytest.raises(AppError) as exc_info:
        service.attach_page_upload(session["session_id"], "missing-page", "ref")
    assert exc_info.value.code == ErrorCode.SESSION_NOT_FOUND.code
    assert "页面不存在" in exc_info.value.message
```

- [ ] **Step 2: 实现 attach_page_upload**

在 `session_service.py` 的 `SessionService` 类中，`reorder_pages` 方法之后、`finish` 方法之前添加：

```python
def attach_page_upload(self, session_id: str, page_id: str, upload_ref: str) -> dict:
    """把页面元数据引用写回指定页面项。"""
    session = self.get(session_id)
    for page in session["pages"]:
        if page["page_id"] == page_id:
            page["upload_ref"] = upload_ref
            return self._persist_session(session)
    raise AppError(ErrorCode.SESSION_NOT_FOUND, message="页面不存在")
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_session_service.py::TestSessionPages -v
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/session_service.py app/backend/tests/test_session_service.py
git commit -m "feat: 新增 SessionService.attach_page_upload 方法"
```

---

### Task 2: 新增 INVALID_REQUEST_PARAMS 错误码

**Files:**
- Modify: `app/backend/errors.py`
- Modify: `app/backend/tests/test_errors.py`
- Modify: `docs/Shared/error-codes.md`

- [ ] **Step 1: 写 RED 测试**

在 `test_errors.py` 中新增：

```python
def test_invalid_request_params_error_code_exists():
    from app.backend.errors import ErrorCode
    assert hasattr(ErrorCode, "INVALID_REQUEST_PARAMS")
    code = ErrorCode.INVALID_REQUEST_PARAMS
    assert code.code == "INVALID_REQUEST_PARAMS"
    assert code.http_status == 400
    assert "参数" in code.default_message


def test_invalid_request_params_app_error_response():
    from app.backend.errors import AppError, ErrorCode
    error = AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少必填字段 image")
    assert error.http_status == 400
    assert error.code == "INVALID_REQUEST_PARAMS"
```

```bash
python -m pytest app/backend/tests/test_errors.py::test_invalid_request_params_error_code_exists -v
# 预期: FAIL — AttributeError: INVALID_REQUEST_PARAMS
```

- [ ] **Step 2: 新增错误码枚举**

在 `errors.py` 的 `ErrorCode` 类中，`INVALID_QUAD_POINTS` 之前添加：

```python
INVALID_REQUEST_PARAMS = ("INVALID_REQUEST_PARAMS", 400, "请求参数缺失、类型错误、格式错误或取值非法")
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_errors.py -v
```

- [ ] **Step 4: 更新共享错误码文档**

在 `docs/Shared/error-codes.md` 表格中 `UNSUPPORTED_FILE_TYPE` 之前新增：

```
| `INVALID_REQUEST_PARAMS` | 400 | 请求参数缺失、类型错误、格式错误或取值非法 |
```

- [ ] **Step 5: 提交**

```bash
git add app/backend/errors.py app/backend/tests/test_errors.py docs/Shared/error-codes.md
git commit -m "feat: 新增 INVALID_REQUEST_PARAMS 错误码"
```

---

### Task 3: 新增上传配置项

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/backend/tests/test_config.py`

- [ ] **Step 1: 写 RED 测试**

在 `test_config.py` 中新增：

```python
def test_upload_max_file_size_mb_default(tmp_path):
    from app.backend.config import load_config
    config = load_config(str(tmp_path / "nonexistent"))
    assert config["max_upload_file_size_mb"] == 10


def test_upload_min_quad_area_ratio_default(tmp_path):
    from app.backend.config import load_config
    config = load_config(str(tmp_path / "nonexistent"))
    assert config["min_quad_area_ratio"] == 0.01


def test_flatten_upload_config(tmp_path):
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("""
upload:
  max_file_size_mb: 20
  min_quad_area_ratio: 0.02
""", encoding="utf-8")
    config = load_config(str(config_dir))
    assert config["max_upload_file_size_mb"] == 20
    assert config["min_quad_area_ratio"] == 0.02


def test_max_upload_file_size_mb_must_be_positive(tmp_path):
    import pytest
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("upload:\n  max_file_size_mb: -5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="max_upload_file_size_mb"):
        load_config(str(config_dir))


def test_min_quad_area_ratio_must_be_between_0_and_1(tmp_path):
    import pytest
    from app.backend.config import load_config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("upload:\n  min_quad_area_ratio: 2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="min_quad_area_ratio"):
        load_config(str(config_dir))
```

```bash
python -m pytest app/backend/tests/test_config.py::test_upload_max_file_size_mb_default -v
# 预期: FAIL — KeyError
```

- [ ] **Step 2: 修改 DEFAULT_CONFIG**

在 `config.py` 的 `DEFAULT_CONFIG` dict 中新增：

```python
"max_upload_file_size_mb": 10,
"min_quad_area_ratio": 0.01,
```

- [ ] **Step 3: 修改 _flatten_config**

在 `_flatten_config` 函数末尾（`return flattened` 之前）添加：

```python
upload_config = raw.get("upload", {})
if "max_file_size_mb" in upload_config:
    flattened["max_upload_file_size_mb"] = upload_config["max_file_size_mb"]
if "min_quad_area_ratio" in upload_config:
    flattened["min_quad_area_ratio"] = upload_config["min_quad_area_ratio"]
```

- [ ] **Step 4: 修改 _validate_config**

在 `_validate_config` 函数末尾添加：

```python
max_size = config.get("max_upload_file_size_mb")
if not isinstance(max_size, int) or max_size <= 0:
    raise ValueError(f"max_upload_file_size_mb 必须为正整数，当前值: {max_size}")
ratio = config.get("min_quad_area_ratio")
if not isinstance(ratio, (int, float)) or not (0 < ratio < 1):
    raise ValueError(f"min_quad_area_ratio 必须在 (0, 1) 区间内，当前值: {ratio}")
```

- [ ] **Step 5: 更新 default.yaml**

```yaml
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
```

- [ ] **Step 6: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_config.py -v
```

- [ ] **Step 7: 提交**

```bash
git add app/backend/config.py app/config/default.yaml app/backend/tests/test_config.py
git commit -m "feat: 新增上传配置项 max_upload_file_size_mb 和 min_quad_area_ratio"
```

---

## 阶段二：file_validator — 文件安全校验

### Task 4: 实现 FileValidator 真实类型检测与大小校验（TDD）

**Files:**
- Create: `app/backend/services/file_validator.py`
- Create: `app/backend/tests/test_file_validator.py`

- [ ] **Step 1: 写 RED 测试**

创建 `test_file_validator.py`：

```python
import pytest
from app.backend.errors import AppError, ErrorCode


def _make_jpg_bytes():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100

def _make_png_bytes():
    return b'\x89PNG\r\n\x1a\n' + b'\x00' * 100

def _make_bmp_bytes():
    return b'BM' + b'\x00' * 100


def make_validator(max_size_mb=10):
    from app.backend.services.file_validator import FileValidator
    return FileValidator(max_size_mb=max_size_mb)


class TestMagicBytesDetection:
    def test_accepts_jpg_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_jpg_bytes())
        assert result["ext"] == "jpg"

    def test_accepts_png_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_png_bytes())
        assert result["ext"] == "png"

    def test_accepts_bmp_by_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_bmp_bytes())
        assert result["ext"] == "bmp"

    def test_rejects_pdf_by_magic_bytes(self):
        validator = make_validator()
        pdf_bytes = b'%PDF-1.4' + b'\x00' * 100
        with pytest.raises(AppError) as exc_info:
            validator.validate(pdf_bytes)
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code

    def test_rejects_text_file_with_jpg_extension(self):
        validator = make_validator()
        text_bytes = b'this is not an image file'
        with pytest.raises(AppError) as exc_info:
            validator.validate(text_bytes)
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code

    def test_generates_extension_from_magic_bytes(self):
        validator = make_validator()
        result = validator.validate(_make_png_bytes())
        assert result["ext"] == "png"


class TestFileSizeValidation:
    def test_rejects_file_exceeding_size_limit(self):
        validator = make_validator(max_size_mb=1)
        big = b'\xff\xd8\xff\xe0' + b'\x00' * (1024 * 1024 + 1)
        with pytest.raises(AppError) as exc_info:
            validator.validate(big)
        assert exc_info.value.code == ErrorCode.FILE_TOO_LARGE.code

    def test_file_size_at_boundary_accepted(self):
        validator = make_validator(max_size_mb=1)
        boundary = b'\xff\xd8\xff\xe0' + b'\x00' * (1024 * 1024 - 4)
        result = validator.validate(boundary)
        assert result["ext"] == "jpg"

    def test_empty_file_rejected(self):
        validator = make_validator(max_size_mb=1)
        with pytest.raises(AppError) as exc_info:
            validator.validate(b'')
        assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE.code
```

```bash
python -m pytest app/backend/tests/test_file_validator.py -v
# 预期: 全部 FAIL — ModuleNotFoundError
```

- [ ] **Step 2: 实现 FileValidator**

创建 `file_validator.py`：

```python
import os
import re

_MAGIC_BYTES = {
    b'\xff\xd8\xff': "jpg",
    b'\x89PNG': "png",
    b'BM': "bmp",
}
_MAX_HEADER_LEN = max(len(m) for m in _MAGIC_BYTES)
_SAFE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-_]+$')


class FileValidator:
    def __init__(self, max_size_mb: int = 10, base_dir: str = "data/pages"):
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._base_dir = base_dir

    def validate(self, data: bytes) -> dict:
        if len(data) == 0:
            from ..errors import AppError, ErrorCode
            raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
        if len(data) > self._max_size_bytes:
            from ..errors import AppError, ErrorCode
            raise AppError(ErrorCode.FILE_TOO_LARGE)
        header = data[:_MAX_HEADER_LEN]
        for magic, ext in _MAGIC_BYTES.items():
            if header.startswith(magic):
                return {"ext": ext}
        from ..errors import AppError, ErrorCode
        raise AppError(ErrorCode.UNSUPPORTED_FILE_TYPE)
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_file_validator.py -v
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/file_validator.py app/backend/tests/test_file_validator.py
git commit -m "feat: 实现 FileValidator 真实类型检测与大小校验"
```

---

### Task 5: FileValidator 路径安全校验（TDD 扩展）

**Files:**
- Modify: `app/backend/services/file_validator.py`
- Modify: `app/backend/tests/test_file_validator.py`

- [ ] **Step 1: 写 RED 测试**

在 `test_file_validator.py` 末尾追加：

```python
class TestPathSafety:
    def test_rejects_path_traversal(self):
        validator = make_validator()
        dangerous = ["../etc/passwd", "..\\windows", "sess/../etc", "~/root"]
        for sid in dangerous:
            with pytest.raises(ValueError):
                validator.build_path(sid, "abc123", "jpg")

    def test_rejects_null_byte(self):
        validator = make_validator()
        with pytest.raises(ValueError):
            validator.build_path("abc\x00def", "abc123", "jpg")

    def test_accepts_valid_ids(self):
        validator = make_validator()
        path = validator.build_path("550e8400-e29b-41d4-a716-446655440000",
                                     "660e8400-e29b-41d4-a716-446655440001", "jpg")
        assert path.endswith(".jpg")
        assert "550e8400" in path

    def test_relative_path_stays_within_pages_dir(self):
        validator = make_validator()
        path = validator.build_path("sess-1", "page-1", "png")
        assert ".." not in path
```

```bash
python -m pytest app/backend/tests/test_file_validator.py::TestPathSafety -v
# 预期: FAIL — AttributeError: 'FileValidator' object has no attribute 'build_path'
```

- [ ] **Step 2: 实现 build_path**

在 `FileValidator` 类中追加：

```python
def build_path(self, session_id: str, page_id: str, ext: str) -> str:
    """生成安全保存路径，拒绝路径穿越字符。返回相对路径。"""
    for value in (session_id, page_id, ext):
        if not _SAFE_ID_PATTERN.match(value):
            raise ValueError(f"非法路径字符")
    return os.path.join(self._base_dir, session_id, f"{page_id}.{ext}")
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_file_validator.py -v
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/file_validator.py app/backend/tests/test_file_validator.py
git commit -m "feat: FileValidator 新增 build_path 路径安全校验"
```

---

## 阶段三：quad_validator — 四点几何校验

### Task 6: 实现 QuadValidator（TDD）

**Files:**
- Create: `app/backend/services/quad_validator.py`
- Create: `app/backend/tests/test_quad_validator.py`

- [ ] **Step 1: 写 RED 测试**

创建 `test_quad_validator.py`：

```python
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
        # 对角线交叉
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
        # 仅 2 像素的四边形，不到 1920*1080*0.01
        pts = [[0, 0], [2, 0], [2, 1], [0, 1]]
        with pytest.raises(AppError) as exc_info:
            validate_quad_points(json.dumps(pts), 1920, 1080, 0.01)
        assert exc_info.value.code == ErrorCode.INVALID_QUAD_POINTS.code
```

```bash
python -m pytest app/backend/tests/test_quad_validator.py -v
# 预期: 全部 FAIL — ModuleNotFoundError
```

- [ ] **Step 2: 实现 QuadValidator**

创建 `quad_validator.py`：

```python
import json
import math


def validate_quad_points(
    quad_points_raw: str | None,
    image_width: int,
    image_height: int,
    min_area_ratio: float = 0.01,
) -> list | None:
    """校验 quad_points。合法返回坐标列表，缺失返回 None，非法抛出 AppError。"""
    if quad_points_raw is None or quad_points_raw == "":
        return None

    from ..errors import AppError, ErrorCode

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

    # 自相交检测：对角线 0-2 与 1-3 是否交叉
    if _segments_intersect(points[0], points[2], points[1], points[3]):
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
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_quad_validator.py -v
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/quad_validator.py app/backend/tests/test_quad_validator.py
git commit -m "feat: 实现 QuadValidator 四点几何校验"
```

---

## 阶段四：page_service — 协调层

### Task 7: 实现 PageService（TDD）

**Files:**
- Create: `app/backend/services/page_service.py`
- Create: `app/backend/tests/test_page_service.py`

> 关键约束：`page_id` 和 `page_no` 来自 `SessionService.add_page()`，PageService 不自行生成。上传成功后通过 `attach_page_upload` 写回 `upload_ref`。文件保存失败不删除会话页面项（upload_ref 保持 null）。

- [ ] **Step 1: 写 RED 测试**

创建 `test_page_service.py`：

```python
import json
import os
import pytest
from datetime import datetime, timezone
from app.backend.storage.json_store import JsonStore


def _make_jpg():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


def make_page_service(tmp_path, max_size_mb=10):
    from app.backend.services.file_validator import FileValidator
    from app.backend.services.session_service import SessionService
    from app.backend.services.page_service import PageService

    store = JsonStore(str(tmp_path))
    ss = SessionService(store, ["192.168.1.5:8081"], 30)
    fv = FileValidator(max_size_mb=max_size_mb, base_dir="data/pages")
    return PageService(
        session_service=ss,
        file_validator=fv,
        store=store,
        storage_dir=str(tmp_path),
        min_quad_area_ratio=0.01,
    )


class TestPageService:
    def test_save_page_creates_image_file(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        # 文件应在 storage_dir 下拼接 data/pages/...
        full = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        assert os.path.isdir(full)
        files = os.listdir(full)
        assert any(f == f"{page_id}.jpg" for f in files)

    def test_save_page_creates_metadata_json(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        meta_dir = os.path.join(str(tmp_path), "data", "pages", session["session_id"])
        meta_path = os.path.join(meta_dir, f"{page_id}.json")
        assert os.path.isfile(meta_path)
        meta = json.loads(open(meta_path, encoding="utf-8").read())
        assert meta["page_id"] == page_id
        assert meta["image_width"] == 1920
        assert meta["image_height"] == 1080
        assert meta["processed_image_path"] is None

    def test_save_page_returns_page_dict(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["page_id"] == page_id
        assert result["session_id"] == session["session_id"]
        assert result["page_no"] == 1
        assert "original_image_path" in result
        assert result["uploaded_at"] is not None

    def test_page_id_and_page_no_from_session_service(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        ss.add_page(session["session_id"])
        updated = ss.add_page(session["session_id"])
        page2 = updated["pages"][-1]

        result = ps.save(session["session_id"], page2["page_id"], _make_jpg(), 1920, 1080)
        assert result["page_no"] == page2["page_no"]
        assert result["page_no"] == 2

    def test_upload_ref_written_back(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)

        current = ss.get(session["session_id"])
        assert current["pages"][0]["upload_ref"] is not None
        assert current["pages"][0]["upload_ref"].endswith(".json")

    def test_quad_points_null_when_not_provided(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["quad_points"] is None

    def test_quad_points_preserved_when_valid(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        quad = [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]
        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080,
                         quad_points_raw=json.dumps(quad))
        assert result["quad_points"] == quad

    def test_session_isolation_different_directories(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        s1 = ss.create()
        p1 = ss.add_page(s1["session_id"])["pages"][0]["page_id"]
        ps.save(s1["session_id"], p1, _make_jpg(), 1920, 1080)

        s2 = ss.create()
        p2 = ss.add_page(s2["session_id"])["pages"][0]["page_id"]
        ps.save(s2["session_id"], p2, _make_jpg(), 1920, 1080)

        d1 = os.path.join(str(tmp_path), "data", "pages", s1["session_id"])
        d2 = os.path.join(str(tmp_path), "data", "pages", s2["session_id"])
        assert d1 != d2
        assert os.path.isdir(d1)
        assert os.path.isdir(d2)

    def test_processed_image_path_is_null(self, tmp_path):
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        result = ps.save(session["session_id"], page_id, _make_jpg(), 1920, 1080)
        assert result["processed_image_path"] is None

    def test_image_width_height_must_be_positive(self, tmp_path):
        from app.backend.errors import AppError, ErrorCode
        ps = make_page_service(tmp_path)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        with pytest.raises(AppError) as exc_info:
            ps.save(session["session_id"], page_id, _make_jpg(), 0, 1080)
        assert exc_info.value.code == ErrorCode.INVALID_REQUEST_PARAMS.code

    def test_file_save_failure_keeps_upload_ref_null(self, tmp_path):
        from app.backend.errors import AppError
        ps = make_page_service(tmp_path, max_size_mb=1)
        ss = ps._session_service
        session = ss.create()
        page_id = ss.add_page(session["session_id"])["pages"][0]["page_id"]

        big = b'\xff\xd8\xff\xe0' + b'\x00' * (2 * 1024 * 1024)
        try:
            ps.save(session["session_id"], page_id, big, 1920, 1080)
        except AppError:
            pass

        current = ss.get(session["session_id"])
        page = current["pages"][0]
        assert page["page_id"] == page_id
        assert page["upload_ref"] is None
```

```bash
python -m pytest app/backend/tests/test_page_service.py -v
# 预期: 全部 FAIL — ModuleNotFoundError
```

- [ ] **Step 2: 实现 PageService**

创建 `page_service.py`：

```python
import json
import os
from datetime import datetime, timezone

from .file_validator import FileValidator
from .quad_validator import validate_quad_points
from ..errors import AppError, ErrorCode
from ..storage.json_store import JsonStore


class PageService:
    def __init__(
        self,
        session_service,
        file_validator: FileValidator,
        store: JsonStore,
        storage_dir: str,
        min_quad_area_ratio: float = 0.01,
    ):
        self._session_service = session_service
        self._file_validator = file_validator
        self._store = store
        self._storage_dir = storage_dir
        self._min_quad_area_ratio = min_quad_area_ratio

    def save(
        self,
        session_id: str,
        page_id: str,
        image_data: bytes,
        image_width: int,
        image_height: int,
        quad_points_raw: str | None = None,
    ) -> dict:
        if not isinstance(image_width, int) or image_width <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS,
                           message="image_width 必须为正整数")
        if not isinstance(image_height, int) or image_height <= 0:
            raise AppError(ErrorCode.INVALID_REQUEST_PARAMS,
                           message="image_height 必须为正整数")

        validation = self._file_validator.validate(image_data)
        ext = validation["ext"]

        quad_points = validate_quad_points(
            quad_points_raw, image_width, image_height, self._min_quad_area_ratio
        )

        # 从会话取 page_no
        session = self._session_service.get(session_id)
        page = next(p for p in session["pages"] if p["page_id"] == page_id)

        rel_path = self._file_validator.build_path(session_id, page_id, ext)

        # 写入文件（用 storage_dir 拼绝对路径）
        abs_image_path = os.path.join(self._storage_dir, rel_path)
        os.makedirs(os.path.dirname(abs_image_path), exist_ok=True)
        with open(abs_image_path, "wb") as f:
            f.write(image_data)

        # 元数据写入
        meta = {
            "page_id": page_id,
            "session_id": session_id,
            "page_no": page["page_no"],
            "original_image_path": abs_image_path,
            "processed_image_path": None,
            "image_width": image_width,
            "image_height": image_height,
            "quad_points": quad_points,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        meta_rel = self._file_validator.build_path(session_id, page_id, "json")
        abs_meta_path = os.path.join(self._storage_dir, meta_rel)
        with open(abs_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 写回 upload_ref
        self._session_service.attach_page_upload(session_id, page_id, abs_meta_path)

        return meta
```

- [ ] **Step 3: 运行测试确认 GREEN**

```bash
python -m pytest app/backend/tests/test_page_service.py -v
```

- [ ] **Step 4: 提交**

```bash
git add app/backend/services/page_service.py app/backend/tests/test_page_service.py
git commit -m "feat: 实现 PageService 上传协调与元数据持久化"
```

---

## 阶段五：路由 + 集成

### Task 8: 实现 POST /api/mobile/{session_id}/pages 端点（TDD）

**Files:**
- Modify: `app/backend/routes/mobile.py`
- Modify: `app/backend/__init__.py`
- Create: `app/backend/tests/test_mobile_pages.py`

- [ ] **Step 1: 注册 PageService 到 app 工厂**

在 `__init__.py` 的 `create_backend_app()` 中，`SessionService` 注册之后添加：

```python
from .services.file_validator import FileValidator
from .services.page_service import PageService

session_service = app.config["SESSION_SERVICE"]
file_validator = FileValidator(
    max_size_mb=config["max_upload_file_size_mb"],
    base_dir="data/pages",
)
page_service = PageService(
    session_service=session_service,
    file_validator=file_validator,
    store=store,
    storage_dir=config["storage_dir"],
    min_quad_area_ratio=config["min_quad_area_ratio"],
)
app.config["PAGE_SERVICE"] = page_service
```

- [ ] **Step 2: 在 mobile.py 新增端点**

在 `routes/mobile.py` 中追加。注意：需要在文件顶部 `from flask import Blueprint, current_app` 增加 `request`：

```python
from flask import Blueprint, current_app, request
```

然后追加端点：

```python
from flask import request
from ..responses import success


@mobile_bp.route("/api/mobile/<session_id>/pages", methods=["POST"])
def upload_page(session_id: str):
    """上传图片页面到指定会话。"""
    page_service = current_app.config["PAGE_SERVICE"]
    session_service = current_app.config["SESSION_SERVICE"]

    if "image" not in request.files:
        from ..errors import AppError, ErrorCode
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image 文件")

    image_file = request.files["image"]
    image_data = image_file.read()

    image_width_str = request.form.get("image_width")
    image_height_str = request.form.get("image_height")
    if not image_width_str or not image_height_str:
        from ..errors import AppError, ErrorCode
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="缺少 image_width 或 image_height")

    try:
        image_width = int(image_width_str)
        image_height = int(image_height_str)
    except (ValueError, TypeError):
        from ..errors import AppError, ErrorCode
        raise AppError(ErrorCode.INVALID_REQUEST_PARAMS, message="image_width 和 image_height 必须为整数")

    quad_points_raw = request.form.get("quad_points")

    # 创建会话页面项（含 active/expired/locked guard）
    updated = session_service.add_page(session_id, upload_ref=None)
    page = updated["pages"][-1]

    result = page_service.save(
        session_id=session_id,
        page_id=page["page_id"],
        image_data=image_data,
        image_width=image_width,
        image_height=image_height,
        quad_points_raw=quad_points_raw,
    )

    return success(data=result, status=201)
```

- [ ] **Step 3: 写集成测试**

创建 `test_mobile_pages.py`：

```python
import io
import json
import os
import pytest
from app.backend.__init__ import create_backend_app


def _make_jpg():
    return b'\xff\xd8\xff\xe0' + b'\x00' * 100


@pytest.fixture
def client(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text("""
app:
  version: "0.1.0"
server:
  bind_host: "0.0.0.0"
  port: 8081
paths:
  data_dir: "./data"
  log_dir: "./logs"
  export_dir: "./exports"
  model_dir: "./models"
sessions:
  capture_session_ttl_minutes: 30
upload:
  max_file_size_mb: 10
  min_quad_area_ratio: 0.01
""", encoding="utf-8")

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    old_cwd = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        app = create_backend_app(str(config_dir))
        app.config["TESTING"] = True
        yield app.test_client()
    finally:
        os.chdir(old_cwd)


def _create_session(client):
    resp = client.post("/api/capture-sessions")
    assert resp.status_code == 201
    return resp.get_json()["data"]["session_id"]


class TestMobilePages:
    def test_upload_page_returns_201(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(
            f"/api/mobile/{sid}/pages",
            data=data,
            content_type="multipart/form-data",
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["page_id"]
        assert body["data"]["page_no"] == 1

    def test_upload_without_quad_points_returns_201(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 201
        assert resp.get_json()["data"]["quad_points"] is None

    def test_upload_rejects_non_image_file(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(b'%PDF-1.4 fake pdf'), "doc.pdf"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    def test_upload_rejects_oversized_file(self, client):
        sid = _create_session(client)
        big = b'\xff\xd8\xff\xe0' + b'\x00' * (11 * 1024 * 1024)
        data = {
            "image": (io.BytesIO(big), "big.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "FILE_TOO_LARGE"

    def test_upload_rejects_invalid_quad_points(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
            "quad_points": "not json",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_QUAD_POINTS"

    def test_upload_missing_image_returns_400(self, client):
        sid = _create_session(client)
        data = {"image_width": "1920", "image_height": "1080"}
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"

    def test_upload_missing_dimensions_returns_400(self, client):
        sid = _create_session(client)
        data = {"image": (io.BytesIO(_make_jpg()), "test.jpg")}
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "INVALID_REQUEST_PARAMS"

    def test_upload_nonexistent_session_returns_404(self, client):
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post("/api/mobile/nonexistent/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 404

    def test_upload_session_page_has_upload_ref(self, client):
        sid = _create_session(client)
        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 201

        # 查会话确认 upload_ref 已写回
        info = client.get(f"/api/capture-sessions/{sid}")
        pages = info.get_json()["data"]["pages"]
        assert len(pages) == 1
        assert pages[0]["upload_ref"] is not None

    def test_upload_locked_session_returns_409(self, client):
        sid = _create_session(client)
        client.post(f"/api/mobile/{sid}/finish")

        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 409
        assert resp.get_json()["error"]["code"] == "SESSION_LOCKED"

    def test_upload_expired_session_returns_409(self, client):
        sid = _create_session(client)
        import os as _os
        path = _os.path.join(_os.getcwd(), "data", "sessions", f"{sid}.json")
        session = json.loads(open(path, encoding="utf-8").read())
        session["expires_at"] = "2020-01-01T00:00:00+00:00"
        open(path, "w", encoding="utf-8").write(json.dumps(session))

        data = {
            "image": (io.BytesIO(_make_jpg()), "test.jpg"),
            "image_width": "1920",
            "image_height": "1080",
        }
        resp = client.post(f"/api/mobile/{sid}/pages", data=data,
                           content_type="multipart/form-data")
        assert resp.status_code == 409
```

- [ ] **Step 3: 运行集成测试确认 RED**

```bash
python -m pytest app/backend/tests/test_mobile_pages.py -v
# 预期: FAIL — 端点不存在或 PageService 未注册
```

- [ ] **Step 4: 实现路由 + app 工厂注册后运行确认 GREEN**

```bash
python -m pytest app/backend/tests/test_mobile_pages.py -v
```

- [ ] **Step 5: 运行全部测试确认无回归**

```bash
python -m pytest app/backend/tests/ -v
```

- [ ] **Step 6: 提交**

```bash
git add app/backend/routes/mobile.py app/backend/__init__.py app/backend/tests/test_mobile_pages.py
git commit -m "feat: 实现 POST /api/mobile/{session_id}/pages 图片上传端点"
```

---

## 阶段六：收尾验证

### Task 9: 全量回归测试 + 检查

- [ ] **Step 1: 运行全量测试**

```bash
cd /home/kbzz1/manzufei_ocr/.claude/worktrees/backend-file-upload
python -m pytest app/backend/tests/ -v
```

预期：全部 PASS，无回归。

- [ ] **Step 2: 对照 spec 检查覆盖**

对照 `docs/superpowers/specs/2026-05-12-file-upload-design.md` 逐项确认：

| 需求 | 覆盖测试 |
|------|----------|
| 真实类型检测 jpg/png/bmp | test_file_validator.py |
| 拒绝非图片文件 | test_file_validator.py + test_mobile_pages.py |
| 文件大小限制 | test_file_validator.py + test_mobile_pages.py |
| 路径安全防穿越 | test_file_validator.py |
| quad_points 4点/数字/范围/自相交/面积 | test_quad_validator.py |
| quad_points 缺失保存 null | test_page_service.py + test_mobile_pages.py |
| 上传不调用算法模块 | test_page_service.py (processed_image_path is None) |
| 图片保存 + 元数据持久化 | test_page_service.py |
| page_id/page_no 来自 SessionService | test_page_service.py |
| upload_ref 写回 | test_page_service.py + test_mobile_pages.py |
| 会话状态 guard (404/409) | test_mobile_pages.py |
| 缺失参数返回 INVALID_REQUEST_PARAMS | test_mobile_pages.py |

- [ ] **Step 3: 提交收尾**

```bash
git commit --allow-empty -m "chore: PR-BE-003 图片上传与文件管理 A-lite 实现完成"
```
