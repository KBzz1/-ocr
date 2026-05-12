#!/usr/bin/env python3
"""离线启动验收脚本。

检查项:
  1. 断网环境检查
  2. Python 解释器可用
  3. 运行目录存在
  4. 配置文件检查
  5. 启动后端并等待健康检查
  6. 停止后端

用法:
  python scripts/offline_startup_check.py
"""
import os
import sys
import time
import json
import subprocess
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_URL = "http://127.0.0.1:8081/api/system/status"
MAX_WAIT = 30


def check_network():
    """检查断网环境：尝试 ping 外部地址，失败则为离线。"""
    print("[1/6] 断网环境检查...")
    try:
        subprocess.run(
            ["ping", "-n" if sys.platform == "win32" else "-c", "1",
             "-w" if sys.platform == "win32" else "-W", "2", "8.8.8.8"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3
        )
        print("  [WARN] 网络可达 — 离线验收应在断网环境执行")
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("  [PASS] 网络不可达（离线环境正常）")
        return True


def check_python():
    """检查 Python 解释器可用。"""
    print("[2/6] Python 解释器可用...")
    try:
        result = subprocess.run(
            [sys.executable, "--version"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5
        )
        if result.returncode == 0:
            print(f"  [PASS] Python 可用 ({result.stdout.decode().strip()})")
            return True
    except Exception:
        pass
    print("  [FAIL] Python 不可用")
    return False


def check_directories():
    """检查必要运行目录，缺失目录将在 startup 时自动创建。"""
    print("[3/6] 运行目录检查...")
    dirs = ["data", "logs", "exports"]
    all_ok = True
    for d in dirs:
        path = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(path):
            print(f"  [OK] {d}/")
        else:
            print(f"  [INFO] {d}/ 缺失 — 将在 run.bat 启动时自动创建")
            all_ok = False
    return True  # 缺失不算失败


def check_config():
    """检查配置文件是否存在。"""
    print("[4/6] 配置文件检查...")
    config_path = os.path.join(PROJECT_ROOT, "app", "config", "default.yaml")
    if os.path.isfile(config_path):
        print("  [PASS] default.yaml 存在")
    else:
        print("  [INFO] default.yaml 缺失 — 将使用硬编码默认值 + warning 日志")
    return True  # 缺失不算失败


def check_backend_startup():
    """启动后端并等待健康检查。"""
    print(f"[5/6] 启动后端并等待健康检查（最多 {MAX_WAIT} 秒）...")

    # 启动后端
    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "verify_startup.log")

    with open(log_file, "wb") as f:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.backend.main"],
            stdout=f, stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT,
        )

    waited = 0
    ready = False
    while waited < MAX_WAIT:
        try:
            resp = urllib.request.urlopen(HEALTH_URL, timeout=2)
            if resp.status == 200:
                body = json.loads(resp.read().decode())
                if body.get("data", {}).get("status") == "running":
                    ready = True
                    print(f"  [PASS] 后端在 {waited} 秒内就绪")
                    print(f"  状态响应: {json.dumps(body, ensure_ascii=False)}")
                    break
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(1)
        waited += 1

    if not ready:
        print(f"  [FAIL] 后端启动超时（{MAX_WAIT} 秒）")
        return False, proc

    return ready, proc


def check_backend_stop(proc):
    """停止后端进程。"""
    print("[6/6] 停止后端...")
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        print("  [PASS] 后端已停止")

        # 清理 PID 文件
        pid_file = os.path.join(PROJECT_ROOT, "logs", "backend.pid")
        if os.path.exists(pid_file):
            print("  [WARN] PID 文件未被清理（应被 atexit 或 stop.bat 清理）")
        return True
    except Exception as e:
        print(f"  [FAIL] 停止失败: {e}")
        return False


def main():
    print("=" * 40)
    print("  manzufei_ocr 离线验收检查")
    print("=" * 40)
    print()

    failures = 0

    if not check_network():
        failures += 1
    if not check_python():
        failures += 1
        print("\n[ABORT] Python 不可用，无法继续")
        return 1
    check_directories()
    check_config()

    ready, proc = check_backend_startup()
    if not ready:
        failures += 1
        try:
            proc.terminate()
        except Exception:
            pass
    else:
        if not check_backend_stop(proc):
            failures += 1

    print()
    print("=" * 40)
    print(f"  验收结果: {6 - failures}/6 通过")
    print("=" * 40)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
