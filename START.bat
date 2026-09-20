@echo off
title HealthAI Lite — Backend Launcher
color 0B
echo.
echo  HealthAI Lite — Starting backend server...
echo  =============================================
echo.

cd /d "%~dp0backend"
set "PYTHON=..\.venv\Scripts\python.exe"

:: Check if Python is available
%PYTHON% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo  [1/3] Installing dependencies...
%PYTHON% -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo  [ERROR] pip install failed. Check your Python environment.
    pause
    exit /b 1
)

echo  [2/3] Dependencies ready.
echo.
echo  [3/3] Starting FastAPI server...
echo.
echo  -----------------------------------------------
echo  App URL:     http://localhost:8000
echo  API Docs:    http://localhost:8000/docs
echo  Credentials: admin / admin123
echo  -----------------------------------------------
echo.
echo  Opening browser in 2 seconds...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

%PYTHON% -m uvicorn main:app --reload --port 8000
pause
