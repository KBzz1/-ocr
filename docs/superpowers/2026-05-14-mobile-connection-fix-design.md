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

新增配置项 `static_dir`，默认指向 `app/frontend/dist/`。

路由优先级（高到低）：
1. `/api/*` → Blueprint 路由（不变）
2. `/assets/*`、`/mobile/sessions/*`、`/` 等 → 静态文件目录 `dist/`
3. 静态文件中不存在的路径 → SPA fallback 返回 `dist/index.html`

实现方式：注册一个 `before_request` 钩子，对非 `/api/*` 请求，如果路径对应静态文件则直接返回文件，否则返回 `index.html`。

核心逻辑：
```python
import os
from flask import send_from_directory, send_file

def _register_static_serve(app, static_dir):
    """注册静态文件服务 + SPA fallback。"""
    @app.before_request
    def _serve_spa():
        # 只拦截非 API 请求
        if request.path.startswith('/api/'):
            return None

        file_path = os.path.join(static_dir, request.path.lstrip('/'))
        # 静态资源（有扩展名）存在则返回，不存在则 404
        if os.path.splitext(request.path)[1]:
            if os.path.isfile(file_path):
                return send_from_directory(static_dir, request.path.lstrip('/'))
            return None  # 让 Flask 返回 404

        # 无扩展名的 SPA 路由，返回 index.html
        index_path = os.path.join(static_dir, 'index.html')
        if os.path.isfile(index_path):
            return send_file(index_path)

        return None
```

注意：使用 `before_request` 而非 error handler，因为需要区分「静态资源 404」和「SPA 路由」。

### 3. 前端二维码 URL 转换

**文件**：`app/frontend/src/api/captureSessions.ts`

新增 `buildQrCodeUrl()` 函数，替代当前的 `buildFrontendMobileUrl()`：

```typescript
function buildQrCodeUrl(session: CaptureSession): string {
  // DEV 模式：将后端 8081 端口转为 Vite 端口
  if (import.meta.env.DEV) {
    const backendUrl = new URL(session.qr_code_url);
    const frontendUrl = new URL(window.location.href);
    frontendUrl.pathname = `/mobile/sessions/${encodeURIComponent(session.session_id)}`;
    frontendUrl.search = '';
    frontendUrl.hash = '';
    return frontendUrl.toString();
  }
  // 生产模式：原样返回后端 URL
  return session.qr_code_url;
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
| BE-NW-007 | `GET /api/system/status` 返回 `lan_addresses`，排除 127.0.0.1、localhost | `test_system_status.py`（已有，确认） |

### 前端测试

| ID | 测试 | 文件 |
|----|------|------|
| FE-NW-001 | 生产模式：`buildQrCodeUrl()` 原样返回后端 URL | `captureSessions.test.ts`（新增） |
| FE-NW-002 | 开发模式：`buildQrCodeUrl()` 转端口为 Vite origin | `captureSessions.test.ts`（新增） |
| FE-NW-003 | `createCaptureSession()` 返回的 `qr_code_url` 使用后端 8081 地址（生产）/ Vite 地址（开发） | `App.test.tsx`（修改） |
| FE-NW-004 | 二维码弹窗显示正确的手机可访问 URL | `App.test.tsx`（修改） |

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
```

## 实施顺序

1. 后端：修正二维码 URL → 测试 BE-NW-001
2. 后端：实现静态文件托管 + SPA fallback → 测试 BE-NW-002 ~ BE-NW-006
3. 后端：确认 `lan_addresses` 过滤 → 测试 BE-NW-007
4. 前端：`buildQrCodeUrl()` → 测试 FE-NW-001 ~ FE-NW-002
5. 前端：Vite `allowedHosts` → 测试 FE-NW-003 ~ FE-NW-004
6. 启动脚本：`run.bat` 打开 `http://127.0.0.1:8081/`
7. 手动验证：curl 命令验证全链路
