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

    # --- Model provider: OmniRoute / OpenRouter gateway ---
    openrouter_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "OMNIROUTE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"
        ),
    )
    openrouter_base_url: str = Field(
        default="https://omniroute.dawrly.space/v1",
        validation_alias=AliasChoices("OMNIROUTE_BASE_URL", "OPENROUTER_BASE_URL"),
    )

    # --- Embeddings ---
    embedding_model: str = Field(default="gemini/gemini-embedding-001", alias="EMBEDDING_MODEL")
    embedding_batch_size: int = Field(default=32, alias="EMBEDDING_BATCH_SIZE")

    # --- Generation (Day 3) ---
    generation_model: str = Field(default="eva-ai", alias="GENERATION_MODEL")

    # Reasoning models spend part of this budget on a <think> block before
    # writing anything. At 1024 the whole budget went to reasoning and the
    # completion was truncated before an answer existed.
    generation_max_tokens: int = Field(default=4096, alias="GENERATION_MAX_TOKENS")
    generation_temperature: float = Field(default=0.1, alias="GENERATION_TEMPERATURE")

    # --- Chunking ---
    chunk_target_tokens: int = Field(default=600, alias="CHUNK_TARGET_TOKENS")
    chunk_min_tokens: int = Field(default=400, alias="CHUNK_MIN_TOKENS")
    chunk_max_tokens: int = Field(default=800, alias="CHUNK_MAX_TOKENS")

    # --- Retrieval ---
    # k=3 scored highest precision in the Day 2 eval and cuts prompt tokens.
    top_k: int = Field(default=3, alias="TOP_K")
    # Compared against RetrievalResult.absolute_relevance (dense cosine, or the
    # cross-encoder score when reranking) — never against the RRF-normalised
    # `score`, whose top hit is 1.0 for every query. Measured on this corpus:
    # in-scope results land at 0.667-0.810, unrelated ones at 0.000-0.526.
    relevance_floor: float = Field(default=0.62, alias="RELEVANCE_FLOOR")
    # Default is plain hybrid: the Day 2 eval showed the cross-encoder reranker
    # lowers hit rate (94.4% vs 100%) while adding per-query latency.
    retriever_type: str = Field(default="hybrid", alias="RETRIEVER_TYPE")
    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RERANKER_MODEL"
    )
    hybrid_candidate_k: int = Field(default=20, alias="HYBRID_CANDIDATE_K")
    # Below this, a query is rejected as out_of_scope. Sits in the measured gap
    # between unrelated queries (top relevance <= 0.526) and in-scope ones
    # (top relevance >= 0.700). Same scale as relevance_floor above.
    scope_threshold: float = Field(default=0.58, alias="SCOPE_THRESHOLD")

    # --- Graph expansion (lightweight Graph RAG) ---
    graph_expansion: bool = Field(default=True, alias="GRAPH_EXPANSION")
    graph_max_expand: int = Field(default=1, alias="GRAPH_MAX_EXPAND")

    # --- Generation response cache ---
    response_cache_size: int = Field(default=128, alias="RESPONSE_CACHE_SIZE")

    # --- Paths (relative values resolve against the repo root) ---
    corpus_dir: Path = Field(default=Path("data/corpus"), alias="CORPUS_DIR")
    sources_file: Path = Field(default=Path("data/sources.yaml"), alias="SOURCES_FILE")
    index_dir: Path = Field(default=Path("data/index"), alias="INDEX_DIR")
    chroma_collection: str = Field(default="guidelines", alias="CHROMA_COLLECTION")

    # --- Cleaning ---
    boilerplate_page_ratio: float = Field(default=0.6, alias="BOILERPLATE_PAGE_RATIO")

    # --- Logging & observability ---
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # "text" for humans, "json" for log aggregators in deployment.
    log_format: str = Field(default="text", alias="LOG_FORMAT")
    # Clinical queries can carry PHI. Logged text is always scrubbed and
    # truncated; set LOG_QUERY_TEXT=false to drop it entirely.
    log_query_text: bool = Field(default=True, alias="LOG_QUERY_TEXT")
    log_query_max_chars: int = Field(default=200, alias="LOG_QUERY_MAX_CHARS")
    # Requests slower than this are logged at WARNING so they stand out.
    slow_request_ms: int = Field(default=5000, alias="SLOW_REQUEST_MS")
    # Log the assembled evidence text and the LLM prompt/answer previews.
    # Verbose and PHI-adjacent: off unless a pipeline is being debugged.
    log_prompt_preview: bool = Field(default=False, alias="LOG_PROMPT_PREVIEW")
    log_preview_chars: int = Field(default=400, alias="LOG_PREVIEW_CHARS")

    # --- Sentry Error Tracking & Monitoring ---
    sentry_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("SENTRY_DSN", "SENTRY_BACKEND_DSN"),
    )
    sentry_environment: str = Field(
        default="development",
        alias="SENTRY_ENVIRONMENT",
    )
    sentry_traces_sample_rate: float = Field(
        default=1.0,
        alias="SENTRY_TRACES_SAMPLE_RATE",
    )

    # --- Serving ---
    allowed_origins: str = Field(
        default="",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "ALLOWED_ORIGIN"),
    )

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
