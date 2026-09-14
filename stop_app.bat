@echo off
title Stop Job Search Automation Web App
echo =======================================================
echo      Stopping Job Search Automation Web App
echo =======================================================
echo.

echo [*] Terminating processes listening on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [*] Killing process PID %%a...
    taskkill /f /pid %%a >nul 2>&1
)

echo [*] Stopping any lingering uvicorn processes...
taskkill /f /im python.exe /fi "WINDOWTITLE eq Job Search Automation*" >nul 2>&1

echo.
echo [OK] App server stopped.
timeout /t 2 >nul
