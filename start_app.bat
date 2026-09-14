@echo off
title Job Search Automation Web App
echo =======================================================
echo      Starting Job Search Automation Web App
echo =======================================================
echo.

:: Change directory to the folder where this batch file is located
cd /d "%~dp0"

:: Check for virtual environment
if exist ".venv\Scripts\activate.bat" (
    echo [*] Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    echo [!] Virtual environment not found at .venv\Scripts\activate.bat.
    echo [*] Checking for system Python...
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python 3.11+ from https://python.org
        pause
        exit /b 1
    )
    set "PYTHON_EXE=python"
)

:: Verify dependencies
"%PYTHON_EXE%" -c "import fastapi, uvicorn" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing required packages from requirements.txt...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [*] Installing Playwright Chromium browser...
    "%PYTHON_EXE%" -m playwright install chromium
)

:: Automatically launch browser after 2 seconds
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

echo.
echo =======================================================
echo  App URL: http://127.0.0.1:8000
echo  Press Ctrl+C in this window to stop the server.
echo =======================================================
echo.

:: Launch FastAPI backend and frontend server
"%PYTHON_EXE%" -m uvicorn web.backend.app:app --host 127.0.0.1 --port 8000

pause
