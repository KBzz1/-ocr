@echo off
setlocal
pushd "%~dp0" || exit /b 1

docker compose down
if errorlevel 1 (
  echo Failed to stop service.
  pause
  exit /b 1
)

echo Service stopped.
pause
popd
exit /b 0
