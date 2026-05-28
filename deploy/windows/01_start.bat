@echo off
setlocal enabledelayedexpansion
pushd "%~dp0" | exit /b 1

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

call :detect_public_base_url
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

:detect_public_base_url
set "HOST_LAN_IP="
call :log_ip_candidates
for /f "usebackq tokens=* delims= " %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$excludedAlias = '(?i)(docker|wsl|vEthernet|virtualbox|vmware|loopback)'; $best = $null; foreach ($cfg in Get-NetIPConfiguration) { $alias = [string]$cfg.InterfaceAlias; $adapter = $cfg.NetAdapter; if (-not $adapter -or $adapter.Status -ne 'Up' -or $alias -match $excludedAlias) { continue }; foreach ($addr in @($cfg.IPv4Address)) { $ip = [string]$addr.IPAddress; if ($ip -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' -or $ip -match '^(127|169\.254|172\.18)\.') { continue }; $score = 0; if ($cfg.IPv4DefaultGateway) { $score += 100 }; if ($alias -match '(?i)(wi-fi|wifi|wlan|wireless|hotspot|ethernet|local area connection)') { $score += 50 }; if ($ip -match '^(10|192\.168|172\.(1[6-9]|2[0-9]|3[0-1]))\.') { $score += 10 }; $candidate = [pscustomobject]@{ IPAddress = $ip; Score = $score }; if ($null -eq $best -or $candidate.Score -gt $best.Score) { $best = $candidate } } }; if ($best) { Write-Output $best.IPAddress.Trim() }"`) do if not "%%~I"=="" set "HOST_LAN_IP=%%~I"
call :validate_ipv4
if errorlevel 1 set "HOST_LAN_IP="
if "!HOST_LAN_IP!"=="" (
  call :log "WARNING: Could not auto-detect host LAN IPv4."
  echo.
  echo Could not auto-detect the Windows IPv4 for phone access.
  echo Run ipconfig and enter the IPv4 address of the Wi-Fi or hotspot adapter.
  echo Example: 172.20.10.5 or 192.168.43.10
  set /p HOST_LAN_IP=Enter Windows IPv4 for phone access, or press Enter to skip: 
  call :validate_ipv4
  if errorlevel 1 set "HOST_LAN_IP="
)
if not "!HOST_LAN_IP!"=="" (
  set "MANZUFEI_PUBLIC_BASE_URL=http://!HOST_LAN_IP!:8081"
  call :log "Mobile upload public URL base: !MANZUFEI_PUBLIC_BASE_URL!"
) else (
  set "MANZUFEI_PUBLIC_BASE_URL="
  call :log "WARNING: Phone QR access is disabled for this run."
  echo WARNING: Phone QR access is disabled for this run.
  echo The workstation will still start at http://127.0.0.1:8081/.
  echo Rerun 01_start.bat later and enter the Wi-Fi or hotspot IPv4 address to enable phone access.
)
exit /b 0

:log_ip_candidates
call :section "IPv4 candidates"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetIPConfiguration | ForEach-Object { $alias = [string]$_.InterfaceAlias; $status = if ($_.NetAdapter) { $_.NetAdapter.Status } else { '' }; $gateway = if ($_.IPv4DefaultGateway) { ($_.IPv4DefaultGateway | ForEach-Object { $_.NextHop }) -join ',' } else { '' }; foreach ($addr in @($_.IPv4Address)) { [pscustomobject]@{ Alias = $alias; Status = $status; IPv4 = $addr.IPAddress; Gateway = $gateway } } } | Format-Table -AutoSize" >> "%LOG_FILE%" 2>&1
exit /b 0

:validate_ipv4
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip = $env:HOST_LAN_IP.Trim(); if ($ip -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$') { exit 1 }; $parts = $ip.Split('.') | ForEach-Object { [int]$_ }; if (($parts | Where-Object { $_ -lt 0 -or $_ -gt 255 }).Count -gt 0) { exit 1 }; exit 0" >nul 2>nul
exit /b %ERRORLEVEL%

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
