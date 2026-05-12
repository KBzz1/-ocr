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
set "PID_FILE=%~dp0logs\backend.pid"
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
