"""ChromaDB persistence with multi-collection and fallback support.

Metadata lives on the vector entry itself, never a sidecar file — that is
Constitution Principle II enforced structurally rather than by convention.

Ingestion is atomic at the collection level: a new collection is built under a
temporary name and swapped in only on success, so a failed run leaves the previous
index intact and queryable (FR-020). Supports primary and fallback collections.
"""

from __future__ import annotations

import json
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, IndexManifest

BUILD_SUFFIX = "__building"


class VectorStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._settings.index_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(self._settings.index_path),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )

    @property
    def collection_name(self) -> str:
        return self._settings.chroma_collection

    @property
    def fallback_collection_name(self) -> str:
        return self._settings.fallback_chroma_collection

    # --- read -------------------------------------------------------------

    def _get(self, name: str):
        return self._client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    def count(self, collection_name: str | None = None) -> int:
        col_name = collection_name or self.collection_name
        try:
            return self._get(col_name).count()
        except Exception:
            return 0

    def is_ready(self, collection_name: str | None = None) -> bool:
        return self.count(collection_name) > 0

    def query(
        self,
        embedding: list[float],
        top_k: int,
        collection_name: str | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Cosine search over the designated collection. Returns (chunk, score) pairs, best first.

        Chroma reports cosine *distance*; score = 1 - distance, clamped to [0, 1].
        """
        col_name = collection_name or self.collection_name
        collection = self._get(col_name)
        if collection.count() == 0:
            return []

        raw = collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        ids = raw.get("ids", [[]])[0]
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        out: list[tuple[Chunk, float]] = []
        for chunk_id, text, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            out.append((Chunk.from_stored(chunk_id, text, dict(metadata)), score))
        return out

    def all_chunks(self, collection_name: str | None = None) -> list[Chunk]:
        """Every stored chunk in the designated collection."""
        col_name = collection_name or self.collection_name
        collection = self._get(col_name)
        if collection.count() == 0:
            return []
        raw = collection.get(include=["documents", "metadatas"])
        return [
            Chunk.from_stored(cid, text, dict(meta))
            for cid, text, meta in zip(
                raw.get("ids", []),
                raw.get("documents", []),
                raw.get("metadatas", []),
                strict=False,
            )
        ]

    def get_chunks(self, chunk_ids: list[str], collection_name: str | None = None) -> list[Chunk]:
        """Fetch specific chunks by ID from designated collection."""
        if not chunk_ids:
            return []
        col_name = collection_name or self.collection_name
        collection = self._get(col_name)
        raw = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
        return [
            Chunk.from_stored(cid, text, dict(meta))
            for cid, text, meta in zip(
                raw.get("ids", []),
                raw.get("documents", []),
                raw.get("metadatas", []),
                strict=False,
            )
        ]

    # --- write ------------------------------------------------------------

    def build(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
        collection_name: str | None = None,
    ) -> None:
        """Build into a staging collection, then swap it in atomically."""
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"{len(chunks)} chunks but {len(embeddings)} embeddings — refusing "
                "to build a misaligned index."
            )

        target_name = collection_name or self.collection_name
        staging_name = f"{target_name}{BUILD_SUFFIX}"
        self._drop(staging_name)
        staging = self._get(staging_name)

        # Chroma caps batch size; 500 stays well inside it.
        for start in range(0, len(chunks), 500):
            window = slice(start, start + 500)
            staging.add(
                ids=[c.chunk_id for c in chunks[window]],
                documents=[c.text for c in chunks[window]],
                metadatas=[c.to_metadata() for c in chunks[window]],
                embeddings=embeddings[window],
            )

        # Swap: only now is the previous index discarded.
        self._drop(target_name)
        staging.modify(name=target_name)

    def _drop(self, name: str) -> None:
        try:
            self._client.delete_collection(name)
        except Exception:
            pass  # Did not exist; nothing to drop.

    # --- manifest ---------------------------------------------------------

    def write_manifest(self, manifest: IndexManifest) -> None:
        self._settings.manifest_path.write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

    def read_manifest(self) -> IndexManifest | None:
        path = self._settings.manifest_path
        if not path.exists():
            return None
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return IndexManifest(**data)
        except Exception:
            return None
