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

set "OCR_IMAGE_TAR="
if exist "images\manzufei-ocr.tar" set "OCR_IMAGE_TAR=images\manzufei-ocr.tar"
if not defined OCR_IMAGE_TAR (
  for %%F in ("images\*ocr*.tar") do (
    if not defined OCR_IMAGE_TAR if exist "%%~fF" set "OCR_IMAGE_TAR=%%~fF"
  )
)
if not defined OCR_IMAGE_TAR (
  call :log "ERROR: Missing OCR image tar. Put manzufei-ocr.tar under images."
  call :log "Current images directory:"
  dir /b "images" >> "%LOG_FILE%" 2>&1
  pause
  exit /b 1
)
call :log "Using OCR image tar: %OCR_IMAGE_TAR%"

docker version >nul 2>nul
if errorlevel 1 (
  call :log "ERROR: Docker is not available. Start Docker Desktop first."
  pause
  exit /b 1
)

call :log "Loading OCR Docker image from tar. This can take several minutes..."
docker load -i "%OCR_IMAGE_TAR%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :log "ERROR: Failed to load Docker image."
  call :log "Send this log file for troubleshooting: %LOG_FILE%"
  pause
  exit /b 1
)
call :ensure_image_tag "manzufei-ocr:0.1.0" "manzufei-ocr:latest"

call :log "Image loaded successfully."
docker images manzufei-ocr >> "%LOG_FILE%" 2>&1

set "QWEN_IMAGE_TAR="
if exist "images\qwen-vllm-server.tar" set "QWEN_IMAGE_TAR=images\qwen-vllm-server.tar"
if not defined QWEN_IMAGE_TAR (
  for %%F in ("images\*qwen*.tar") do (
    if not defined QWEN_IMAGE_TAR if exist "%%~fF" set "QWEN_IMAGE_TAR=%%~fF"
  )
)
if not defined QWEN_IMAGE_TAR (
  call :log "ERROR: Missing Qwen image tar. Put qwen-vllm-server.tar under images."
  call :log "Current images directory:"
  dir /b "images" >> "%LOG_FILE%" 2>&1
  pause
  exit /b 1
)
call :log "Using Qwen image tar: %QWEN_IMAGE_TAR%"
docker image inspect "qwen-vllm-openai:verified" >nul 2>nul
if not errorlevel 1 (
  call :log "Image tag already available; skipping load: qwen-vllm-openai:verified"
) else (
  call :log "Loading qwen-vllm-server image. This can take several minutes..."
  docker load -i "%QWEN_IMAGE_TAR%" >> "%LOG_FILE%" 2>&1
  if errorlevel 1 (
    call :log "ERROR: Failed to load qwen-vllm-server image."
    call :log "Send this log file for troubleshooting: %LOG_FILE%"
    pause
    exit /b 1
  )
  call :ensure_image_tag "qwen-vllm-openai:verified" "vllm/vllm-openai:latest"
)
call :log "qwen-vllm-server image loaded successfully."
docker images qwen-vllm-openai >> "%LOG_FILE%" 2>&1

call :log "Send this log file if later startup fails: %LOG_FILE%"
pause
popd
exit /b 0

:log
echo [%date% %time%] %~1
>> "%LOG_FILE%" echo [%date% %time%] %~1
exit /b 0

:ensure_image_tag
set "EXPECTED_TAG=%~1"
set "SOURCE_TAG=%~2"
docker image inspect "%EXPECTED_TAG%" >nul 2>nul
if not errorlevel 1 (
  call :log "Image tag already available: %EXPECTED_TAG%"
  exit /b 0
)
call :log "Expected image tag missing after load; retagging %SOURCE_TAG% as %EXPECTED_TAG%"
docker image inspect "%SOURCE_TAG%" >nul 2>nul
if errorlevel 1 (
  call :log "ERROR: Source image tag is also missing: %SOURCE_TAG%"
  call :log "Current Docker images:"
  docker images >> "%LOG_FILE%" 2>&1
  pause
  exit /b 1
)
docker tag "%SOURCE_TAG%" "%EXPECTED_TAG%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :log "ERROR: Failed to retag image as %EXPECTED_TAG%."
  call :log "Run docker images and compare tags with docker-compose.yml."
  pause
  exit /b 1
)
call :log "Retagged image as %EXPECTED_TAG%"
exit /b 0
