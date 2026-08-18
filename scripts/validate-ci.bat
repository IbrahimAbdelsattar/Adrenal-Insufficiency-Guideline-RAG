@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo   Eva-AI Local CI/CD Pre-flight Validation
echo ===================================================
echo.

echo [1/5] Checking Python formatting and linting (Ruff)...
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

echo [2/5] Running Backend Unit Tests...
pytest backend/tests/unit -v
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Backend unit tests failed.
    exit /b %ERRORLEVEL%
)
echo [PASS] Backend unit tests passed.
echo.

echo [3/5] Checking Frontend TypeScript Types...
cd frontend
call npm run typecheck
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Frontend TypeScript type check failed.
    cd ..
    exit /b %ERRORLEVEL%
)
echo [PASS] TypeScript types valid.
echo.

echo [4/5] Running Frontend ESLint...
call npm run lint
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Frontend ESLint failed.
    cd ..
    exit /b %ERRORLEVEL%
)
echo [PASS] Frontend linting passed.
echo.

echo [5/5] Testing Frontend Production Build...
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

echo ===================================================
echo   [SUCCESS] All CI/CD pre-flight checks passed!
echo ===================================================
