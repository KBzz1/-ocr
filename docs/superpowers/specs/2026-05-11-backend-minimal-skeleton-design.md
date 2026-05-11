# 后端最小骨架设计

## 范围

本地服务启动、配置加载、健康检查、统一错误响应、状态枚举。对应 TDD 实施顺序第 1 步（状态机 + 错误码 + 统一响应）和第 2 步（系统启动）。

## 技术选型

| 项 | 选择 |
|----|------|
| Web 框架 | Flask |
| 配置格式 | YAML（default.yaml + local.yaml 覆盖） |
| 持久化 | JSON 文件存储（storage/json_store.py） |

## 目录结构

```
app/backend/
├── __init__.py              # create_backend_app() 工厂
├── main.py                  # 开发/调试入口
├── config.py                # 配置加载（YAML + 默认值 + 合并）
├── enums.py                 # 状态枚举（任务/会话/字段 + 状态流转）
├── errors.py                # ErrorCode 枚举、AppError 异常、全局 errorhandler
├── responses.py             # success() / error_response() helper
├── routes/
│   ├── __init__.py
│   └── system.py            # system_bp: GET /api/system/status
├── storage/
│   ├── __init__.py
│   └── json_store.py        # JsonStore(base_dir)，原子写入
└── tests/
    ├── __init__.py
    ├── test_config.py
    ├── test_enums.py
    ├── test_errors.py
    └── test_system.py
```

```
app/config/
├── default.yaml             # 提交的默认配置
└── local.yaml               # 本地覆盖（gitignore）
```

## 模块接口契约

### config.py

```python
def load_config(config_dir: str | None = None) -> dict:
    """加载配置，合并: 硬编码默认值 < default.yaml < local.yaml(可选)。

    返回 dict 包含:
    - bind_host: 服务监听地址（0.0.0.0 允许局域网访问）
    - local_host: 本地回环地址（127.0.0.1）
    - port: 端口号
    - data_dir / log_dir / model_dir: 归一化为绝对路径
    - version: 应用版本号
    - storage_dir / export_dir: 存储与导出路径

    校验:
    - port 范围为 1024-65535
    - data_dir/log_dir 路径可写性
    - 缺失配置文件时使用安全默认值继续启动
    """
```

### enums.py

继承 `docs/Shared/state-enums.md`，每个状态枚举包含合法流转校验。

```python
class TaskStatus(Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    CONFIRMED = "confirmed"
    EXPORTED = "exported"
    FAILED = "failed"

    @classmethod
    def allowed_transitions(cls, current: "TaskStatus") -> list["TaskStatus"]
    @classmethod
    def is_valid_transition(cls, current: "TaskStatus", target: "TaskStatus") -> bool

class SessionStatus(Enum):
    # active, expired, locked, cancelled
    # 同上方法

class FieldStatus(Enum):
    # unreviewed, confirmed, modified, suspicious, empty
```

### errors.py

```python
class ErrorCode(Enum):
    SESSION_NOT_FOUND = ("SESSION_NOT_FOUND", 404)
    SESSION_EXPIRED = ("SESSION_EXPIRED", 409)
    SESSION_LOCKED = ("SESSION_LOCKED", 409)
    UNSUPPORTED_FILE_TYPE = ("UNSUPPORTED_FILE_TYPE", 400)
    FILE_TOO_LARGE = ("FILE_TOO_LARGE", 400)
    INVALID_QUAD_POINTS = ("INVALID_QUAD_POINTS", 400)
    TASK_NOT_FOUND = ("TASK_NOT_FOUND", 404)
    INVALID_TASK_TRANSITION = ("INVALID_TASK_TRANSITION", 400)
    REVIEW_VALIDATION_FAILED = ("REVIEW_VALIDATION_FAILED", 400)
    EXPORT_VALIDATION_FAILED = ("EXPORT_VALIDATION_FAILED", 400)
    EXPORT_FAILED = ("EXPORT_FAILED", 500)
    # 算法模块错误码（任务进入 failed，无固定 HTTP 状态码）
    ALGORITHM_MODULE_NOT_CONFIGURED = ("ALGORITHM_MODULE_NOT_CONFIGURED", 500)
    ALGORITHM_MODULE_FAILED = ("ALGORITHM_MODULE_FAILED", 500)
    ALGORITHM_CONTRACT_INVALID = ("ALGORITHM_CONTRACT_INVALID", 500)

class AppError(Exception):
    def __init__(self, error_code: ErrorCode, message: str = None, details: dict = None):
        self.code = error_code.code
        self.message = message or error_code.default_message
        self.http_status = error_code.http_status
        self.details = details or {}

def register_error_handlers(app: Flask):
    """注册全局 errorhandler，捕获 AppError 返回统一 JSON 结构。"""

def abort(error_code: ErrorCode, message: str = None, details: dict = None):
    """快捷抛出 AppError，被 errorhandler 捕获。"""
```

### responses.py

统一响应格式，遵循 `docs/Shared/error-codes.md`：

```python
# 成功响应
def success(data=None, status=200) -> Flask.Response:
    """{"success": true, "data": ...}"""

# 错误响应
def error_response(app_error: AppError) -> Flask.Response:
    """{"success": false, "error": {"code": "...", "message": "...", "details": {}}}"""
```

### storage/json_store.py

```python
class JsonStore:
    """基于本地目录的 JSON 文件读写工具。

    - 路径安全：relative_path 校验，拒绝 ../ 越权
    - 原子写入：先写 .tmp 临时文件，再 os.replace
    - 目录自动创建
    """

    def __init__(self, base_dir: str)
    def read(self, relative_path: str, default=None) -> dict | list
    def write(self, relative_path: str, data: dict | list)
    def delete(self, relative_path: str)
    def exists(self, relative_path: str) -> bool
```

### routes/system.py

```python
# Blueprint: system_bp, url_prefix 由 app 工厂决定

@system_bp.route("/api/system/status")
def get_system_status():
    """返回系统运行状态。

    Response:
    {
        "success": true,
        "data": {
            "status": "running",
            "version": "1.0.0",
            "started_at": "2026-05-11T12:00:00",
            "lan_addresses": ["192.168.1.100:8080"]
        }
    }
    """
```

### __init__.py

```python
def create_backend_app(config_dir: str | None = None) -> Flask:
    """轻量工厂：加载配置 → 创建 Flask app → 注册 Blueprint 和 errorhandler。

    允许测试层传入临时 config 目录，不依赖真实 app/config/。
    """
```

## 数据流

```
启动 main.py
  → create_backend_app()
    → load_config() → 合并 YAML
    → Flask(__name__)
    → register_error_handlers(app)
    → app.register_blueprint(system_bp)
  → app.run(bind_host, port)

请求 GET /api/system/status
  → system_bp.get_system_status()
    → responses.success({...})
      → flask.jsonify({"success": true, "data": {...}})

异常路径：
  任意路由层 raise AppError / abort()
    → Flask errorhandler
      → responses.error_response(app_error)
        → flask.jsonify({"success": false, "error": {...}})
```

## 配置加载策略

```
硬编码默认值 (config.py 内置)
  ↓ 被覆盖
app/config/default.yaml (提交)
  ↓ 被覆盖
app/config/local.yaml (可选，gitignore)
```

- 不配置 `app/config/` 目录 → 全用默认值 + warning 日志
- 有 `default.yaml` 缺 `local.yaml` → 正常启动
- 目录存在但 `default.yaml` 缺失 → 用默认值 + warning

## 测试策略

遵循 TDD 流程：先写测试 → RED → 实现 → GREEN → 重构。

| 测试文件 | 测试目标 | 对应 TDD ID |
|----------|----------|-------------|
| test_enums.py | 状态枚举值正确、状态流转合法/非法 | 实施顺序 #1 |
| test_errors.py | ErrorCode 正确、AppError 属性、响应 JSON 结构 | BE-API-002 |
| test_config.py | 默认值、YAML 加载、合并覆盖、路径归一化 | 实施顺序 #2 |
| test_system.py | GET /api/system/status 返回 200 和正确结构 | BE-SYS-001, BE-SYS-002 |

## 不在此阶段实现

- 采集会话 CRUD
- 文件上传与校验
- 任务生命周期
- 算法端口适配器
- 审核结果持久化
- 导出功能
- LAN 地址自动发现（system status 中 lan_addresses 第一阶段写空列表）
