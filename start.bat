@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Clinical Decision Support Lite — Project Launcher
echo ===================================================
echo.

REM 1. Check Python virtual environment
if not exist ".venv" (
    echo [INFO] Creating Python virtual environment in .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create Python virtual environment.
        echo Please ensure Python 3.13+ is installed and on your PATH.
        pause
        exit /b 1
    )
)

REM 2. Activate virtual environment and install backend requirements
echo [INFO] Checking & installing Python dependencies from requirements.txt ...
call .venv\Scripts\activate.bat
pip install -r requirements.txt

REM 3. Check .env configuration file
if not exist ".env" (
    echo [WARNING] .env file not found. Creating .env from .env.example ...
    copy .env.example .env >nul
    echo [IMPORTANT] Created .env file. Please set your OPENROUTER_API_KEY inside .env if needed.
)

REM 4. Check frontend dependencies
if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies (npm install) ...
    cd frontend
    call npm install
    cd ..
)

echo.
echo ===================================================
echo [1/2] Starting FastAPI Backend on http://localhost:8000 ...
start "CDS-Lite Backend (FastAPI)" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.app.main:app --reload --port 8000"

echo [2/2] Starting Next.js Frontend on http://localhost:3000 ...
start "CDS-Lite Frontend (Next.js)" cmd /k "cd frontend && npm run dev"

echo.
echo ===================================================
echo   All services launched in separate windows!
echo   -----------------------------------------------
echo   Web UI:         http://localhost:3000
echo   API Docs:       http://localhost:8000/docs
echo   Health Check:   http://localhost:8000/api/health
echo ===================================================
echo.
pause
