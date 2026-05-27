@echo off
setlocal
pushd "%~dp0" || exit /b 1

if not exist "images\manzufei-ocr.tar" (
  echo Missing image file: images\manzufei-ocr.tar
  pause
  exit /b 1
)

docker version >nul 2>nul
if errorlevel 1 (
  echo Docker is not available. Start Docker Desktop first.
  pause
  exit /b 1
)

echo Loading Docker image. This can take several minutes...
docker load -i "images\manzufei-ocr.tar"
if errorlevel 1 (
  echo Failed to load Docker image.
  pause
  exit /b 1
)

echo Image loaded successfully.
pause
popd
exit /b 0
