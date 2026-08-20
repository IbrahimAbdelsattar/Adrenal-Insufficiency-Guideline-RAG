"""LangSmith tracing for the RAG pipeline.

There is no LangChain here -- just direct httpx calls to the retriever and
the OmniRoute gateway -- so tracing is wired in with LangSmith's standalone
``@traceable`` decorator rather than a LangChain callback handler. Decorated
functions in ``generation/service.py`` and ``generation/client.py`` produce a
nested trace per request: retrieval -> graph expansion -> LLM call, all
rolled up under one top-level pipeline run.

Query text and model output are scrubbed with the same PHI patterns used for
logs and Sentry (Constitution safety rules apply to traces too) before they
ever leave the process. Everything degrades to a no-op if LANGSMITH_API_KEY
is not set, so tracing is opt-in and never blocks generation.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.monitoring.sentry import scrub_text

logger = logging.getLogger(__name__)

_LANGSMITH_ENABLED = False

try:
    from langsmith import traceable as _traceable
except ImportError:  # pragma: no cover - only hit if the package is missing
    def _traceable(*_args: Any, **_kwargs: Any):  # type: ignore[misc]
        def _decorator(func):
            return func

        return _decorator

    logger.warning("langsmith package not installed; RAG tracing decorators are no-ops.")

traceable = _traceable


def init_langsmith(settings: Settings | None = None) -> bool:
    """Configure LangSmith tracing from settings.

    Returns:
        bool: True if tracing was enabled and env vars were set, False otherwise.
    """
    global _LANGSMITH_ENABLED

    settings = settings or get_settings()
    api_key = settings.langsmith_api_key.strip()
    if not api_key or not settings.langsmith_tracing:
        _LANGSMITH_ENABLED = False
        logger.debug("LangSmith API key not set or tracing disabled; RAG tracing disabled.")
        return False

    # The langsmith SDK reads its config from the environment, not from an
    # explicit init() call -- so setting these makes @traceable start emitting.
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint

    _LANGSMITH_ENABLED = True
    logger.info("LangSmith tracing initialized (project=%s).", settings.langsmith_project)
    return True


def is_langsmith_enabled() -> bool:
    """Check if LangSmith tracing is currently active."""
    return _LANGSMITH_ENABLED


def scrub_trace_value(value: Any) -> Any:
    """Recursively scrub PHI-adjacent text before it is sent to LangSmith."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {k: scrub_trace_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_trace_value(v) for v in value]
    return value
