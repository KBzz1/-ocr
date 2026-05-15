@echo off
setlocal enabledelayedexpansion

pushd "%~dp0" || (
    echo Failed to enter project directory: %~dp0
    pause
    exit /b 1
)

set "ROOT_DIR=%CD%"
set "PYTHON_EXE=%ROOT_DIR%\runtime\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "DATA_DIR=%ROOT_DIR%\data"
set "LOG_DIR=%ROOT_DIR%\logs"
set "EXPORT_DIR=%ROOT_DIR%\exports"
set "FRONTEND_DIR=%ROOT_DIR%\app\frontend"
set "FRONTEND_DIST_INDEX=%FRONTEND_DIR%\dist\index.html"

if not exist "%DATA_DIR%" md "%DATA_DIR%"
if not exist "%LOG_DIR%" md "%LOG_DIR%"
if not exist "%EXPORT_DIR%" md "%EXPORT_DIR%"

set "PID_FILE=%LOG_DIR%\backend.pid"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"
set "HEALTH_URL=http://127.0.0.1:8081/api/system/status"
set "WORKSTATION_URL=http://127.0.0.1:8081/"

call :ensure_frontend_dist
if errorlevel 1 goto fail

call :ensure_backend
if errorlevel 1 goto fail

echo Opening workstation: %WORKSTATION_URL%
start "" "%WORKSTATION_URL%"
popd
exit /b 0

:ensure_frontend_dist
if not exist "%FRONTEND_DIR%\package.json" (
    echo Frontend package.json not found: %FRONTEND_DIR%\package.json
    exit /b 1
)

echo [%date% %time%] Rebuilding manzufei_ocr frontend dist... >> "%FRONTEND_LOG%"
pushd "%FRONTEND_DIR%" >nul
call npm run build >> "%FRONTEND_LOG%" 2>&1
set "BUILD_RESULT=%ERRORLEVEL%"
popd >nul

if not "%BUILD_RESULT%"=="0" (
    echo Frontend build failed. Check log: %FRONTEND_LOG%
    exit /b 1
)

if not exist "%FRONTEND_DIST_INDEX%" (
    echo Frontend build did not create: %FRONTEND_DIST_INDEX%
    exit /b 1
)

echo Frontend dist is ready: %FRONTEND_DIST_INDEX%
exit /b 0

:ensure_backend
if exist "%PID_FILE%" (
    set /p BACKEND_PID=<"%PID_FILE%"
    echo Found existing PID file: %PID_FILE%
    call :check_url "%HEALTH_URL%"
    if !ERRORLEVEL! EQU 0 goto backend_ready_existing
    echo Existing backend PID is stale. Cleaning PID file.
    del "%PID_FILE%" >nul 2>nul
)

echo [%date% %time%] Starting manzufei_ocr backend... >> "%BACKEND_LOG%"
start "manzufei_ocr_backend" /MIN cmd /d /c ""%PYTHON_EXE%" -m app.backend.main >> "%BACKEND_LOG%" 2>&1"

set "MAX_WAIT=10"
set "WAITED=0"

:wait_backend_pid
if exist "%PID_FILE%" goto backend_pid_ready
timeout /t 1 /nobreak >nul
set /a WAITED+=1
if !WAITED! LSS !MAX_WAIT! goto wait_backend_pid

echo [%date% %time%] [ERROR] Backend startup timed out. PID file was not created. >> "%BACKEND_LOG%"
echo Backend startup timed out. Check log: %BACKEND_LOG%
exit /b 1

:backend_pid_ready
set /p BACKEND_PID=<"%PID_FILE%"
echo [%date% %time%] Backend PID: %BACKEND_PID% >> "%BACKEND_LOG%"

set "MAX_HEALTH_WAIT=30"
set "HEALTH_WAITED=0"

:backend_health_check
call :check_url "%HEALTH_URL%"
if !ERRORLEVEL! EQU 0 goto backend_ready
timeout /t 1 /nobreak >nul
set /a HEALTH_WAITED+=1
if !HEALTH_WAITED! LSS !MAX_HEALTH_WAIT! goto backend_health_check

echo [%date% %time%] [ERROR] Backend health check timed out. >> "%BACKEND_LOG%"
echo Backend health check timed out. Check log: %BACKEND_LOG%
exit /b 1

:backend_ready
echo Backend is ready: http://127.0.0.1:8081
exit /b 0

:backend_ready_existing
echo Backend is already running (PID: %BACKEND_PID%)
exit /b 0

:check_url
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%~1' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %ERRORLEVEL%

:fail
popd
pause
exit /b 1
