"""Monitoring and telemetry package: logging, latency metrics, error tracking."""

from backend.app.monitoring.logging_config import (
    configure_logging,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from backend.app.monitoring.metrics import (
    REGISTRY,
    RagTrace,
    estimate_tokens,
    safe_query,
    stage_timer,
)
from backend.app.monitoring.sentry import (
    init_sentry,
    is_sentry_enabled,
    set_rag_context,
    trace_span,
)

__all__ = [
    "REGISTRY",
    "RagTrace",
    "configure_logging",
    "estimate_tokens",
    "get_request_id",
    "init_sentry",
    "is_sentry_enabled",
    "reset_request_id",
    "safe_query",
    "set_rag_context",
    "set_request_id",
    "stage_timer",
    "trace_span",
]
