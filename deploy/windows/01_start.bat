@echo off
setlocal enabledelayedexpansion
pushd "%~dp0" || exit /b 1

if not exist "deploy_debug_logs" md "deploy_debug_logs"
for /f %%I in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "RUN_ID=%%I"
set "LOG_FILE=deploy_debug_logs\start_%RUN_ID%.log"

call :log "Starting manzufei OCR workstation from %CD%"
call :log "Debug log: %LOG_FILE%"
call :collect_host_diagnostics

docker version >nul 2>nul
if errorlevel 1 (
  call :log "ERROR: Docker is not available. Start Docker Desktop first."
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
  call :log "ERROR: Docker Compose is not available. Update Docker Desktop."
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)

if not exist "app\config\local.yaml" (
  call :log "ERROR: Missing config file: app\config\local.yaml"
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)

if not exist "models\llm" (
  call :log "ERROR: Missing models directory: models\llm"
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)

if not exist "data" md "data"
if not exist "exports" md "exports"
if not exist "logs" md "logs"

call :log "Validating docker compose config"
docker compose config >> "%LOG_FILE%" 2>&1

call :log "Starting manzufei OCR workstation..."
docker compose up -d >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :log "ERROR: Failed to start container."
  call :collect_failure_diagnostics
  call :log "Send this whole folder for troubleshooting: deploy_debug_logs"
  pause
  exit /b 1
)

call :log "Container start command completed."
docker compose ps >> "%LOG_FILE%" 2>&1

set "HEALTH_URL=http://127.0.0.1:8081/api/system/status"
set "WORKSTATION_URL=http://127.0.0.1:8081/"
set "WAITED=0"
set "MAX_WAIT=60"

:wait_health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if !ERRORLEVEL! EQU 0 goto ready

call :log "Waiting for health check: %HEALTH_URL% (!WAITED!/!MAX_WAIT! seconds)"
timeout /t 2 /nobreak >nul
set /a WAITED+=2
if !WAITED! LSS !MAX_WAIT! goto wait_health

call :log "ERROR: Startup timed out."
call :collect_failure_diagnostics
echo Startup timed out. Showing recent logs:
docker compose logs --tail 80
call :log "Send this whole folder for troubleshooting: deploy_debug_logs"
pause
exit /b 1

:ready
call :log "Health check passed: %HEALTH_URL%"
call :collect_runtime_diagnostics
call :log "Workstation is ready: %WORKSTATION_URL%"
call :log "Keep this log if OCR/GPU processing later fails: %LOG_FILE%"
start "" "%WORKSTATION_URL%"
popd
exit /b 0

:log
echo [%date% %time%] %~1
>> "%LOG_FILE%" echo [%date% %time%] %~1
exit /b 0

:section
>> "%LOG_FILE%" echo.
>> "%LOG_FILE%" echo ===== %~1 =====
exit /b 0

:collect_host_diagnostics
call :section "Host diagnostics"
echo Current directory: %CD% >> "%LOG_FILE%"
echo Computer: %COMPUTERNAME% >> "%LOG_FILE%"
echo User: %USERNAME% >> "%LOG_FILE%"
ver >> "%LOG_FILE%" 2>&1
docker version >> "%LOG_FILE%" 2>&1
docker compose version >> "%LOG_FILE%" 2>&1
docker info >> "%LOG_FILE%" 2>&1
where nvidia-smi >> "%LOG_FILE%" 2>&1
nvidia-smi >> "%LOG_FILE%" 2>&1
dir /s /b models >> "%LOG_FILE%" 2>&1
exit /b 0

:collect_runtime_diagnostics
call :section "Runtime diagnostics"
docker compose ps >> "%LOG_FILE%" 2>&1
docker inspect manzufei-ocr >> "%LOG_FILE%" 2>&1
docker exec manzufei-ocr python -c "import sys; print(sys.version)" >> "%LOG_FILE%" 2>&1
docker exec manzufei-ocr python -c "import paddle; print('paddle', paddle.__version__); print('cuda', paddle.version.cuda()); print('compiled_cuda', paddle.device.is_compiled_with_cuda()); print('device_count', paddle.device.cuda.device_count())" >> "%LOG_FILE%" 2>&1
docker exec manzufei-ocr python -c "import llama_cpp; print('llama_cpp import ok')" >> "%LOG_FILE%" 2>&1
docker compose logs --tail 120 >> "%LOG_FILE%" 2>&1
exit /b 0

:collect_failure_diagnostics
call :section "Failure diagnostics"
docker compose ps >> "%LOG_FILE%" 2>&1
docker inspect manzufei-ocr >> "%LOG_FILE%" 2>&1
docker compose logs --tail 300 >> "%LOG_FILE%" 2>&1
docker exec manzufei-ocr python -c "import paddle; print('paddle', paddle.__version__); print('cuda', paddle.version.cuda()); print('compiled_cuda', paddle.device.is_compiled_with_cuda()); print('device_count', paddle.device.cuda.device_count())" >> "%LOG_FILE%" 2>&1
exit /b 0
