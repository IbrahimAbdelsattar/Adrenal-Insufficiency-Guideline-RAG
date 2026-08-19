#!/usr/bin/env bash
# Local CI gate — mirrors .github/workflows/ci-cd.yml so pushes never reach
# GitHub unverified. Runs as a pre-push hook when core.hooksPath is set
# (see scripts/install-hooks.sh) or standalone: scripts/validate-ci.sh
set -e

cd "$(git rev-parse --show-toplevel)"

echo "==================================================="
echo "  Eva-AI Local CI/CD Pre-flight Validation"
echo "==================================================="
echo ""

echo "[1/7] Checking Python formatting and linting (Ruff)..."
python -m ruff format --check backend
python -m ruff check backend
echo "[PASS] Python code style and linting clean."
echo ""

echo "[2/7] Running Backend Unit Tests..."
pytest backend/tests/unit -v
echo "[PASS] Backend unit tests passed."
echo ""

echo "[3/7] Running Backend Integration Tests..."
pytest backend/tests/integration -v
echo "[PASS] Backend integration tests passed."
echo ""

echo "[4/7] Checking Frontend TypeScript Types..."
(cd frontend && npm run typecheck)
echo "[PASS] TypeScript types valid."
echo ""

echo "[5/7] Running Frontend ESLint..."
(cd frontend && npm run lint)
echo "[PASS] Frontend linting passed."
echo ""

echo "[6/7] Testing Frontend Production Build..."
(cd frontend && NEXT_OUTPUT=export NEXT_DIST_DIR=.next-build npm run build)
rm -rf frontend/.next-build frontend/out
echo "[PASS] Frontend production build succeeded."
echo ""

echo "[7/7] Docker Build & Healthcheck Smoke Test..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    # Build the stub index into a temp dir so the real data/index is untouched.
    STUB_INDEX_DIR="$(mktemp -d)"
    cleanup() {
        docker rm -f eva-ai-smoke >/dev/null 2>&1 || true
        rm -rf "$STUB_INDEX_DIR"
    }
    trap cleanup EXIT

    echo "  Building stub index into $STUB_INDEX_DIR ..."
    INDEX_DIR="$STUB_INDEX_DIR" python scripts/build_stub_index.py

    echo "  Building Docker image..."
    docker build -t eva-ai:test .

    echo "  Starting smoke-test container..."
    MOUNT_DIR="$STUB_INDEX_DIR"
    if command -v cygpath >/dev/null 2>&1; then
        MOUNT_DIR="$(cygpath -w "$STUB_INDEX_DIR")"
    fi
    SMOKE_PORT=8008
    docker run -d --name eva-ai-smoke -p "$SMOKE_PORT:8000" \
        -v "$MOUNT_DIR:/app/data/index" eva-ai:test

    echo "  Waiting for health endpoint..."
    HEALTHY=0
    for i in $(seq 1 30); do
        if curl -s -f "http://localhost:$SMOKE_PORT/api/health" >/dev/null 2>&1; then
            HEALTHY=1
            break
        fi
        sleep 3
    done

    if [ "$HEALTHY" -ne 1 ]; then
        echo "[FAIL] Container did not become healthy. Logs:"
        docker logs eva-ai-smoke
        exit 1
    fi
    echo "[PASS] Docker smoke test passed."
else
    echo "[SKIP] Docker not available or not running - skipping smoke test."
fi
echo ""

echo "==================================================="
echo "  [SUCCESS] All CI/CD pre-flight checks passed!"
echo "==================================================="
