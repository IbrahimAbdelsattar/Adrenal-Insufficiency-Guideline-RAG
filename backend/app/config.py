"""Central configuration.

Constitution Operating Constraints forbid magic numbers scattered through modules:
every tunable lives here and is overridable from .env (research.md D10).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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

    # --- Model provider: OmniRoute gateway ---
    # OMNIROUTE_* is the correct name. OPENROUTER_* is accepted as a legacy
    # alias because early config used it by mistake — the provider is OmniRoute
    # (an OpenAI-compatible gateway), not OpenRouter.
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OMNIROUTE_API_KEY", "OPENROUTER_API_KEY"),
    )
    openrouter_base_url: str = Field(
        default="https://omniroute.dawrly.space/v1",
        validation_alias=AliasChoices("OMNIROUTE_BASE_URL", "OPENROUTER_BASE_URL"),
    )

    # --- Embeddings ---
    # Default is the model verified working on the OmniRoute gateway and the one
    # the shipped index is built with. The former default
    # (openai/text-embedding-3-small) is NOT routable there — it returns
    # "No credentials for embedding provider" — so falling back to it produced a
    # model-mismatch 503 whenever EMBEDDING_MODEL failed to propagate.
    embedding_model: str = Field(
        default="gemini/gemini-embedding-001", alias="EMBEDDING_MODEL"
    )
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")

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
    retriever_type: str = Field(default="hybrid_rerank", alias="RETRIEVER_TYPE")
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RERANKER_MODEL"
    )
    hybrid_candidate_k: int = Field(default=20, alias="HYBRID_CANDIDATE_K")
    # Tuned against the cross-encoder reranker scale, where unrelated queries
    # score ~0.000 and in-scope queries start around 0.007. This value is tied
    # to RETRIEVER_TYPE: raw dense scores sit in a 0.4-0.8 band, so switching
    # retrievers requires re-tuning this (see tests/unit/test_scope.py).
    scope_threshold: float = Field(default=0.005, alias="SCOPE_THRESHOLD")

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
    # Browser origins permitted to call the API directly. The deployed frontend
    # calls the backend domain cross-origin, so without a matching entry the
    # browser blocks every request before it is sent — the backend looks healthy
    # from curl while the UI reports "cannot reach the backend".
    #
    # Comma-separated. ALLOWED_ORIGINS (plural) is canonical; ALLOWED_ORIGIN is
    # accepted as an alias.
    allowed_origins: str = Field(
        default="",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "ALLOWED_ORIGIN"),
    )

    # Any subdomain of the deployment domain is trusted, so the split
    # frontend/backend hosts work even when the env var is missing. Override by
    # setting CORS_ORIGIN_REGEX (empty string disables the regex entirely).
    cors_origin_regex: str = Field(
        default=r"https://([a-z0-9-]+\.)*dawrly\.space",
        alias="CORS_ORIGIN_REGEX",
    )

    @property
    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        for candidate in self.allowed_origins.split(","):
            cleaned = candidate.strip().rstrip("/")
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
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
