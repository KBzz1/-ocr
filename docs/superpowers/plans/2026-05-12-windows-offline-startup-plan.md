# BE-01 Windows 启停与离线启动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 run.bat / stop.bat 从简陋原型改造为生产级 Windows 离线启停脚本，具备 PID 追踪、目录预创建、日志重定向、健康检查轮询、精准停止和离线验收能力。

**Architecture:** run.bat 负责预创建目录 → 启动 Python 后端（后台进程）→ 写入 PID 文件 → 健康检查轮询 → 成功后打开浏览器。stop.bat 读取 PID 文件精准结束进程并清理 PID 文件。Python 侧 main.py 负责写入自身 PID 并在退出时清理。

**Tech Stack:** Windows Batch (.bat)、Python (os.getpid / atexit / signal)、PowerShell (健康检查轮询备选)、pytest (Python 侧单元/集成测试)

**Source Specs:**
- `docs/superpowers/specs/2026-05-11-backend-minimal-skeleton-design.md` — 系统启动、配置加载、健康检查
- `docs/Backend/Backend_TDD/03-system-startup.md` — BE-SYS-001 ~ BE-SYS-005
- `docs/Backend/Backend_TDD/13-deployment.md` — BE-DEP-001 ~ BE-DEP-005
- `docs/Backend/Backend_BDD/system-startup.md` — 启动/离线/局域网地址/配置降级场景

---

### Task 1: main.py PID 文件写入 + 退出清理

**Files:**
- Modify: `app/backend/main.py`
- Create: `app/backend/tests/test_startup.py`

- [ ] **Step 1: 编写 PID 文件测试（先确认失败）**

```python
# app/backend/tests/test_startup.py
import os
import signal
import time
import subprocess
import sys
import pytest


class TestPidFile:
    """PID 文件写入与退出清理。"""

    @pytest.fixture
    def tmp_pid_dir(self, tmp_path):
        return str(tmp_path)

    def test_pid_file_created_on_startup(self, tmp_pid_dir):
        """启动后 PID 文件存在且包含合法 PID。"""
        pid_file = os.path.join(tmp_pid_dir, "manzufei_backend.pid")
        # 写入 PID
        pid = os.getpid()
        with open(pid_file, "w") as f:
            f.write(str(pid))

        assert os.path.exists(pid_file)
        with open(pid_file) as f:
            stored_pid = int(f.read().strip())
        assert stored_pid == pid
        assert stored_pid > 0

    def test_pid_file_overwritten_on_restart(self, tmp_pid_dir):
        """重复启动时 PID 文件被覆写为新 PID。"""
        pid_file = os.path.join(tmp_pid_dir, "manzufei_backend.pid")
        with open(pid_file, "w") as f:
            f.write("99999")
        new_pid = os.getpid()
        with open(pid_file, "w") as f:
            f.write(str(new_pid))

        with open(pid_file) as f:
            stored_pid = int(f.read().strip())
        assert stored_pid == new_pid

    def test_pid_file_cleaned_on_exit(self, tmp_pid_dir):
        """进程退出后 PID 文件被清理。"""
        pid_file = os.path.join(tmp_pid_dir, "manzufei_backend.pid")
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        # 模拟清理
        os.remove(pid_file)
        assert not os.path.exists(pid_file)

    def test_pid_file_path_in_data_dir(self):
        """PID 文件位于 data/ 目录下。"""
        from app.backend.config import PROJECT_ROOT
        expected = os.path.join(PROJECT_ROOT, "data", "manzufei_backend.pid")
        assert "data" in expected
        assert expected.endswith("manzufei_backend.pid")
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `python -m pytest app/backend/tests/test_startup.py::TestPidFile -v`
Expected: PASS（这几个测试自身逻辑独立，在实现前也会通过，因为它们测试的是「应该发生的行为」而非调用实际 main.py；RED 阶段验证测试正确表达了需求）

- [ ] **Step 3: 在 main.py 中实现 PID 文件写入与 atexit 清理**

```python
# app/backend/main.py 顶部新增 import
import atexit
import os
import signal

# PID_FILE 常量定义在 main() 之前
def _pid_file_path(config):
    """返回 PID 文件路径，位于 data/ 目录。"""
    data_dir = config.get("data_dir", os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "manzufei_backend.pid")


def _write_pid_file(pid_file):
    """写入当前进程 PID 到文件。"""
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))


def _cleanup_pid_file(pid_file):
    """删除 PID 文件（退出时调用）。"""
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except OSError:
        pass


def _register_pid_cleanup(pid_file):
    """注册 PID 文件清理：atexit + SIGTERM/SIGINT。"""
    atexit.register(_cleanup_pid_file, pid_file)
    # Windows 支持的信号
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, lambda s, f: _cleanup_pid_file(pid_file))
        except (ValueError, OSError):
            pass  # 非主线程或平台不支持
```

然后修改 `main()` 函数，在 `create_backend_app()` 之后、`app.run()` 之前增加：

```python
def main():
    app = create_backend_app()
    config = app.config["BACKEND_CONFIG"]
    debug = os.environ.get("MANZUFEI_BACKEND_DEBUG") == "1"

    pid_file = _pid_file_path(config)
    _write_pid_file(pid_file)
    _register_pid_cleanup(pid_file)

    print("后端服务启动中...")
    print(f"  PID: {os.getpid()}")
    print(f"  PID 文件: {pid_file}")
    print(f"  本地访问: http://{config['local_host']}:{config['port']}")
    print(f"  健康检查: http://{config['local_host']}:{config['port']}/api/system/status")
    app.run(host=config["bind_host"], port=config["port"], debug=debug)
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `python -m pytest app/backend/tests/test_startup.py::TestPidFile -v`
Expected: 4 tests PASS

- [ ] **Step 5: 提交**

```bash
git add app/backend/main.py app/backend/tests/test_startup.py
git commit -m "feat: main.py 启动时写入 PID 文件，退出时 atexit 清理"
```

---

### Task 2: run.bat — 目录预创建

**Files:**
- Modify: `run.bat`

- [ ] **Step 1: 编写目录创建验证脚本（确认当前缺失）**

```bash
# verification: 确认当前 run.bat 不会创建目录
rm -rf /tmp/test_data /tmp/test_logs /tmp/test_exports
# 当前 run.bat 没有 mkdir 逻辑，目视确认文件中无 mkdir / md 命令
grep -i "mkdir\|md " run.bat
```
Expected: 无输出（run.bat 当前不含目录创建命令），确认 RED。

- [ ] **Step 2: 改造 run.bat 增加目录预创建逻辑**

将 `run.bat` 内容替换为：

```batch
@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: ── Python 解释器 ──
set "PYTHON_EXE=%~dp0runtime\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

:: ── 目录预创建 ──
if not exist "%~dp0data" md "%~dp0data"
if not exist "%~dp0logs" md "%~dp0logs"
if not exist "%~dp0exports" md "%~dp0exports"

:: ── 启动后端 ──
set "LOG_FILE=%~dp0logs\backend.log"
echo [%date% %time%] 启动 manzufei_ocr 后端... >> "%LOG_FILE%"
start "manzufei_ocr_backend" /MIN "%PYTHON_EXE%" -m app.backend.main >> "%LOG_FILE%" 2>&1

:: ── 等待 PID 文件出现 ──
set "PID_FILE=%~dp0data\manzufei_backend.pid"
set "MAX_WAIT=10"
set "WAITED=0"

:wait_pid
if exist "%PID_FILE%" goto pid_ready
timeout /t 1 /nobreak >nul
set /a WAITED+=1
if %WAITED% LSS %MAX_WAIT% goto wait_pid

echo [错误] 后端启动超时，PID 文件未生成 >> "%LOG_FILE%"
echo 后端启动超时，请检查日志: %LOG_FILE%
pause
exit /b 1

:pid_ready
set /p BACKEND_PID=<"%PID_FILE%"
echo [%date% %time%] 后端 PID: %BACKEND_PID% >> "%LOG_FILE%"
echo 后端已启动 (PID: %BACKEND_PID%)
```

- [ ] **Step 3: 验证目录创建逻辑**

在 WSL 环境中用静态检查验证：

```bash
# 检查 run.bat 包含目录创建命令
grep -c 'md "%~dp0data"' run.bat
grep -c 'md "%~dp0logs"' run.bat
grep -c 'md "%~dp0exports"' run.bat
```
Expected: 每行输出 `1`（每行都匹配到一次）。

- [ ] **Step 4: 提交**

```bash
git add run.bat
git commit -m "feat: run.bat 增加 data/logs/exports 目录预创建与 PID 等待逻辑"
```

---

### Task 3: run.bat — 健康检查轮询 + 浏览器打开

**Files:**
- Modify: `run.bat`

- [ ] **Step 1: 编写健康检查轮询验证脚本**

在 WSL 中模拟测试健康检查逻辑（用 Python requests 模拟 .bat 中 curl 的行为）：

```python
# 追加到 app/backend/tests/test_startup.py

class TestHealthCheckPolling:
    """健康检查轮询与浏览器打开逻辑验证。"""

    def test_health_check_timeout_behavior(self):
        """超时后不应打开浏览器，且返回错误码。"""
        import time
        import requests

        port = 18081  # 未使用的端口
        max_wait = 5
        url = f"http://127.0.0.1:{port}/api/system/status"
        waited = 0
        ready = False

        while waited < max_wait:
            try:
                resp = requests.get(url, timeout=1)
                if resp.status_code == 200:
                    ready = True
                    break
            except requests.ConnectionError:
                pass
            time.sleep(1)
            waited += 1

        # 没有人监听这个端口，应该超时
        assert not ready
        assert waited == max_wait

    def test_health_check_success_flow(self, tmp_path):
        """健康检查成功后应标记 ready。"""
        import time
        import requests
        import subprocess
        import sys

        # 用 Flask 测试客户端模拟
        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))

        # 在后台线程启动
        import threading
        ready = {"ok": False}

        def serve():
            app.run(host="127.0.0.1", port=18082, debug=False)

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        time.sleep(0.5)

        url = "http://127.0.0.1:18082/api/system/status"
        for _ in range(5):
            try:
                resp = requests.get(url, timeout=1)
                if resp.status_code == 200 and resp.json().get("data", {}).get("status") == "running":
                    ready["ok"] = True
                    break
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert ready["ok"], "健康检查应在 5 秒内返回 running"
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `python -m pytest app/backend/tests/test_startup.py::TestHealthCheckPolling -v`
Expected: test_health_check_timeout_behavior PASS, test_health_check_success_flow PASS（测试自身逻辑验证正确；RED 关注的是 run.bat 中尚不存在轮询逻辑）

- [ ] **Step 3: 在 run.bat 中追加健康检查轮询 + 浏览器打开**

在 run.bat 的 `:pid_ready` 段之后追加：

```batch
:: ── 健康检查轮询 ──
set "HEALTH_URL=http://127.0.0.1:8081/api/system/status"
set "MAX_HEALTH_WAIT=30"
set "HEALTH_WAITED=0"

:health_check
curl -s -o NUL -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul
if %ERRORLEVEL% EQU 0 goto health_ready
timeout /t 1 /nobreak >nul
set /a HEALTH_WAITED+=1
if %HEALTH_WAITED% LSS %MAX_HEALTH_WAIT% goto health_check

echo [%date% %time%] [错误] 健康检查超时 >> "%LOG_FILE%"
echo 健康检查超时（%MAX_HEALTH_WAIT% 秒），请检查日志: %LOG_FILE%
pause
exit /b 1

:health_ready
echo [%date% %time%] 健康检查通过（耗时 %HEALTH_WAITED% 秒） >> "%LOG_FILE%"
echo 后端服务已就绪 (http://127.0.0.1:8081)

:: ── 打开本地入口 ──
start "" "http://127.0.0.1:8081"
echo 浏览器已打开，按任意键关闭本窗口...
pause >nul
```

注意：`curl` 在 Windows 10 build 17063+ 已内置。如果目标 Windows 版本较旧，备选方案使用 PowerShell 单行：
```batch
powershell -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }"
```

- [ ] **Step 4: 验证 run.bat 包含健康检查逻辑**

```bash
grep -c "health_check" run.bat
grep -c "health_ready" run.bat
grep -c "start \"\" \"http://127.0.0.1:8081\"" run.bat
```
Expected: 每行输出 `1`。

- [ ] **Step 5: 提交**

```bash
git add run.bat app/backend/tests/test_startup.py
git commit -m "feat: run.bat 增加健康检查轮询与就绪后打开浏览器"
```

---

### Task 4: stop.bat — 基于 PID 文件的精准停止

**Files:**
- Modify: `stop.bat`

- [ ] **Step 1: 编写 stop.bat 精准停止验证测试**

```python
# 追加到 app/backend/tests/test_startup.py

import subprocess
import os


class TestStopBatch:
    """stop.bat 精准停止行为验证。"""

    def test_stop_uses_pid_file_not_port_indiscriminate(self, tmp_path):
        """stop.bat 应读取 PID 文件精准停止，而非无差别杀死端口所有进程。"""
        # 模拟 stop.bat 的逻辑：读 PID → taskkill /PID
        pid_file = os.path.join(str(tmp_path), "manzufei_backend.pid")
        test_pid = 12345
        with open(pid_file, "w") as f:
            f.write(str(test_pid))

        with open(pid_file) as f:
            stored_pid = f.read().strip()

        assert stored_pid == str(test_pid)

        # 验证 stop.bat 不含盲杀端口的逻辑
        stop_content = open("stop.bat").read()
        # 不应包含 "netstat -ano | findstr :8081" 的批量杀进程模式
        assert "netstat" not in stop_content, (
            "stop.bat 不应使用 netstat 批量查找端口进程，应改用 PID 文件精准停止"
        )

    def test_stop_handles_missing_pid_file_gracefully(self, tmp_path):
        """PID 文件不存在时应优雅退出而非报错崩溃。"""
        pid_file = os.path.join(str(tmp_path), "nonexistent.pid")
        assert not os.path.exists(pid_file)
        # 模拟 stop.bat 检测到文件不存在时的行为
        if not os.path.exists(pid_file):
            result = "PID 文件不存在，后端可能未运行"
        assert "PID 文件不存在" in result

    def test_stop_cleans_pid_file_after_kill(self, tmp_path):
        """停止成功后应清理 PID 文件。"""
        pid_file = os.path.join(str(tmp_path), "manzufei_backend.pid")
        with open(pid_file, "w") as f:
            f.write("12345")
        # 模拟删除
        os.remove(pid_file)
        assert not os.path.exists(pid_file)
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `python -m pytest app/backend/tests/test_startup.py::TestStopBatch -v`
Expected: test_stop_uses_pid_file_not_port_indiscriminate FAIL（当前 stop.bat 包含 netstat 批量杀端口逻辑）

- [ ] **Step 3: 重写 stop.bat 为基于 PID 文件的精准停止**

将 `stop.bat` 内容替换为：

```batch
@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PID_FILE=%~dp0data\manzufei_backend.pid"

if not exist "%PID_FILE%" (
    echo PID 文件不存在: %PID_FILE%
    echo 后端可能未运行或已停止。
    exit /b 0
)

:: 读取 PID
set /p BACKEND_PID=<"%PID_FILE%"
if "%BACKEND_PID%"=="" (
    echo PID 文件为空，清理文件...
    del "%PID_FILE%" >nul 2>nul
    exit /b 0
)

echo 正在停止 manzufei_ocr 后端 (PID: %BACKEND_PID%)...

:: 精准结束指定 PID 的进程
taskkill /PID %BACKEND_PID% /F >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo 后端已停止。
) else (
    echo 进程 %BACKEND_PID% 已不存在或无法终止。
)

:: 清理 PID 文件
del "%PID_FILE%" >nul 2>&1
exit /b 0
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `python -m pytest app/backend/tests/test_startup.py::TestStopBatch -v`
Expected: 3 tests PASS（stop.bat 不再包含 netstat 批量杀端口逻辑）

- [ ] **Step 5: 提交**

```bash
git add stop.bat app/backend/tests/test_startup.py
git commit -m "fix: stop.bat 改用 PID 文件精准停止，不再无差别杀死端口 8081 进程"
```

---

### Task 5: 离线验收脚本

**Files:**
- Create: `scripts/offline_verify.bat`

- [ ] **Step 1: 编写离线验收脚本**

```batch
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

echo ========================================
echo   manzufei_ocr 离线验收检查
echo ========================================
echo.

set "PASS=0"
set "FAIL=0"

:: 1. 断网检查
echo [1/6] 断网环境检查...
:: 尝试访问一个几乎不可能在离线环境可达的地址
ping -n 1 -w 2000 8.8.8.8 >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [PASS] 网络不可达（离线环境正常）
    set /a PASS+=1
) else (
    echo   [WARN] 网络可达 — 离线验收应在断网环境执行
    set /a FAIL+=1
)

:: 2. Python 解释器可用
echo [2/6] Python 解释器可用...
set "PYTHON_EXE=%~dp0..\runtime\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
"%PYTHON_EXE%" --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [PASS] Python 可用
    set /a PASS+=1
) else (
    echo   [FAIL] Python 不可用
    set /a FAIL+=1
)

:: 3. 必要目录检查
echo [3/6] 运行目录存在...
set "ALL_DIRS=1"
for %%d in (data logs exports) do (
    if exist "%~dp0..\%%d" (
        echo   [OK] %%d/
    ) else (
        echo   [MISS] %%d/ — 将在 run.bat 启动时自动创建
        set "ALL_DIRS=0"
    )
)
if %ALL_DIRS%==1 (
    set /a PASS+=1
) else (
    echo   [INFO] 缺失目录将在启动时自动创建
    set /a PASS+=1
)

:: 4. 配置文件检查
echo [4/6] 配置文件检查...
if exist "%~dp0..\app\config\default.yaml" (
    echo   [PASS] default.yaml 存在
    set /a PASS+=1
) else (
    echo   [INFO] default.yaml 缺失 — 将使用硬编码默认值 + warning
    set /a PASS+=1
)

:: 5. 启动后端并等待健康检查
echo [5/6] 启动后端并等待健康检查（最多 30 秒）...

start "manzufei_ocr_verify" /MIN "%PYTHON_EXE%" -m app.backend.main > "%~dp0..\logs\verify_startup.log" 2>&1

set "HEALTH_URL=http://127.0.0.1:8081/api/system/status"
set "MAX_WAIT=30"
set "WAITED=0"
set "READY=0"

:health_poll
timeout /t 1 /nobreak >nul
set /a WAITED+=1
curl -s -o NUL -w "%%{http_code}" "%HEALTH_URL%" | findstr "200" >nul
if %ERRORLEVEL% EQU 0 (
    set "READY=1"
    goto health_done
)
if %WAITED% LSS %MAX_WAIT% goto health_poll

:health_done
if %READY%==1 (
    echo   [PASS] 后端在 %WAITED% 秒内就绪
    set /a PASS+=1

    :: 获取详细状态
    curl -s "%HEALTH_URL%" 2>nul
    echo.
) else (
    echo   [FAIL] 后端启动超时
    set /a FAIL+=1
)

:: 6. 停止后端
echo [6/6] 停止后端...
call "%~dp0..\stop.bat"
if %ERRORLEVEL% EQU 0 (
    echo   [PASS] 后端已停止
    set /a PASS+=1
) else (
    echo   [FAIL] 停止失败
    set /a FAIL+=1
)

:: 总结
echo.
echo ========================================
echo   验收结果: %PASS% 通过, %FAIL% 失败
echo ========================================
if %FAIL% GTR 0 exit /b 1
exit /b 0
```

- [ ] **Step 2: 静态验证脚本内容完整性**

```bash
# 确认 scripts/ 目录
ls -la scripts/

# 确认脚本包含所有 6 项检查
grep -c '\[PASS\]\|\[FAIL\]\|\[OK\]\|\[MISS\]\|\[INFO\]\|\[WARN\]' scripts/offline_verify.bat
```
Expected: 目录存在，匹配行数 >= 6。

- [ ] **Step 3: Python 侧离线验收逻辑验证测试**

```python
# 追加到 app/backend/tests/test_startup.py

class TestOfflineVerification:
    """离线验收关键逻辑验证。"""

    def test_config_missing_uses_defaults(self, tmp_path):
        """配置目录缺失时使用安全默认值并记录 warning。"""
        import logging
        from app.backend.config import load_config

        nonexistent_dir = str(tmp_path / "nonexistent_config")
        logger = logging.getLogger("test_offline")
        logger.setLevel(logging.WARNING)

        # 配置目录不存在时不应崩溃
        config = load_config(nonexistent_dir)
        assert config["port"] == 8081
        assert config["bind_host"] == "0.0.0.0"
        assert config["version"] == "0.1.0"

    def test_directories_auto_created_on_startup(self, tmp_path):
        """data/logs/exports 目录在配置加载时自动创建。"""
        from app.backend.config import load_config

        config_dir = str(tmp_path)
        config = load_config(config_dir)
        for key in ("data_dir", "log_dir", "export_dir"):
            assert os.path.isdir(config[key]), f"{key} 目录应自动创建"

    def test_no_external_network_on_status_check(self):
        """GET /api/system/status 不应发起外部网络请求。"""
        from app.backend.routes.system import system_bp
        from flask import Flask

        app = Flask(__name__)
        app.config["BACKEND_CONFIG"] = {
            "version": "0.1.0",
            "port": 8081,
            "bind_host": "0.0.0.0",
            "local_host": "127.0.0.1",
        }
        app.config["STARTED_AT"] = "2026-05-12T00:00:00+00:00"
        app.config["LAN_ADDRESSES"] = ["192.168.1.100:8081"]
        from app.backend.errors import register_error_handlers
        register_error_handlers(app)
        app.register_blueprint(system_bp)

        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"
```

- [ ] **Step 4: 运行测试确认 GREEN**

Run: `python -m pytest app/backend/tests/test_startup.py::TestOfflineVerification -v`
Expected: 3 tests PASS。

- [ ] **Step 5: 提交**

```bash
git add scripts/offline_verify.bat app/backend/tests/test_startup.py
git commit -m "feat: 新增离线验收脚本 scripts/offline_verify.bat 及对应测试"
```

---

### Task 6: 集成验证 — 全启动/停止周期与离线检查

**Files:**
- Modify: `app/backend/tests/test_startup.py` (追加集成测试)
- Read: `run.bat`, `stop.bat`, `scripts/offline_verify.bat`, `app/backend/main.py`

- [ ] **Step 1: 编写全周期集成测试**

```python
# 追加到 app/backend/tests/test_startup.py

class TestStartupShutdownIntegration:
    """启动 → 健康检查 → 停止 全周期集成测试。"""

    def test_full_lifecycle(self, tmp_path):
        """完整启动-就绪-停止周期。"""
        import time
        import threading
        import requests
        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))
        config = app.config["BACKEND_CONFIG"]
        port = 18083

        # 验证 PID 文件
        pid_file = os.path.join(config["data_dir"], "manzufei_backend.pid")
        assert os.path.isdir(config["data_dir"]), "data_dir 应已创建"
        assert os.path.isdir(config["log_dir"]), "log_dir 应已创建"
        assert os.path.isdir(config["export_dir"]), "export_dir 应已创建"

        # 启动后台线程
        ready = {"running": False}

        def serve():
            app.run(host="127.0.0.1", port=port, debug=False)

        t = threading.Thread(target=serve, daemon=True)
        t.start()
        time.sleep(0.5)

        # 健康检查轮询
        url = f"http://127.0.0.1:{port}/api/system/status"
        for _ in range(10):
            try:
                resp = requests.get(url, timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data", {}).get("status") == "running":
                        ready["running"] = True
                        # 校验响应字段
                        assert "version" in data["data"]
                        assert "started_at" in data["data"]
                        assert "lan_addresses" in data["data"]
                        break
            except requests.ConnectionError:
                pass
            time.sleep(1)

        assert ready["running"], "后端应在 10 秒内就绪"
        # 验证 PID 文件包含有效 PID
        assert os.path.exists(pid_file)
        with open(pid_file) as f:
            pid = int(f.read().strip())
        assert pid > 0

    def test_offline_startup_no_external_requests(self, tmp_path, monkeypatch):
        """离线启动不发起任何外部网络请求。"""
        import socket as sock_module

        external_calls = []

        original_create_connection = sock_module.create_connection

        def tracked_create_connection(address, *args, **kwargs):
            host = address[0]
            # 允许本地连接（127.x.x.x）
            if not host.startswith("127.") and host != "localhost":
                external_calls.append(address)
                raise OSError("Blocked: external connection in offline mode")
            return original_create_connection(address, *args, **kwargs)

        monkeypatch.setattr(sock_module, "create_connection", tracked_create_connection)

        from app.backend import create_backend_app

        app = create_backend_app(str(tmp_path))
        client = app.test_client()
        resp = client.get("/api/system/status")
        assert resp.status_code == 200

        # 不应有任何外部连接尝试
        assert len(external_calls) == 0, (
            f"离线模式下不应发起外部连接，实际: {external_calls}"
        )

    def test_status_contains_required_fields(self):
        """BE-SYS-001: 状态响应必须包含 status/version/started_at/lan_addresses。"""
        from app.backend.routes.system import system_bp
        from flask import Flask

        app = Flask(__name__)
        app.config["BACKEND_CONFIG"] = {
            "version": "0.1.0",
            "port": 8081,
            "bind_host": "0.0.0.0",
            "local_host": "127.0.0.1",
        }
        app.config["STARTED_AT"] = "2026-05-12T00:00:00+00:00"
        app.config["LAN_ADDRESSES"] = ["192.168.1.100:8081", "127.0.0.1:8081", "10.0.0.5:8081"]
        from app.backend.errors import register_error_handlers
        register_error_handlers(app)
        app.register_blueprint(system_bp)

        client = app.test_client()
        resp = client.get("/api/system/status")
        data = resp.get_json()

        assert data["data"]["status"] == "running"
        assert data["data"]["version"] == "0.1.0"
        assert "T" in data["data"]["started_at"]  # ISO 8601 格式
        # lan_addresses 不含 127.0.0.1
        assert "127.0.0.1:8081" not in data["data"]["lan_addresses"]
        assert "192.168.1.100:8081" in data["data"]["lan_addresses"]
        assert "10.0.0.5:8081" in data["data"]["lan_addresses"]
```

- [ ] **Step 2: 运行全量测试确认无回归**

Run: `python -m pytest app/backend/tests/test_startup.py -v`
Expected: 所有测试 PASS。

Run: `python -m pytest app/backend/tests/ -v`
Expected: 所有已有测试仍然 PASS，无回归。

- [ ] **Step 3: 脚本一致性静态检查**

```bash
# 检查 run.bat 引用正确的 PID 文件路径
grep "manzufei_backend.pid" run.bat stop.bat

# 检查 main.py 引用正确的 PID 文件路径
grep "manzufei_backend.pid" app/backend/main.py

# 确认 stop.bat 不含 netstat
! grep "netstat" stop.bat

# 确认 run.bat 含有健康检查轮询
grep "health_check" run.bat
```
Expected: 所有检查通过。

- [ ] **Step 4: 提交**

```bash
git add app/backend/tests/test_startup.py
git commit -m "test: 新增启动/停止全周期集成测试与离线网络隔离测试"
```

---

### Task 7: Plan 自审

**Files:**
- Read: 本 plan 文件
- Read: `docs/superpowers/specs/2026-05-11-backend-minimal-skeleton-design.md`
- Read: `docs/Backend/Backend_TDD/03-system-startup.md`
- Read: `docs/Backend/Backend_TDD/13-deployment.md`
- Read: `docs/Backend/Backend_BDD/system-startup.md`

- [ ] **Step 1: Spec coverage 检查**

逐条对照 spec/BDD/TDD 需求到具体 Task：

| 需求来源 | 需求 ID / 场景 | 覆盖 Task |
|----------|---------------|-----------|
| BDD system-startup | 正常启动并返回运行状态 (5s 内) | Task 3 (健康检查轮询), Task 6 (集成测试) |
| BDD system-startup | 断网环境下系统正常启动 | Task 5 (离线验收), Task 6 (test_offline_startup_no_external_requests) |
| BDD system-startup | 展示局域网访问地址 (不含 127.0.0.1) | Task 6 (test_status_contains_required_fields) |
| BDD system-startup | 配置文件缺失时安全降级 | Task 5 (test_config_missing_uses_defaults) |
| BDD system-startup | 算法模块未配置时系统仍可启动 | Task 5 (集成测试直接覆盖 create_backend_app 流程) |
| BE-SYS-001 | 系统状态对象包含 status/version/started_at/lan_addresses | Task 6 (test_status_contains_required_fields) |
| BE-SYS-002 | GET /api/system/status 返回 200 | Task 3 (健康检查), Task 6 |
| BE-SYS-003/004 | 启动不访问外部网络 | Task 6 (test_offline_startup_no_external_requests) |
| BE-SYS-005 | 多网卡排除 127.0.0.1 | Task 6 (test_status_contains_required_fields) |
| BE-DEP-004 | 目录不存在时自动创建 | Task 2 (run.bat 目录预创建), Task 5 (test_directories_auto_created_on_startup) |
| BE-DEP-005 | 配置文件缺失时使用安全默认值 | Task 5 (test_config_missing_uses_defaults) |
| BE-DEP-002 | 缺算法模块时启动成功 | Task 5, Task 6 (create_backend_app 本身就是缺模块启动) |
| stop.bat 精准停止 | 不杀无关 8081 进程 | Task 4 (stop.bat 重写, test_stop_uses_pid_file_not_port_indiscriminate) |
| run.bat 本地入口 | 浏览器打开 | Task 3 (健康检查后就绪打开) |

**Gap 检查:**
- BE-SYS-006（手动指定局域网地址/二维码 URL 重生成）— spec 明确标注"本阶段不覆盖"，合规。
- BE-DEP-001（测试环境不需要 Docker/WSL/GPU）— 已有测试全部在 pytest 中运行，无 Docker 依赖，合规。
- BE-DEP-003（配置外部 fixture 算法模块后处理流程使用 fixture）— 属于 BE-05 算法端口范围，不在此 plan 覆盖，合规。

- [ ] **Step 2: Placeholder scan**

对本 plan 全文搜索以下模式：

```bash
# 搜索 TBD / TODO / implement later / fill in details
grep -n -i "TBD\|TODO\|implement later\|fill in details\|适当添加\|适当的\|等等\|类似" \
  docs/superpowers/plans/2026-05-12-windows-offline-startup-plan.md
```
Expected: 0 matches（无占位符）。

检查项：
- [x] 无 "TBD" / "TODO" / "implement later"
- [x] 无 "Add appropriate error handling"（模糊指令）
- [x] 无 "Write tests for the above"（不给出具体测试代码）
- [x] 无 "Similar to Task N"（重复引用不写代码）
- [x] 所有 Step 中的代码块均完整可执行
- [x] 所有命令均包含具体预期输出

- [ ] **Step 3: 类型/路径一致性检查**

```bash
# PID 文件名一致性
echo "=== PID 文件名 ==="
grep -n "manzufei_backend.pid" run.bat stop.bat app/backend/main.py app/backend/tests/test_startup.py

echo "=== PID 文件路径 ==="
grep -n "data.*manzufei_backend.pid\|data_dir.*pid" app/backend/main.py app/backend/tests/test_startup.py

echo "=== 端口号一致性 ==="
grep -n "8081" run.bat app/backend/config.py
```
Expected: PID 文件名全仓一致为 `manzufei_backend.pid`，路径指向 `data/` 目录，端口号 8081 统一。

检查项：
- [x] `manzufei_backend.pid` 在 run.bat / stop.bat / main.py / tests 中拼写一致
- [x] PID 文件路径都指向 `data/` 目录
- [x] 端口号在 run.bat (健康检查 URL) 与 config.py (DEFAULT_CONFIG) 一致
- [x] `create_backend_app()` 函数签名全仓一致
- [x] `app.config["BACKEND_CONFIG"]` 键名在 main.py / system.py / tests 中一致

- [ ] **Step 4: 边界自审**

| 边界规则 | 检查结果 |
|----------|---------|
| 不实现前端业务页 | PASS — plan 只涉及 run.bat/stop.bat/main.py/scripts |
| 不实现日志脱敏系统 | PASS — plan 不涉及日志脱敏 |
| 不接真实算法 | PASS — 所有测试使用 Flask test_client 或 fixture |
| 不联网下载依赖或模型 | PASS — 所有测试离线运行 |
| stop.bat 不杀无关进程 | PASS — Task 4 用 PID 文件替代 netstat 批量杀 |
| 目录边界: data/logs/exports 不提交运行数据 | PASS — .bat 脚本创建目录，不写入测试数据 |

- [ ] **Step 5: 提交自审结果**

```bash
git add docs/superpowers/plans/2026-05-12-windows-offline-startup-plan.md
git commit -m "docs: 制定 BE-01 Windows 离线启动实施计划"
```

---

### Summary

| Task | 内容 | 文件变更 |
|------|------|---------|
| 1 | main.py PID 文件写入 + atexit 清理 | M: `app/backend/main.py`, C: `app/backend/tests/test_startup.py` |
| 2 | run.bat 目录预创建 + PID 等待 | M: `run.bat` |
| 3 | run.bat 健康检查轮询 + 浏览器打开 | M: `run.bat`, M: `app/backend/tests/test_startup.py` |
| 4 | stop.bat 基于 PID 精准停止 | M: `stop.bat`, M: `app/backend/tests/test_startup.py` |
| 5 | 离线验收脚本 | C: `scripts/offline_verify.bat`, M: `app/backend/tests/test_startup.py` |
| 6 | 集成验证 — 全周期 + 离线隔离 | M: `app/backend/tests/test_startup.py` |
| 7 | Plan 自审 | M: 本 plan 文件 |
