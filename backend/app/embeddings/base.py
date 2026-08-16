"""Embedder protocol — the provider substitution seam."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Anything that can turn text into vectors.

    Documents and queries are separate methods because some providers
    (e.g. Cohere embed-v3) require distinct input modes for asymmetric retrieval.
    """

    @property
    def model_id(self) -> str:
        """Identifier recorded in the index manifest (FR-019)."""
        ...

    @property
    def dimensions(self) -> int:
        """Vector width. Zero until the first call has revealed it."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunk texts for indexing."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        ...
