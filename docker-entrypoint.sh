#!/bin/sh
# Production entrypoint.
#
# data/index/ is gitignored, so a VPS build context never contains a prebuilt
# index. Rather than shipping an empty deployment that answers "no evidence
# available", build the index on first boot and persist it in the mounted volume.
# Subsequent restarts detect the existing index and skip straight to serving.

set -e

INDEX_DB="/app/data/index/chroma.sqlite3"
MANIFEST_FILE="/app/data/index/manifest.json"

NEEDS_INGEST=0

if [ "$FORCE_REINDEX" = "true" ] || [ "$REBUILD_INDEX" = "true" ]; then
    echo "[entrypoint] FORCE_REINDEX or REBUILD_INDEX is set to true. Rebuilding index..."
    NEEDS_INGEST=1
elif [ ! -f "$INDEX_DB" ] || [ ! -f "$MANIFEST_FILE" ]; then
    echo "[entrypoint] No complete index found at $INDEX_DB. Ingesting..."
    NEEDS_INGEST=1
else
    echo "[entrypoint] Verifying existing index compatibility with configured embedder..."
    if ! python -c "
import sys
from backend.app.config import get_settings
from backend.app.retrieval.factory import get_shared_store, get_shared_retriever
try:
    settings = get_settings()
    store = get_shared_store(settings)
    manifest = store.read_manifest()
    if not manifest:
        sys.exit(1)
    embedder = get_shared_retriever(settings).embedder
    index_dims = store.dimension_of(store.collection_name)
    if index_dims and embedder.dimensions and index_dims != embedder.dimensions:
        print(f'[entrypoint] Mismatch: index has {index_dims} dims, query embedder produces {embedder.dimensions} dims.')
        sys.exit(1)
except Exception as e:
    print(f'[entrypoint] Verification check error: {e}')
    sys.exit(1)
sys.exit(0)
" ; then
        echo "[entrypoint] Existing index is incompatible (dimension/model mismatch). Auto-rebuilding index..."
        NEEDS_INGEST=1
    else
        echo "[entrypoint] Existing index verified and compatible."
    fi
fi

if [ "$NEEDS_INGEST" -eq 1 ]; then
    echo "[entrypoint] Building/rebuilding index from registered corpus..."
    python -m backend.app.cli ingest
    echo "[entrypoint] Index built successfully."
fi

echo "[entrypoint] Starting API on port ${PORT:-8000}..."
exec uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
