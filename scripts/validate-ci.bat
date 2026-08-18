@echo off
REM Local CI gate — mirrors .github/workflows/ci-cd.yml so pushes never reach
REM GitHub unverified. Standalone twin of validate-ci.sh for cmd.exe users.
setlocal enabledelayedexpansion

cd /d "%~dp0\.."

echo ===================================================
echo   Eva-AI Local CI/CD Pre-flight Validation
echo ===================================================
echo.

echo [1/7] Checking Python formatting and linting (Ruff)...
python -m ruff format --check backend
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Python formatting check failed. Run 'python -m ruff format backend' to fix.
    exit /b %ERRORLEVEL%
)
python -m ruff check backend
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Python lint check failed. Run 'python -m ruff check --fix backend' to fix.
    exit /b %ERRORLEVEL%
)
echo [PASS] Python code style and linting clean.
echo.

echo [2/7] Running Backend Unit Tests...
pytest backend/tests/unit -v
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Backend unit tests failed.
    exit /b %ERRORLEVEL%
)
echo [PASS] Backend unit tests passed.
echo.

echo [3/7] Running Backend Integration Tests...
pytest backend/tests/integration -v
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Backend integration tests failed.
    exit /b %ERRORLEVEL%
)
echo [PASS] Backend integration tests passed.
echo.

echo [4/7] Checking Frontend TypeScript Types...
cd frontend
call npm run typecheck
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Frontend TypeScript type check failed.
    cd ..
    exit /b %ERRORLEVEL%
)
echo [PASS] TypeScript types valid.
echo.

echo [5/7] Running Frontend ESLint...
call npm run lint
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Frontend ESLint failed.
    cd ..
    exit /b %ERRORLEVEL%
)
echo [PASS] Frontend linting passed.
echo.

echo [6/7] Testing Frontend Production Build...
set NEXT_OUTPUT=export
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Frontend production build failed.
    cd ..
    exit /b %ERRORLEVEL%
)
cd ..
echo [PASS] Frontend production build succeeded.
echo.

echo [7/7] Docker Build & Healthcheck Smoke Test...
where docker >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [SKIP] Docker not available - skipping smoke test.
    goto :success
)
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [SKIP] Docker daemon not running - skipping smoke test.
    goto :success
)

REM Build the stub index into a temp dir so the real data/index is untouched.
set "STUB_INDEX_DIR=%TEMP%\eva-stub-index-%RANDOM%%RANDOM%"
mkdir "%STUB_INDEX_DIR%"
echo   Building stub index into %STUB_INDEX_DIR% ...
set "INDEX_DIR=%STUB_INDEX_DIR%"
python scripts/build_stub_index.py
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Stub index build failed.
    rmdir /s /q "%STUB_INDEX_DIR%"
    exit /b %ERRORLEVEL%
)

echo   Building Docker image...
docker build -t eva-ai:test .
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Docker image build failed.
    rmdir /s /q "%STUB_INDEX_DIR%"
    exit /b %ERRORLEVEL%
)

echo   Starting smoke-test container...
docker rm -f eva-ai-smoke >nul 2>&1
docker run -d --name eva-ai-smoke -p 8000:8000 -v "%STUB_INDEX_DIR%:/app/data/index" eva-ai:test
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Container failed to start.
    rmdir /s /q "%STUB_INDEX_DIR%"
    exit /b %ERRORLEVEL%
)

echo   Waiting for health endpoint...
set "HEALTHY=0"
for /l %%i in (1,1,30) do (
    curl -s -f http://localhost:8000/api/health >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set "HEALTHY=1"
        goto :healthcheck_done
    )
    timeout /t 3 /nobreak >nul
)
:healthcheck_done

docker rm -f eva-ai-smoke >nul 2>&1
rmdir /s /q "%STUB_INDEX_DIR%"

if "%HEALTHY%" NEQ "1" (
    echo [FAIL] Container did not become healthy.
    exit /b 1
)
echo [PASS] Docker smoke test passed.
echo.

:success
echo ===================================================
echo   [SUCCESS] All CI/CD pre-flight checks passed!
echo ===================================================
