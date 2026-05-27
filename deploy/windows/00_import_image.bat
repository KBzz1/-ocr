@echo off
setlocal enabledelayedexpansion
pushd "%~dp0" || exit /b 1

if not exist "deploy_debug_logs" md "deploy_debug_logs"
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_ID=%%I"
set "LOG_FILE=deploy_debug_logs\import_%RUN_ID%.log"

call :log "Starting image import from %CD%"
call :log "Debug log: %LOG_FILE%"
call :log "Collecting Docker version"
docker version >> "%LOG_FILE%" 2>&1

if not exist "images\manzufei-ocr.tar" (
  call :log "ERROR: Missing image file: images\manzufei-ocr.tar"
  pause
  exit /b 1
)

docker version >nul 2>nul
if errorlevel 1 (
  call :log "ERROR: Docker is not available. Start Docker Desktop first."
  pause
  exit /b 1
)

call :log "Loading Docker image. This can take several minutes..."
docker load -i "images\manzufei-ocr.tar" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :log "ERROR: Failed to load Docker image."
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)

call :log "Image loaded successfully."
docker images manzufei-ocr >> "%LOG_FILE%" 2>&1
call :log "Send this log file if later startup fails: %LOG_FILE%"
pause
popd
exit /b 0

:log
echo [%date% %time%] %~1
>> "%LOG_FILE%" echo [%date% %time%] %~1
exit /b 0
