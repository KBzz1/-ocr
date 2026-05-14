# 手机连接修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现单端口 8081 同源生产链路：Flask 托管前端 dist 静态文件 + API，手机扫码直连 8081 无需 CORS；Vite 5173 仅开发兜底。

**Architecture:** 后端修正二维码 URL → `/mobile/sessions/{id}`；`before_request` 钩子区分 API/静态资源/SPA 路由；前端 `buildQrCodeUrl()` 纯函数在 DEV 模式转换端口，生产模式原样透传；Vite 加 `allowedHosts: true`。

**Tech Stack:** Python 3.12 via conda env `manzufei_ocr`, Flask + Werkzeug `safe_join`, pytest, React + Vitest, Vite 6

---

## 范围边界

本计划覆盖 NW-001 ~ NW-012 全部 12 个 spec 需求，映射为 19 个后端测试 + 5 个前端测试 + 2 个启动脚本测试。

本计划不覆盖：
- flask-cors 安装
- Windows 防火墙配置
- 手机端拍照、上传、四边形框选逻辑变更
- 后端 API 业务逻辑变更

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/backend/services/session_service.py:21` | 修改 | 二维码 URL 改为 `/mobile/sessions/{id}` |
| `app/backend/config.py` | 修改 | 新增 `static_dir` 默认值 + flatten + normalize + validate |
| `app/backend/__init__.py` | 修改 | 注册 `_serve_spa` before_request 钩子 |
| `app/config/default.yaml` | 修改 | 新增 `paths.static_dir` 占位 |
| `app/backend/tests/test_capture_session.py` | 修改 | 修正 qr_code_url 断言 |
| `app/backend/tests/test_config.py` | 修改 | 新增 static_dir 配置测试 |
| `app/backend/tests/test_static_serve.py` | 新建 | 静态文件托管 + SPA fallback 全用例 |
| `app/frontend/src/api/captureSessions.ts` | 修改 | 新增 `buildQrCodeUrl()` 纯函数 + `BuildQrCodeUrlOptions` |
| `app/frontend/src/api/captureSessions.test.ts` | 新建 | `buildQrCodeUrl()` 单元测试 |
| `app/frontend/vite.config.ts` | 修改 | 新增 `allowedHosts: true` |
| `app/frontend/src/app/App.test.tsx` | 修改 | 二维码 URL 断言更新 |
| `run.bat` | 修改 | 浏览器打开 `http://127.0.0.1:8081/` |
| `app/backend/tests/test_windows_startup_scripts.py` | 修改 | run.bat 入口 + 健康检查断言 |

---

### Task 1: 修正后端二维码 URL

**Files:**
- Modify: `app/backend/services/session_service.py:21`
- Modify: `app/backend/tests/test_capture_session.py:63`

- [ ] **Step 1: 修改测试断言，验证新 URL 格式**

在 `test_capture_session.py` 第 63 行，修改 `test_create_session_returns_201_with_qr_url` 中的断言：

```python
# 修改前
assert data["qr_code_url"].startswith("http://192.168.1.5:8081/mobile/")

# 修改后
assert data["qr_code_url"].startswith("http://192.168.1.5:8081/mobile/sessions/")
```

- [ ] **Step 2: 运行测试验证失败**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py::TestCaptureSessionAPI::test_create_session_returns_201_with_qr_url -v
```

Expected: FAIL — 实际返回 `/mobile/` 但断言期望 `/mobile/sessions/`

- [ ] **Step 3: 修正 session_service.py**

将 `app/backend/services/session_service.py` 第 21 行：

```python
# 修改前
qr_code_url = f"http://{self._lan_addresses[0]}/mobile/{session_id}"

# 修改后
qr_code_url = f"http://{self._lan_addresses[0]}/mobile/sessions/{session_id}"
```

- [ ] **Step 4: 运行测试验证通过**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_capture_session.py -v
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/services/session_service.py app/backend/tests/test_capture_session.py
git commit -m "修正二维码 URL 为 /mobile/sessions/{id} 格式"
```

---

### Task 2: 增加 static_dir 配置

**Files:**
- Modify: `app/backend/config.py`
- Modify: `app/config/default.yaml`
- Modify: `app/backend/tests/test_config.py`

- [ ] **Step 1: DEFAULT_CONFIG 增加 static_dir**

在 `app/backend/config.py` 的 `DEFAULT_CONFIG` dict 中，`"export_dir"` 之后新增一行：

```python
"static_dir": "./app/frontend/dist",
```

- [ ] **Step 2: _flatten_config 支持 paths.static_dir**

在 `app/backend/config.py` 的 `_flatten_config()` 函数中，`paths_config` 解析部分，`"export_dir"` 处理之后新增：

```python
if "static_dir" in paths_config:
    flattened["static_dir"] = paths_config["static_dir"]
```

- [ ] **Step 3: _normalize_paths 纳入 static_dir**

在 `app/backend/config.py` 的 `_normalize_paths()` 函数中，`for key in (...)` 元组里加上 `"static_dir"`：

```python
for key in ("data_dir", "log_dir", "model_dir", "storage_dir", "export_dir", "static_dir"):
```

- [ ] **Step 4: _validate_config 对 static_dir 不做创建校验**

`_validate_config()` 中 `for key in ("data_dir", "log_dir", "storage_dir", "export_dir"):` 不变（不包含 `static_dir`），因为它是构建产物目录，缺失时静态路由返回受控 404。

- [ ] **Step 5: default.yaml 增加 paths.static_dir 占位**

在 `app/config/default.yaml` 的 `paths:` 段，`model_dir` 之后新增：

```yaml
  static_dir: "./app/frontend/dist"
```

- [ ] **Step 6: 编写配置测试**

在 `app/backend/tests/test_config.py` 末尾新增测试函数：

```python
def test_static_dir_default_normalized(tmp_path):
    """static_dir 默认值归一化为项目内 app/frontend/dist"""
    from app.backend.config import load_config
    config = load_config(str(tmp_path / "nonexistent"))
    assert "static_dir" in config
    assert os.path.isabs(config["static_dir"])
    assert config["static_dir"].endswith(os.path.join("app", "frontend", "dist"))


def test_static_dir_overridable_via_local_yaml(tmp_path):
    """paths.static_dir 可通过 local.yaml 覆盖"""
    import yaml
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default = {"paths": {"static_dir": "./app/frontend/dist"}}
    local = {"paths": {"static_dir": "./custom_dist"}}
    with open(config_dir / "default.yaml", "w") as f:
        yaml.dump(default, f)
    with open(config_dir / "local.yaml", "w") as f:
        yaml.dump(local, f)

    from app.backend.config import load_config
    config = load_config(str(config_dir))
    assert os.path.isabs(config["static_dir"])
    assert config["static_dir"].endswith("custom_dist")
```

- [ ] **Step 7: 运行配置测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_config.py -v
```

Expected: 全部 PASS（含新增的 2 个测试）

- [ ] **Step 8: Commit**

```bash
git add app/backend/config.py app/config/default.yaml app/backend/tests/test_config.py
git commit -m "新增 static_dir 配置项，支持 YAML 覆盖和路径归一化"
```

---

### Task 3: 实现静态文件托管 + SPA fallback

**Files:**
- Modify: `app/backend/__init__.py`
- Create: `app/backend/tests/test_static_serve.py`

- [ ] **Step 1: 编写 test_static_serve.py 全部测试**

创建 `app/backend/tests/test_static_serve.py`：

```python
"""NW-002 ~ NW-008: 静态文件托管 + SPA fallback 测试。"""
import os
import pytest


@pytest.fixture
def static_app(tmp_path, monkeypatch):
    """创建带 static_dir 的测试 app，包含模拟 dist 目录。"""
    from app.backend import create_backend_app

    # 构建模拟 dist
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text(
        "<!DOCTYPE html><html><head><title>工作台</title></head><body>App</body></html>",
        encoding="utf-8",
    )
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('hello');", encoding="utf-8")

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "default.yaml").write_text(
        f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
  static_dir: "{dist_dir}"
sessions:
  capture_session_ttl_minutes: 30
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
    app = create_backend_app(config_dir=str(config_dir))
    app.config["TESTING"] = True
    return app


@pytest.fixture
def static_client(static_app):
    return static_app.test_client()


class TestStaticServe:
    """BE-NW-002 ~ BE-NW-008"""

    def test_root_returns_html_not_json(self, static_client):
        """BE-NW-002: GET / 返回 HTML，Content-Type 为 text/html"""
        resp = static_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"<!DOCTYPE html>" in resp.data

    def test_mobile_session_returns_spa(self, static_client):
        """BE-NW-003: GET /mobile/sessions/{id} 返回 SPA index.html"""
        resp = static_client.get("/mobile/sessions/abc-123")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert b"<!DOCTYPE html>" in resp.data

    def test_api_status_not_eaten_by_fallback(self, static_client):
        """BE-NW-004: GET /api/system/status 不被 fallback 吃掉"""
        resp = static_client.get("/api/system/status")
        assert resp.status_code == 200
        assert resp.is_json
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"

    def test_api_not_exists_returns_json_404(self, static_client):
        """BE-NW-005: GET /api/not-exists 返回 API JSON 404"""
        resp = static_client.get("/api/not-exists")
        assert resp.status_code == 404
        assert resp.is_json
        data = resp.get_json()
        assert data["error"]["code"] == "REQUEST_NOT_FOUND"

    def test_missing_asset_returns_404_not_html(self, static_client):
        """BE-NW-006: GET /assets/missing.js 返回 404，不返回 index.html"""
        resp = static_client.get("/assets/missing.js")
        assert resp.status_code == 404

    def test_existing_asset_returns_file(self, static_client):
        """BE-NW-007: GET /assets/app.js 存在时返回静态文件"""
        resp = static_client.get("/assets/app.js")
        assert resp.status_code == 200
        assert b"console.log" in resp.data

    def test_root_without_dist_returns_json_404(self, tmp_path, monkeypatch):
        """BE-NW-008: GET / 在 dist/index.html 缺失时返回统一 JSON 404"""
        from app.backend import create_backend_app

        empty_dist = tmp_path / "empty_dist"
        empty_dist.mkdir()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "default.yaml").write_text(
            f"""
app:
  version: "test"
server:
  bind_host: "127.0.0.1"
  port: 8081
paths:
  data_dir: "{tmp_path}"
  log_dir: "{tmp_path}/logs"
  storage_dir: "{tmp_path}"
  export_dir: "{tmp_path}/exports"
  static_dir: "{empty_dist}"
sessions:
  capture_session_ttl_minutes: 30
""",
            encoding="utf-8",
        )

        monkeypatch.setattr("app.backend._get_lan_addresses", lambda port: ["192.168.1.5:8081"])
        app = create_backend_app(config_dir=str(config_dir))
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.get("/")
        assert resp.status_code == 404
        assert resp.is_json
        data = resp.get_json()
        assert data["error"]["code"] == "REQUEST_NOT_FOUND"
```

- [ ] **Step 2: 运行测试验证全部失败**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_static_serve.py -v
```

Expected: 全部 FAIL（`_register_static_serve` 尚未实现）

- [ ] **Step 3: 实现 _register_static_serve 并注册到 app**

在 `app/backend/__init__.py` 的 `create_backend_app()` 函数中，在 `register_error_handlers(app)` 之后、blueprint 注册之前插入 `_register_static_serve` 的调用：

```python
# 在 create_backend_app() 中 register_error_handlers(app) 之后新增:
_register_static_serve(app, config["static_dir"])
```

在 `create_backend_app()` 函数之前（文件顶部）新增辅助函数：

```python
import os
from flask import request, send_from_directory, send_file
from werkzeug.exceptions import NotFound
from werkzeug.utils import safe_join


def _register_static_serve(app, static_dir):
    """注册静态文件服务 + SPA fallback。

    路由优先级（高到低）：
    1. /api/* → Blueprint 路由（before_request 返回 None）
    2. 带扩展名静态资源 → 存在则 served，不存在则 Werkzeug 404
    3. 无扩展名 SPA 路由 → 返回 index.html
    4. index.html 缺失 → 受控 JSON 404
    """
    from .responses import error_response
    from .errors import AppError, ErrorCode

    @app.before_request
    def _serve_spa():
        if request.path.startswith("/api/"):
            return None

        relative_path = request.path.lstrip("/") or "index.html"
        file_path = safe_join(static_dir, relative_path)
        if file_path is None:
            raise NotFound()

        if os.path.splitext(request.path)[1]:
            if os.path.isfile(file_path):
                return send_from_directory(static_dir, relative_path)
            raise NotFound()

        index_path = safe_join(static_dir, "index.html")
        if index_path and os.path.isfile(index_path):
            return send_file(index_path)

        return error_response(AppError(ErrorCode.REQUEST_NOT_FOUND))
```

- [ ] **Step 4: 运行测试验证全部通过**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_static_serve.py -v
```

Expected: 全部 7 个测试 PASS

- [ ] **Step 5: 运行全部后端测试确认无回归**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -v
```

Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/backend/__init__.py app/backend/tests/test_static_serve.py
git commit -m "新增 Flask 静态文件托管 + SPA fallback，/api/* 不受影响"
```

---

### Task 4: 确认 lan_addresses 过滤逻辑

**Files:**
- 仅确认: `app/backend/tests/test_windows_startup_scripts.py`（已有测试）

- [ ] **Step 1: 运行现有 lan_addresses 测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py -v -k "lan_addresses"
```

Expected: `test_lan_addresses_excludes_localhost` 和 `test_status_contains_required_fields` PASS（已有测试覆盖 BE-NW-010）

- [ ] **Step 2: 确认即可，无需代码变更**

该测试已在 Task 3 回归测试中验证通过。如果通过，无需 commit。

---

### Task 5: 前端 buildQrCodeUrl 纯函数 + 单元测试

**Files:**
- Modify: `app/frontend/src/api/captureSessions.ts`
- Create: `app/frontend/src/api/captureSessions.test.ts`

- [ ] **Step 1: 编写 captureSessions.test.ts**

创建 `app/frontend/src/api/captureSessions.test.ts`：

```typescript
import { describe, it, expect } from 'vitest';
import { buildQrCodeUrl, type CaptureSession } from './captureSessions';

const baseSession: CaptureSession = {
  session_id: 'abc-123',
  status: 'active',
  created_at: '2026-05-14T00:00:00Z',
  expires_at: '2026-05-14T00:30:00Z',
  qr_code_url: 'http://192.168.1.5:8081/mobile/sessions/abc-123',
  page_count: 0,
};

describe('buildQrCodeUrl', () => {
  it('FE-NW-001: 生产模式原样返回后端 URL', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: false,
      currentHref: 'http://localhost:8081/',
    });
    expect(result).toBe('http://192.168.1.5:8081/mobile/sessions/abc-123');
  });

  it('FE-NW-002: 开发模式将端口转为 Vite origin', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: true,
      currentHref: 'http://192.168.1.5:5173/',
    });
    expect(result).toBe('http://192.168.1.5:5173/mobile/sessions/abc-123');
  });

  it('开发模式保留当前 origin 的 hostname 和 port', () => {
    const result = buildQrCodeUrl(baseSession, {
      isDev: true,
      currentHref: 'http://10.0.0.99:3000/some-page',
    });
    expect(result).toBe('http://10.0.0.99:3000/mobile/sessions/abc-123');
  });

  it('session_id 含特殊字符时正确编码', () => {
    const session: CaptureSession = {
      ...baseSession,
      session_id: 'abc/123?x=1',
      qr_code_url: 'http://192.168.1.5:8081/mobile/sessions/abc/123?x=1',
    };
    const result = buildQrCodeUrl(session, {
      isDev: false,
      currentHref: 'http://localhost:8081/',
    });
    expect(result).toBe('http://192.168.1.5:8081/mobile/sessions/abc/123?x=1');
  });
});
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd app/frontend && npx vitest run src/api/captureSessions.test.ts
```

Expected: FAIL — `buildQrCodeUrl` 尚未导出

- [ ] **Step 3: 修改 captureSessions.ts — 新增纯函数**

在 `app/frontend/src/api/captureSessions.ts` 中，`finishCaptureSession()` 之前新增：

```typescript
export interface BuildQrCodeUrlOptions {
  isDev: boolean;
  currentHref: string;
}

export function buildQrCodeUrl(
  session: CaptureSession,
  options: BuildQrCodeUrlOptions
): string {
  if (options.isDev) {
    const frontendUrl = new URL(options.currentHref);
    frontendUrl.pathname = `/mobile/sessions/${encodeURIComponent(session.session_id)}`;
    frontendUrl.search = '';
    frontendUrl.hash = '';
    return frontendUrl.toString();
  }
  return session.qr_code_url;
}
```

并修改 `createCaptureSession()` 函数：

```typescript
export async function createCaptureSession() {
  const session = await apiRequest<CaptureSession>('/api/capture-sessions', { method: 'POST' });
  assertMobileQrUrl(session);
  return {
    ...session,
    qr_code_url: buildQrCodeUrl(session, {
      isDev: import.meta.env.DEV,
      currentHref: window.location.href
    })
  };
}
```

同时删除旧的 `buildFrontendMobileUrl()` 函数（第 49-57 行）。

- [ ] **Step 4: 运行测试验证通过**

```bash
cd app/frontend && npx vitest run src/api/captureSessions.test.ts
```

Expected: 全部 4 个测试 PASS

- [ ] **Step 5: 运行全部前端测试确认无回归**

```bash
cd app/frontend && npx vitest run
```

Expected: 全部 PASS（注意 App.test.tsx 中可能有断言需要更新，先看结果）

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/api/captureSessions.ts app/frontend/src/api/captureSessions.test.ts
git commit -m "新增 buildQrCodeUrl 纯函数，生产模式透传后端 URL，DEV 模式转 Vite origin"
```

---

### Task 6: Vite allowedHosts + 前端测试更新

**Files:**
- Modify: `app/frontend/vite.config.ts`
- Modify: `app/frontend/src/app/App.test.tsx`

- [ ] **Step 1: 修改 vite.config.ts**

在 `app/frontend/vite.config.ts` 的 `server` 块中，`port: 5173` 之后新增：

```typescript
allowedHosts: true,
```

完整 `server` 块：

```typescript
server: {
  host: '0.0.0.0',
  port: 5173,
  strictPort: false,
  allowedHosts: true,
  proxy: {
    '/api': 'http://127.0.0.1:8081'
  }
},
```

- [ ] **Step 2: 更新 App.test.tsx 中二维码 URL 断言**

当前 App.test.tsx 中可能有针对旧 `buildFrontendMobileUrl` 行为的断言。先运行测试看结果：

```bash
cd app/frontend && npx vitest run src/app/App.test.tsx -v
```

如果测试中有断言期望 `qr_code_url` 包含 `5173` 端口（即旧行为：前端转换 URL），需要更新为适配 DEV 模式的预期。由于 Vitest 运行在 jsdom 环境（`url: 'http://127.0.0.1:5173/'`），`import.meta.env.DEV` 在测试中为 `true`，因此 URL 会被转换为 `http://127.0.0.1:5173/mobile/sessions/{id}`。

检查并更新相关断言：

```typescript
// 如果旧断言是检查 qr_code_url 使用 LAN IP + 5173 端口
// 新行为：DEV 模式下 buildQrCodeUrl 使用 window.location.origin
// jsdom 的 url 是 http://127.0.0.1:5173/，所以 qr_code_url 会是:
// http://127.0.0.1:5173/mobile/sessions/{id}
```

具体修改根据测试失败情况逐一修正。

- [ ] **Step 3: 确认 MobileCapturePage API 调用使用相对路径**

```bash
cd app/frontend && npx vitest run src/pages/mobile-capture/MobileCapturePage.test.tsx -v
```

验证所有 API mock 调用都使用 `/api/mobile/...` 相对路径而非硬编码主机名。预期 PASS。

- [ ] **Step 4: 运行全部前端测试**

```bash
cd app/frontend && npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/frontend/vite.config.ts app/frontend/src/app/App.test.tsx
git commit -m "Vite 增加 allowedHosts: true，更新二维码 URL 前端测试断言"
```

---

### Task 7: 启动脚本 run.bat

**Files:**
- Modify: `run.bat`
- Modify: `app/backend/tests/test_windows_startup_scripts.py`

- [ ] **Step 1: 修改 run.bat 的浏览器入口**

`run.bat` 第 63 行：

```batch
# 修改前
start "" "http://127.0.0.1:8081/api/system/status"

# 修改后
start "" "http://127.0.0.1:8081/"
```

健康检查 URL（第 42 行 `http://127.0.0.1:8081/api/system/status`）保持不变。

- [ ] **Step 2: 更新测试断言**

在 `app/backend/tests/test_windows_startup_scripts.py` 中新增测试：

```python
def test_run_bat_opens_localhost_root_not_health_check(self):
    """WIN-NW-001: run.bat 打开 http://127.0.0.1:8081/ 而不是健康检查 JSON"""
    content = open("run.bat").read()
    assert 'start "" "http://127.0.0.1:8081/"' in content
    assert 'start "" "http://127.0.0.1:8081/api/system/status"' not in content


def test_run_bat_health_check_still_uses_status_endpoint(self):
    """WIN-NW-002: run.bat 健康检查仍使用 /api/system/status"""
    content = open("run.bat").read()
    assert "http://127.0.0.1:8081/api/system/status" in content
```

- [ ] **Step 3: 运行启动脚本测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/test_windows_startup_scripts.py -v
```

Expected: 全部 PASS（含新增的 2 个测试）

- [ ] **Step 4: Commit**

```bash
git add run.bat app/backend/tests/test_windows_startup_scripts.py
git commit -m "run.bat 浏览器入口改为 http://127.0.0.1:8081/，健康检查保持 /api/system/status"
```

---

### Task 8: 构建前端并手动全链路验证

**Files:** 无代码变更，仅验证

- [ ] **Step 1: 构建前端 dist**

```bash
cd app/frontend && npm run build
```

Expected: dist 生成成功

- [ ] **Step 2: 启动后端并验证静态首页**

```bash
# 终端 1：启动后端
conda run -n manzufei_ocr python -m app.backend.main

# 终端 2：验证
curl --noproxy '*' -I http://127.0.0.1:8081/
```

Expected: `HTTP/1.1 200 OK` + `Content-Type: text/html`

- [ ] **Step 3: 验证手机采集页 fallback**

```bash
curl --noproxy '*' -I http://127.0.0.1:8081/mobile/sessions/test
```

Expected: `HTTP/1.1 200 OK` + `Content-Type: text/html`

- [ ] **Step 4: 验证 API 不被 fallback 吃掉**

```bash
curl --noproxy '*' http://127.0.0.1:8081/api/system/status
```

Expected: JSON 响应，`"success": true`，`"status": "running"`

```bash
curl --noproxy '*' http://127.0.0.1:8081/api/not-exists
```

Expected: JSON 404，`"error": {"code": "REQUEST_NOT_FOUND"}`

- [ ] **Step 5: 验证静态资源**

```bash
# 存在的资源
curl --noproxy '*' -I http://127.0.0.1:8081/assets/app.js

# 不存在的资源
curl --noproxy '*' http://127.0.0.1:8081/assets/missing.js
```

Expected: 存在 → 200 + 文件内容；不存在 → 404

- [ ] **Step 6: 验证局域网地址（替换为实际 LAN IP）**

```bash
LAN_IP=$(curl --noproxy '*' -s http://127.0.0.1:8081/api/system/status | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['lan_addresses'][0].rsplit(':',1)[0])")
curl --noproxy '*' -I "http://${LAN_IP}:8081/mobile/sessions/test"
```

Expected: `HTTP/1.1 200 OK` + `Content-Type: text/html`

- [ ] **Step 7: 最终全量测试**

```bash
conda run -n manzufei_ocr python -m pytest app/backend/tests/ -v
cd app/frontend && npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 8: 最终 Commit（如 dist 有变化）**

```bash
git status
# 如有 dist 变更或遗漏文件，提交
```

---

## 实施依赖图

```
Task 1 (QR URL) ──┐
                  ├──> Task 3 (static serve) ──> Task 4 (lan verify)
Task 2 (config)  ──┘                                  │
                                                      │
Task 5 (frontend url) ──> Task 6 (vite + tests) ─────┘
                                                      │
                                          Task 7 (run.bat)
                                                      │
                                          Task 8 (manual verify)
```

Task 1 + 2 可并行，Task 5 独立可并行。
Task 3 依赖 Task 2（需要 static_dir 配置）。
Task 6 依赖 Task 5。
Task 7 独立。
Task 8 需等所有 Task 完成后执行。
