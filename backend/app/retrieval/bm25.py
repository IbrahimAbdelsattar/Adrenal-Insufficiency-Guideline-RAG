"""BM25 Lexical Retriever using BM25Okapi (Day 2 hybrid search).

Implements the Retriever protocol (base.py) with in-memory BM25 index
over stored guideline chunks.  Complements DenseRetriever for exact-match
drug names, dosages, and clinical abbreviations that dense embeddings miss.
"""

from __future__ import annotations

import re
from typing import Sequence

from rank_bm25 import BM25L

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.store import VectorStore


def tokenize_clinical_text(text: str) -> list[str]:
    """Tokenize clinical text preserving drug names, numbers, and Arabic/English terms.

    Single-char tokens are dropped to reduce noise from bullet points and stray
    punctuation.  Everything is lowercased so that 'Hydrocortisone' and
    'hydrocortisone' match.
    """
    return [t.lower() for t in re.findall(r"\w+", text) if len(t) > 1]


class BM25Retriever:
    """BM25 lexical search over stored guideline chunks.

    Satisfies the Retriever protocol.  Weak matches are flagged with
    ``below_floor=True`` rather than dropped (Constitution Principle VI).
    """

    def __init__(
        self,
        chunks: Sequence[Chunk] | None = None,
        store: VectorStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        if chunks is not None:
            self._chunks: list[Chunk] = list(chunks)
        else:
            _store = store or VectorStore(self._settings)
            self._chunks = _store.all_chunks()

        tokenized_corpus = [tokenize_clinical_text(c.text) for c in self._chunks]
        self._bm25 = BM25L(tokenized_corpus) if tokenized_corpus else None

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        k = top_k or self._settings.top_k
        floor = self._settings.relevance_floor

        if not self._chunks or self._bm25 is None:
            return []

        tokens = tokenize_clinical_text(query)
        if not tokens:
            return []

        raw_scores = self._bm25.get_scores(tokens)
        max_s = float(max(raw_scores)) if len(raw_scores) > 0 and max(raw_scores) > 0 else 1.0

        # Sort by score descending, take top-k
        ranked = sorted(
            zip(self._chunks, raw_scores), key=lambda x: x[1], reverse=True
        )[:k]

        return [
            RetrievalResult(
                chunk=chunk,
                score=min(1.0, max(0.0, float(score) / max_s)),
                rank=rank,
                below_floor=(float(score) / max_s) < floor,
            )
            for rank, (chunk, score) in enumerate(ranked, start=1)
        ]
