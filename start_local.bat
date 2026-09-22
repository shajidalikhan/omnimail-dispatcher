@echo off
title OmniMail Dispatcher - Local Mode
cd /d "%~dp0"

echo ========================================================
echo   OmniMail Dispatcher - Single-Machine Local Launcher
echo ========================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your system PATH!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Be sure to check "Add python.exe to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Activate virtual environment if present
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
) else if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo [*] Launching OmniMail Dispatcher in Local Mode...
python run_local.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Server exited with an error code: %ERRORLEVEL%
    echo If required packages are missing, install them with:
    echo     pip install -r requirements.txt
    echo.
    pause
)
