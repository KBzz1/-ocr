@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0runtime\python\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

start "manzufei_ocr_backend" "%PYTHON_EXE%" -m app.backend.main
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8081"
