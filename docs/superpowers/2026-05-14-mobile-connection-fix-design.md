# 手机连接修复设计

## 范围

本设计覆盖手机采集端连接问题的系统性修复：单端口生产链路（Flask 8081 托管前端静态文件 + API）、开发链路兜底（Vite 5173 + allowedHosts）、二维码 URL 修正、以及全链路 TDD 覆盖。

本阶段覆盖：

- **NW-001**：后端生成正确的二维码 URL `http://{lan_ip}:8081/mobile/sessions/{session_id}`
- **NW-002**：Flask 8081 托管前端 dist 静态文件，`/` 返回工作台 SPA
- **NW-003**：`/mobile/sessions/{id}` 返回手机采集 SPA（SPA fallback）
- **NW-004**：`/api/*` 不被静态 fallback 吃掉，仍返回 API 响应 / 404
- **NW-005**：`/assets/xxx.js` 存在时返回文件，不存在时返回 404（不返回 index.html）
- **NW-006**：前端生产模式不再改写二维码 URL，直接使用后端返回的 8081 地址
- **NW-007**：前端开发模式将后端 8081 地址转换为当前 Vite origin（仅 DEV）
- **NW-008**：Vite 配置 `allowedHosts: true`，允许 LAN IP 访问
- **NW-009**：`/api/system/status` 返回 `lan_addresses`，排除 127.0.0.1 和 localhost
- **NW-010**：`run.bat` 启动后打开 `http://127.0.0.1:8081/`（静态首页），不是健康检查 JSON
- **NW-011**：手动验证：`curl --noproxy '*' http://{LAN_IP}:8081/mobile/sessions/test` 返回 HTML
- **NW-012**：缺少前端构建产物时，`/` 和 SPA 路由返回受控 404 JSON，不抛 500，不伪装成可用首页

本阶段不覆盖：

- flask-cors 安装（单端口同源不需要 CORS）
- Windows 防火墙配置（属于部署文档，不在代码仓库内实现）
- 手机端拍照、上传、四边形框选逻辑变更
- 后端 API 业务逻辑变更

## 技术选型

| 项 | 选择 |
|----|------|
| 静态文件托管 | Flask `send_from_directory` + `send_file` |
| SPA fallback | Flask `before_request` 钩子：对非 `/api/*` 非静态资源路由返回 `index.html` |
| 二维码 URL | 后端直接生成 `http://{lan_ip}:8081/mobile/sessions/{id}` |
| 前端 URL 转换 | 仅 DEV 模式下将 8081 端口替换为当前 Vite origin |
| Vite 安全 | `allowedHosts: true` |

## 架构变更

```
当前（有问题）：
手机 → http://{LAN_IP}:5173/mobile/sessions/{id}  (Vite dev server)
       ↓ /api/* 代理到 127.0.0.1:8081
       → Flask API
问题：两个端口都要开防火墙，URL 转换逻辑脆弱，Vite CORS/defaultAllowedOrigins 拒绝 LAN IP

目标：
生产：手机 → http://{LAN_IP}:8081/mobile/sessions/{id}
              ↓ 同源
              Flask 8081 托管前端 dist + API
              （单端口、同源、零 CORS、一个防火墙规则）

开发：前端 dev 时 → Vite :5173 热更新
                     ↓ /api/* 代理到 Flask :8081
                     （allowedHosts: true 兜底，仅开发用）
```

## 详细设计

### 1. 后端二维码 URL 修正

**文件**：`app/backend/services/session_service.py:21`

当前：
```python
qr_code_url = f"http://{self._lan_addresses[0]}/mobile/{session_id}"
```

修正为：
```python
qr_code_url = f"http://{self._lan_addresses[0]}/mobile/sessions/{session_id}"
```

`self._lan_addresses[0]` 已包含端口（如 `192.168.1.5:8081`），因此完整 URL 示例为：
`http://192.168.1.5:8081/mobile/sessions/abc-123`

### 2. Flask 静态文件托管 + SPA fallback

**文件**：`app/backend/__init__.py`（`create_backend_app` 函数）

新增后端扁平配置项 `static_dir`，默认指向 `app/frontend/dist/`。配置加载规则与现有路径类配置一致：

- `app/backend/config.py` 的 `DEFAULT_CONFIG` 增加 `"static_dir": "./app/frontend/dist"`。
- `_flatten_config()` 支持 `paths.static_dir`，允许 `app/config/local.yaml` 在开发或打包验证时覆盖。
- `_normalize_paths()` 对 `static_dir` 做基于 `PROJECT_ROOT` 的绝对路径归一化。
- `_validate_config()` 不创建 `static_dir`，因为它是构建产物目录；缺失时静态路由返回受控 404 JSON。

构建产物契约：

- 发布包必须包含 `app/frontend/dist/index.html` 和对应 `assets/` 文件。
- 开发环境验证 8081 单端口链路前必须先运行 `npm run build`。
- `run.bat` 不负责执行前端构建；它只启动已打包好的离线应用。

路由优先级（高到低）：
1. `/api/*` → Blueprint 路由（不变）
2. `/assets/*` 和其他带扩展名静态资源 → 静态文件目录 `dist/`
3. `/`、`/mobile/sessions/*`、`/tasks` 等无扩展名 SPA 路由 → 返回 `dist/index.html`
4. 缺失的带扩展名资源（如 `/assets/missing.js`）→ 404，不返回 `index.html`
5. `dist/index.html` 缺失 → 受控 404 JSON，不抛 500

实现方式：注册一个 `before_request` 钩子，对非 `/api/*` 请求，如果路径对应静态文件则直接返回文件；带扩展名资源缺失返回 404；无扩展名 SPA 路由返回 `index.html`。文件路径检查和发送都必须使用 Werkzeug/Flask 的安全路径工具，不能用拼接后的路径绕过 `static_dir` 边界。

核心逻辑：
```python
import os
from flask import request, send_from_directory, send_file
from werkzeug.exceptions import NotFound
from werkzeug.utils import safe_join

from .responses import error_response
from .errors import AppError, ErrorCode

def _register_static_serve(app, static_dir):
    """注册静态文件服务 + SPA fallback。"""
    @app.before_request
    def _serve_spa():
        # 只拦截非 API 请求
        if request.path.startswith('/api/'):
            return None

        relative_path = request.path.lstrip('/') or 'index.html'
        file_path = safe_join(static_dir, relative_path)
        if file_path is None:
            raise NotFound()

        # 静态资源（有扩展名）存在则返回，不存在则 404
        if os.path.splitext(request.path)[1]:
            if file_path and os.path.isfile(file_path):
                return send_from_directory(static_dir, relative_path)
            raise NotFound()

        # 无扩展名的 SPA 路由，返回 index.html
        index_path = safe_join(static_dir, 'index.html')
        if os.path.isfile(index_path):
            return send_file(index_path)

        return error_response(AppError(ErrorCode.REQUEST_NOT_FOUND))
```

注意：使用 `before_request` 而非 error handler，因为需要区分「静态资源 404」和「SPA 路由」。`/api/not-exists` 仍交给现有 API 错误处理，返回统一 JSON 404。

### 3. 前端二维码 URL 转换

**文件**：`app/frontend/src/api/captureSessions.ts`

新增可测试的纯函数 `buildQrCodeUrl()`，替代当前的 `buildFrontendMobileUrl()`。`createCaptureSession()` 负责把 `import.meta.env.DEV` 和 `window.location.href` 注入该函数，避免测试直接依赖不可变的 `import.meta.env`。

```typescript
export interface BuildQrCodeUrlOptions {
  isDev: boolean;
  currentHref: string;
}

export function buildQrCodeUrl(
  session: CaptureSession,
  options: BuildQrCodeUrlOptions
): string {
  // DEV 模式：将后端 8081 端口转为 Vite 端口
  if (options.isDev) {
    const frontendUrl = new URL(options.currentHref);
    frontendUrl.pathname = `/mobile/sessions/${encodeURIComponent(session.session_id)}`;
    frontendUrl.search = '';
    frontendUrl.hash = '';
    return frontendUrl.toString();
  }
  // 生产模式：原样返回后端 URL
  return session.qr_code_url;
}

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

关键差异：
- DEV=false（生产）：原样返回 `session.qr_code_url`，即 `http://192.168.1.5:8081/mobile/sessions/abc-123`
- DEV=true（开发）：用 `window.location.origin` + 后端 pathname，即 `http://192.168.1.5:5173/mobile/sessions/abc-123`

`createCaptureSession()` 中调用 `buildQrCodeUrl()` 替换原来的 `buildFrontendMobileUrl()`。

### 4. Vite 配置

**文件**：`app/frontend/vite.config.ts`

```typescript
server: {
  host: '0.0.0.0',
  port: 5173,
  strictPort: false,
  allowedHosts: true,
  proxy: {
    '/api': 'http://127.0.0.1:8081'
  }
}
```

### 5. 启动脚本

**文件**：`run.bat`

启动后端后，自动打开浏览器指向 `http://127.0.0.1:8081/`（静态首页），不再是 `http://127.0.0.1:8081/api/system/status`。

## TDD 测试计划

### 后端测试

| ID | 测试 | 文件 |
|----|------|------|
| BE-NW-001 | `SessionService.create()` 生成的 `qr_code_url` 为 `http://{lan_ip}:8081/mobile/sessions/{id}` | `test_capture_session.py`（修改） |
| BE-NW-002 | `GET /` 返回 HTML（非 JSON），Content-Type 为 `text/html` | `test_static_serve.py`（新增） |
| BE-NW-003 | `GET /mobile/sessions/{id}` 返回 SPA index.html | `test_static_serve.py`（新增） |
| BE-NW-004 | `GET /api/system/status` 不被 fallback 吃掉，仍返回 JSON | `test_static_serve.py`（新增） |
| BE-NW-005 | `GET /api/not-exists` 返回 API JSON 404，不返回 index.html | `test_static_serve.py`（新增） |
| BE-NW-006 | `GET /assets/missing.js` 返回 404，不返回 index.html | `test_static_serve.py`（新增） |
| BE-NW-007 | `GET /assets/app.js` 存在时返回静态文件 | `test_static_serve.py`（新增） |
| BE-NW-008 | `GET /` 在 `dist/index.html` 缺失时返回统一 JSON 404，不抛 500 | `test_static_serve.py`（新增） |
| BE-NW-009 | `static_dir` 默认值会归一化为项目内 `app/frontend/dist`，且可通过 `paths.static_dir` 覆盖 | `test_config.py`（修改） |
| BE-NW-010 | `GET /api/system/status` 返回 `lan_addresses`，排除 127.0.0.1、localhost | `test_windows_startup_scripts.py`（已有，确认） |

### 前端测试

| ID | 测试 | 文件 |
|----|------|------|
| FE-NW-001 | 生产模式：`buildQrCodeUrl()` 原样返回后端 URL | `captureSessions.test.ts`（新增） |
| FE-NW-002 | 开发模式：`buildQrCodeUrl()` 转端口为 Vite origin | `captureSessions.test.ts`（新增） |
| FE-NW-003 | `createCaptureSession()` 返回的 `qr_code_url` 使用后端 8081 地址（生产）/ Vite 地址（开发） | `App.test.tsx`（修改） |
| FE-NW-004 | 二维码弹窗显示正确的手机可访问 URL | `App.test.tsx`（修改） |
| FE-NW-005 | 手机端页面所有 API 调用仍使用相对路径 `/api/...` 和 `/api/mobile/...`，不硬编码主机名 | `MobileCapturePage.test.tsx` / `shared-contracts.test.ts`（确认） |

### 启动脚本测试

| ID | 测试 | 文件 |
|----|------|------|
| WIN-NW-001 | `run.bat` 打开 `http://127.0.0.1:8081/` | `test_windows_startup_scripts.py`（修改） |
| WIN-NW-002 | `run.bat` 仍用 `http://127.0.0.1:8081/api/system/status` 做健康检查，不把 JSON 页面作为用户入口 | `test_windows_startup_scripts.py`（修改） |

### 手动验证命令

```bash
# 验证 Flask 8081 在局域网监听
curl --noproxy '*' http://127.0.0.1:8081/api/system/status

# 验证静态首页返回 HTML
curl --noproxy '*' -I http://127.0.0.1:8081/

# 验证手机采集页 fallback
curl --noproxy '*' -I http://127.0.0.1:8081/mobile/sessions/test

# 验证 API 404 不返回 HTML
curl --noproxy '*' http://127.0.0.1:8081/api/not-exists

# 验证局域网手机采集入口返回 HTML（将 LAN_IP 替换为 /api/system/status 中的地址主机）
curl --noproxy '*' -I http://{LAN_IP}:8081/mobile/sessions/test
```

## 实施顺序

1. 后端：修正二维码 URL → 测试 BE-NW-001
2. 后端：增加 `static_dir` 配置默认值、归一化和覆盖测试 → 测试 BE-NW-009
3. 后端：实现静态文件托管 + SPA fallback → 测试 BE-NW-002 ~ BE-NW-008
4. 后端：确认 `lan_addresses` 过滤 → 测试 BE-NW-010
5. 前端：`buildQrCodeUrl()` 纯函数 → 测试 FE-NW-001 ~ FE-NW-002
6. 前端：接入 `createCaptureSession()`、二维码弹窗和 Vite `allowedHosts` → 测试 FE-NW-003 ~ FE-NW-005
7. 启动脚本：`run.bat` 打开 `http://127.0.0.1:8081/`，健康检查仍使用 `/api/system/status`
8. 构建并手动验证：`npm run build` 后用 curl 命令验证 8081 单端口全链路
