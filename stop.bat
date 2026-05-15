@echo off
setlocal enabledelayedexpansion

pushd "%~dp0" || (
    echo Failed to enter project directory: %~dp0
    pause
    exit /b 1
)

set "ROOT_DIR=%CD%"
set "PID_FILE=%ROOT_DIR%\logs\backend.pid"
set "FRONTEND_PID_FILE=%ROOT_DIR%\logs\frontend.pid"

call :stop_frontend
call :stop_backend

popd
exit /b 0

:stop_frontend
if not exist "%FRONTEND_PID_FILE%" (
    echo Frontend PID file does not exist: %FRONTEND_PID_FILE%
    exit /b 0
)

set /p FRONTEND_PID=<"%FRONTEND_PID_FILE%"
if "%FRONTEND_PID%"=="" (
    echo Frontend PID file is empty. Cleaning file.
    del "%FRONTEND_PID_FILE%" >nul 2>nul
    exit /b 0
)

wmic process where ProcessId=%FRONTEND_PID% get CommandLine 2>nul | findstr /I "npm node vite cmd.exe" >nul
if %ERRORLEVEL% NEQ 0 (
    echo PID %FRONTEND_PID% is not a manzufei_ocr frontend process. Cleaning stale PID file.
    del "%FRONTEND_PID_FILE%" >nul 2>nul
    exit /b 0
)

echo Stopping manzufei_ocr frontend (PID: %FRONTEND_PID%)...
taskkill /PID %FRONTEND_PID% /T /F >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Frontend stopped.
) else (
    echo Frontend process %FRONTEND_PID% does not exist or could not be stopped.
)

del "%FRONTEND_PID_FILE%" >nul 2>nul
exit /b 0

:stop_backend
if not exist "%PID_FILE%" (
    echo Backend PID file does not exist: %PID_FILE%
    echo Backend may not be running.
    exit /b 0
)

set /p BACKEND_PID=<"%PID_FILE%"
if "%BACKEND_PID%"=="" (
    echo Backend PID file is empty. Cleaning file.
    del "%PID_FILE%" >nul 2>nul
    exit /b 0
)

wmic process where ProcessId=%BACKEND_PID% get CommandLine 2>nul | findstr "app.backend.main" >nul
if %ERRORLEVEL% NEQ 0 (
    echo PID %BACKEND_PID% is not a manzufei_ocr backend process. Cleaning stale PID file.
    del "%PID_FILE%" >nul 2>&1
    exit /b 0
)

echo Stopping manzufei_ocr backend (PID: %BACKEND_PID%)...
taskkill /PID %BACKEND_PID% /F >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Backend stopped.
) else (
    echo Backend process %BACKEND_PID% does not exist or could not be stopped.
)

del "%PID_FILE%" >nul 2>&1
exit /b 0
