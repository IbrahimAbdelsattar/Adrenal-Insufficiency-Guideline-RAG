@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Eva AI CDS - Fast Windows Launcher
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

REM 2. Activate virtual environment and check if core requirements are installed
call .venv\Scripts\activate.bat

python -c "import fastapi, uvicorn, chromadb, fitz, tiktoken" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing Python dependencies from requirements.txt ...
    pip install -r requirements.txt
) else (
    echo [INFO] Python dependencies already installed. Skipping pip install.
)

REM 3. Check .env configuration file
if not exist ".env" (
    echo [WARNING] .env file not found. Creating .env from .env.example ...
    copy .env.example .env >nul
    echo [IMPORTANT] Created .env file. Please set your OPENROUTER_API_KEY inside .env if needed.
)

REM 4. Check frontend dependencies
if not exist "frontend\node_modules" (
    echo [INFO] Installing frontend dependencies - npm install ...
    cd frontend
    call npm install
    cd ..
) else (
    echo [INFO] Frontend dependencies already installed. Skipping npm install.
)

REM 5. Free ports 8010 and 3000 if already in use by previous sessions
echo [INFO] Ensuring ports 8010 and 3000 are available...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8010" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ===================================================
echo [1/2] Starting FastAPI Backend on http://localhost:8010 ...
start "Eva AI Backend (FastAPI)" cmd /k "call .venv\Scripts\activate.bat && uvicorn backend.app.main:app --reload --port 8010"

echo [INFO] Waiting 3 seconds for backend warmup...
timeout /t 3 /nobreak >nul

echo [2/2] Starting Next.js Frontend on http://localhost:3000 ...
start "Eva AI Frontend (Next.js)" cmd /k "cd frontend && npm run dev"

echo.
echo ===================================================
echo   Eva AI services launched in separate windows!
echo   -----------------------------------------------
echo   Web UI:         http://localhost:3000
echo   API Docs:       http://localhost:8010/docs
echo   Health Check:   http://localhost:8010/api/health
echo ===================================================
echo.
pause
