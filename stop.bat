@echo off
setlocal

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8081" ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>nul
)
