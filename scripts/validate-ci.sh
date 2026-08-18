#!/usr/bin/env bash
set -e

echo "==================================================="
echo "  Eva-AI Local CI/CD Pre-flight Validation"
echo "==================================================="
echo ""

echo "[1/5] Checking Python formatting and linting (Ruff)..."
python -m ruff format --check backend
python -m ruff check backend
echo "[PASS] Python code style and linting clean."
echo ""

echo "[2/5] Running Backend Unit Tests..."
pytest backend/tests/unit -v
echo "[PASS] Backend unit tests passed."
echo ""

echo "[3/5] Checking Frontend TypeScript Types..."
(cd frontend && npm run typecheck)
echo "[PASS] TypeScript types valid."
echo ""

echo "[4/5] Running Frontend ESLint..."
(cd frontend && npm run lint)
echo "[PASS] Frontend linting passed."
echo ""

echo "[5/5] Testing Frontend Production Build..."
(cd frontend && NEXT_OUTPUT=export npm run build)
echo "[PASS] Frontend production build succeeded."
echo ""

echo "==================================================="
echo "  [SUCCESS] All CI/CD pre-flight checks passed!"
echo "==================================================="
