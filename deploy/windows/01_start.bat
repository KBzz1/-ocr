@echo off
setlocal enabledelayedexpansion
pushd "%~dp0" || exit /b 1

docker version >nul 2>nul
if errorlevel 1 (
  echo Docker is not available. Start Docker Desktop first.
  pause
  exit /b 1
)

docker compose version >nul 2>nul
if errorlevel 1 (
  echo Docker Compose is not available. Update Docker Desktop.
  pause
  exit /b 1
)

if not exist "app\config\local.yaml" (
  echo Missing config file: app\config\local.yaml
  pause
  exit /b 1
)

if not exist "models\llm" (
  echo Missing models directory: models\llm
  pause
  exit /b 1
)

if not exist "data" md "data"
if not exist "exports" md "exports"
if not exist "logs" md "logs"

echo Starting manzufei OCR workstation...
docker compose up -d
if errorlevel 1 (
  echo Failed to start container.
  pause
  exit /b 1
)

set "HEALTH_URL=http://127.0.0.1:8081/api/system/status"
set "WORKSTATION_URL=http://127.0.0.1:8081/"
set "WAITED=0"
set "MAX_WAIT=60"

:wait_health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri '%HEALTH_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if !ERRORLEVEL! EQU 0 goto ready

timeout /t 2 /nobreak >nul
set /a WAITED+=2
if !WAITED! LSS !MAX_WAIT! goto wait_health

echo Startup timed out. Showing recent logs:
docker compose logs --tail 80
pause
exit /b 1

:ready
echo Workstation is ready: %WORKSTATION_URL%
start "" "%WORKSTATION_URL%"
popd
exit /b 0
