@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PID_FILE=%~dp0logs\backend.pid"

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

:: 校验进程命令行属于本项目（含 app.backend.main）才终止
wmic process where ProcessId=%BACKEND_PID% get CommandLine 2>nul | findstr "app.backend.main" >nul
if %ERRORLEVEL% NEQ 0 (
    echo PID %BACKEND_PID% 不是 manzufei_ocr 后端进程，拒绝终止。
    echo 如需强制终止，请手动执行: taskkill /PID %BACKEND_PID% /F
    exit /b 1
)

:: 精准终止
echo 正在停止 manzufei_ocr 后端 (PID: %BACKEND_PID%)...
taskkill /PID %BACKEND_PID% /F >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo 后端已停止。
) else (
    echo 进程 %BACKEND_PID% 已不存在或无法终止。
)

:: 清理 PID 文件
del "%PID_FILE%" >nul 2>&1
exit /b 0
