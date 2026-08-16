"""Central configuration.

Constitution Operating Constraints forbid magic numbers scattered through modules:
every tunable lives here and is overridable from .env (research.md D10).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = backend/app/config.py -> backend/app -> backend -> root
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Field names match .env.example."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Model provider ---
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )

    # --- Embeddings ---
    embedding_model: str = Field(
        default="openai/text-embedding-3-small", alias="EMBEDDING_MODEL"
    )
    embedding_batch_size: int = Field(default=100, alias="EMBEDDING_BATCH_SIZE")

    # --- Generation (Day 2; unused in feature 001) ---
    generation_model: str = Field(
        default="anthropic/claude-sonnet-4.5", alias="GENERATION_MODEL"
    )

    # --- Chunking ---
    chunk_target_tokens: int = Field(default=600, alias="CHUNK_TARGET_TOKENS")
    chunk_min_tokens: int = Field(default=400, alias="CHUNK_MIN_TOKENS")
    chunk_max_tokens: int = Field(default=800, alias="CHUNK_MAX_TOKENS")

    # --- Retrieval ---
    top_k: int = Field(default=5, alias="TOP_K")
    relevance_floor: float = Field(default=0.30, alias="RELEVANCE_FLOOR")

    # --- Paths (relative values resolve against the repo root) ---
    corpus_dir: Path = Field(default=Path("data/corpus"), alias="CORPUS_DIR")
    sources_file: Path = Field(default=Path("data/sources.yaml"), alias="SOURCES_FILE")
    index_dir: Path = Field(default=Path("data/index"), alias="INDEX_DIR")
    chroma_collection: str = Field(default="guidelines", alias="CHROMA_COLLECTION")

    # --- Cleaning ---
    boilerplate_page_ratio: float = Field(
        default=0.6, alias="BOILERPLATE_PAGE_RATIO"
    )

    # --- Serving ---
    # Extra browser origin allowed to call the API directly. In the deployed
    # setup the frontend proxies /api server-side, so this only matters for
    # hitting the backend domain straight from a browser.
    allowed_origin: str = Field(default="", alias="ALLOWED_ORIGIN")

    @property
    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        if self.allowed_origin and self.allowed_origin not in origins:
            origins.append(self.allowed_origin)
        return origins

    # ------------------------------------------------------------------
    # Absolute path helpers. Callers should use these, never the raw fields,
    # so behaviour does not depend on the process working directory.
    # ------------------------------------------------------------------

    def _abs(self, p: Path) -> Path:
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def corpus_path(self) -> Path:
        return self._abs(self.corpus_dir)

    @property
    def sources_path(self) -> Path:
        return self._abs(self.sources_file)

    @property
    def index_path(self) -> Path:
        return self._abs(self.index_dir)

    @property
    def manifest_path(self) -> Path:
        return self.index_path / "manifest.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
