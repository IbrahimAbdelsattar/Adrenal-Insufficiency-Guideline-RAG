"""Embeddings package exposing protocols and providers."""

from backend.app.embeddings.base import Embedder
from backend.app.embeddings.fallback import FallbackEmbedder
from backend.app.embeddings.local import LocalEmbedder
from backend.app.embeddings.openrouter import OpenRouterEmbedder

__all__ = [
    "Embedder",
    "FallbackEmbedder",
    "LocalEmbedder",
    "OpenRouterEmbedder",
]
