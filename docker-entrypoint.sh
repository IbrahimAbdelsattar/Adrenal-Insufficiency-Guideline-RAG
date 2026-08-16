#!/bin/sh
# Production entrypoint.
#
# data/index/ is gitignored, so a VPS build context never contains a prebuilt
# index. Rather than shipping an empty deployment that answers "no evidence
# available", build the index on first boot and persist it in the mounted volume.
# Subsequent restarts detect the existing index and skip straight to serving.

set -e

INDEX_DB="/app/data/index/chroma.sqlite3"

if [ -f "$INDEX_DB" ]; then
    echo "[entrypoint] Existing index found at $INDEX_DB - skipping ingest."
else
    echo "[entrypoint] No index found. Building it from the registered corpus..."
    if [ -z "$OMNIROUTE_API_KEY" ] && [ -z "$OPENROUTER_API_KEY" ]; then
        echo "[entrypoint] ERROR: OMNIROUTE_API_KEY is not set." >&2
        echo "[entrypoint] The index cannot be built and search will not work." >&2
        echo "[entrypoint] Set it in your deployment platform's environment settings." >&2
        exit 5
    fi
    python -m backend.app.cli ingest
    echo "[entrypoint] Index built."
fi

echo "[entrypoint] Starting API on port ${PORT:-8000}..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
