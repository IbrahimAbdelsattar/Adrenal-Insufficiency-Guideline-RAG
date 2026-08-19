"""BM25 Lexical Retriever using BM25Okapi (Day 2 hybrid search).

Implements the Retriever protocol (base.py) with an in-memory BM25 index
over stored guideline chunks. Complements DenseRetriever for exact-match
drug names, dosages, and clinical abbreviations.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter

from backend.app.config import Settings, get_settings
from backend.app.models import Chunk, RetrievalResult
from backend.app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"[\w\d]+(?:[\.\-][\w\d]+)*", re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "what",
    "which",
    "when",
    "where",
    "who",
    "how",
    "should",
    "do",
    "does",
    "ما",
    "هي",
    "هو",
    "في",
    "من",
    "على",
    "إلى",
    "عن",
    "مع",
    "هل",
    "عند",
}

_ARABIC_CLINICAL_MAP = {
    "هيدروكورتيزون": ["hydrocortisone", "100", "mg"],
    "كورتيزول": ["cortisol"],
    "فلودروكورتيزون": ["fludrocortisone"],
    "كظرية": ["adrenal", "crisis"],
    "كظري": ["adrenal"],
    "الكظرية": ["adrenal"],
    "الكظري": ["adrenal"],
    "أزمة": ["crisis", "emergency"],
    "أزمات": ["crisis"],
    "قصور": ["insufficiency"],
    "أديسون": ["addison"],
    "مرض": ["disease"],
    "حمى": ["fever"],
    "قيء": ["vomiting"],
    "استفراغ": ["vomiting"],
    "وريد": ["intravenous", "iv"],
    "وريدي": ["intravenous", "iv"],
    "عضل": ["intramuscular", "im"],
    "عضلي": ["intramuscular", "im"],
    "حقن": ["injection"],
    "طوارئ": ["emergency"],
    "طارئة": ["emergency"],
    "جرعة": ["dose"],
    "جرعات": ["doses"],
    "بالغين": ["adults"],
    "أطفال": ["children", "paediatric", "bsped"],
    "حمل": ["pregnancy"],
    "ولادة": ["birth", "postpartum"],
}


def tokenize_clinical_text(text: str) -> list[str]:
    """Tokenize clinical text preserving dosages, recommendation IDs, and bilingual medical terms."""
    clean = text.lower()
    raw_tokens = _TOKEN_PATTERN.findall(clean)
    tokens: list[str] = []

    for t in raw_tokens:
        if t in _STOPWORDS:
            continue
        if t in _ARABIC_CLINICAL_MAP:
            tokens.extend(_ARABIC_CLINICAL_MAP[t])
        elif len(t) > 1:
            tokens.append(t)

    return tokens


class BM25Retriever:
    """BM25Okapi sparse lexical retriever over ChromaDB or direct chunks."""

    def __init__(
        self,
        store: VectorStore | None = None,
        chunks: list[Chunk] | None = None,
        settings: Settings | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or (VectorStore(self._settings) if chunks is None else None)
        self.k1 = k1
        self.b = b
        self._chunks: list[Chunk] = chunks if chunks is not None else []
        self._corpus_tokens: list[list[str]] = []
        self._doc_lens: list[int] = []
        self._avgdl: float = 0.0
        self._doc_freqs: Counter[str] = Counter()
        self._idf: dict[str, float] = {}
        self._indexed = False
        self._has_explicit_chunks = chunks is not None

    def _build_index(self) -> None:
        """Build in-memory BM25 inverted index from store or direct chunks."""
        # Index building is a cold-start cost: log it so a slow first request
        # is attributable rather than mysterious.
        started = time.perf_counter()

        if not self._has_explicit_chunks and self._store is not None:
            self._chunks = self._store.all_chunks()

        if not self._chunks:
            self._indexed = True
            logger.warning(
                "BM25 index built over an empty corpus - lexical retrieval will return nothing.",
                extra={"event": "retrieval.bm25.index", "chunks": 0},
            )
            return

        self._corpus_tokens = [
            tokenize_clinical_text(
                f"{c.text} {c.section_title} {c.subsection_title} {c.recommendation_ids}"
            )
            for c in self._chunks
        ]
        self._doc_lens = [len(tokens) for tokens in self._corpus_tokens]
        self._avgdl = sum(self._doc_lens) / max(len(self._doc_lens), 1)

        # Document frequencies
        df: Counter[str] = Counter()
        for doc_tokens in self._corpus_tokens:
            df.update(set(doc_tokens))
        self._doc_freqs = df

        # Robertson-Spärck Jones IDF with smoothing
        n_docs = len(self._chunks)
        idf: dict[str, float] = {}
        for term, freq in df.items():
            idf[term] = math.log(1.0 + (n_docs - freq + 0.5) / (freq + 0.5))
        self._idf = idf
        self._indexed = True

        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "BM25 index built: %d chunks, %d terms, avgdl=%.1f in %.0f ms",
            len(self._chunks),
            len(idf),
            self._avgdl,
            elapsed_ms,
            extra={
                "event": "retrieval.bm25.index",
                "chunks": len(self._chunks),
                "vocabulary": len(idf),
                "avg_doc_len": round(self._avgdl, 2),
                "duration_ms": round(elapsed_ms, 2),
            },
        )

    def search(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        """Search chunks with BM25Okapi scoring."""
        if not self._indexed:
            self._build_index()

        if not self._chunks:
            return []

        k = top_k or self._settings.top_k
        floor = self._settings.relevance_floor
        query_tokens = tokenize_clinical_text(query)

        if not query_tokens:
            logger.debug(
                "BM25 query tokenized to nothing (all stopwords) - no lexical signal.",
                extra={"event": "retrieval.bm25.empty_query"},
            )
            return []

        matched_terms = sum(1 for term in set(query_tokens) if term in self._idf)

        scores: list[float] = [0.0] * len(self._chunks)
        for term in query_tokens:
            if term not in self._idf:
                continue
            term_idf = self._idf[term]
            for doc_idx, doc_tokens in enumerate(self._corpus_tokens):
                tf = doc_tokens.count(term)
                if tf == 0:
                    continue
                doc_len = self._doc_lens[doc_idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self._avgdl))
                scores[doc_idx] += term_idf * (numerator / denominator)

        # Normalize BM25 scores to [0, 1] using max score scaling
        max_score = max(scores) if scores else 0.0
        if max_score > 0:
            norm_scores = [s / max_score for s in scores]
        else:
            norm_scores = [0.0] * len(scores)

        # Rank documents
        ranked_indices = sorted(
            range(len(self._chunks)), key=lambda i: norm_scores[i], reverse=True
        )[:k]

        results = [
            RetrievalResult(
                chunk=self._chunks[i],
                score=norm_scores[i],
                rank=rank,
                below_floor=norm_scores[i] < floor,
                bm25_score=norm_scores[i],
                retriever_mode="bm25",
            )
            for rank, i in enumerate(ranked_indices, start=1)
        ]

        logger.debug(
            "retrieval.bm25 results=%d query_terms=%d matched_terms=%d max_raw=%.3f",
            len(results),
            len(query_tokens),
            matched_terms,
            max_score,
            extra={
                "event": "retrieval.bm25",
                "results": len(results),
                "query_terms": len(query_tokens),
                # Zero matched terms means the query shares no vocabulary with
                # the corpus -- a strong out-of-scope signal on its own.
                "matched_terms": matched_terms,
                "max_raw_score": round(max_score, 4),
                "chunk_ids": [r.chunk.chunk_id for r in results],
            },
        )
        return results
