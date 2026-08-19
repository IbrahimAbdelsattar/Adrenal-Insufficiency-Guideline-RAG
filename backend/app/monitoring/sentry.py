"""Sentry error tracking, telemetry, and PHI data sanitization.

Provides centralized error reporting and tracing with strict data scrubbing
for clinical decision support safety and HIPAA/GDPR alignment.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Any, Generator

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.httpx import HttpxIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from backend.app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# State tracking for Sentry initialization
_SENTRY_ENABLED = False

# Sensitive headers to strip from events
SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "omniroute_api_key",
    "openrouter_api_key",
    "anthropic_api_key",
}

# Regex patterns for PHI/PII sanitization
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
MRN_REGEX = re.compile(r"\b(?:MRN|mrn)[-:\s]*([A-Za-z0-9]+)\b", re.IGNORECASE)
SECRET_QUERY_REGEX = re.compile(r"([?&](?:api_key|token|key|secret)=)[^&]+", re.IGNORECASE)
BEARER_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]+", re.IGNORECASE)


def scrub_text(text: str) -> str:
    """Scrub sensitive patterns (emails, phones, SSNs, MRNs, tokens) from text."""
    if not isinstance(text, str):
        return text

    text = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    text = SSN_REGEX.sub("[REDACTED_SSN]", text)
    text = MRN_REGEX.sub("[REDACTED_MRN]", text)
    text = PHONE_REGEX.sub("[REDACTED_PHONE]", text)
    text = BEARER_REGEX.sub("Bearer [REDACTED_TOKEN]", text)
    text = SECRET_QUERY_REGEX.sub(r"\1[REDACTED_KEY]", text)
    return text


def sanitize_dict_recursive(data: Any) -> Any:
    """Recursively sanitize strings and keys in dictionaries and lists."""
    if isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_HEADERS or any(s in key_lower for s in ("secret", "token", "password", "key")):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = sanitize_dict_recursive(val)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_dict_recursive(item) for item in data]
    elif isinstance(data, str):
        return scrub_text(data)
    return data


def sanitize_sentry_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Before-send hook that strips authentication headers, keys, and scrubs PHI."""
    # 1. Sanitize Request data if present
    if "request" in event and isinstance(event["request"], dict):
        req = event["request"]

        # Strip sensitive headers
        if "headers" in req and isinstance(req["headers"], dict):
            req["headers"] = {
                k: v
                for k, v in req["headers"].items()
                if str(k).lower() not in SENSITIVE_HEADERS
            }

        # Sanitize URL / Query string
        if "url" in req and isinstance(req["url"], str):
            req["url"] = scrub_text(req["url"])
        if "query_string" in req and isinstance(req["query_string"], str):
            req["query_string"] = scrub_text(req["query_string"])

        # Sanitize request body / data
        if "data" in req:
            req["data"] = sanitize_dict_recursive(req["data"])

    # 2. Sanitize top-level message
    if "message" in event and isinstance(event["message"], str):
        event["message"] = scrub_text(event["message"])

    # 3. Sanitize Exception values and stacktrace frames
    if "exception" in event and isinstance(event["exception"], dict):
        for exc in event["exception"].get("values", []):
            if isinstance(exc, dict):
                if "value" in exc and isinstance(exc["value"], str):
                    exc["value"] = scrub_text(exc["value"])
                if "type" in exc and isinstance(exc["type"], str):
                    exc["type"] = scrub_text(exc["type"])

    # 4. Sanitize Breadcrumbs
    if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
        for crumb in event["breadcrumbs"].get("values", []):
            sanitize_sentry_breadcrumb(crumb, hint)

    # 5. Sanitize Extra / Context metadata
    if "extra" in event and isinstance(event["extra"], dict):
        event["extra"] = sanitize_dict_recursive(event["extra"])

    return event


def sanitize_sentry_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """Sanitize individual breadcrumb messages and data dictionaries."""
    if "message" in crumb and isinstance(crumb["message"], str):
        crumb["message"] = scrub_text(crumb["message"])
    if "data" in crumb:
        crumb["data"] = sanitize_dict_recursive(crumb["data"])
    return crumb


def init_sentry(settings: Settings | None = None) -> bool:
    """Initialize Sentry error tracking and performance monitoring.

    Returns:
        bool: True if Sentry was enabled and initialized, False otherwise.
    """
    global _SENTRY_ENABLED

    if settings is None:
        settings = get_settings()

    dsn = settings.sentry_dsn.strip()
    if not dsn:
        _SENTRY_ENABLED = False
        logger.debug("Sentry DSN not configured; error tracking disabled.")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profile_session_sample_rate=1.0,
            profile_lifecycle="trace",
            send_default_pii=True,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                HttpxIntegration(),
                LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            ],
            before_send=sanitize_sentry_event,
            before_breadcrumb=sanitize_sentry_breadcrumb,
        )
        _SENTRY_ENABLED = True
        logger.info(
            "Sentry monitoring initialized successfully (env=%s, traces_sample_rate=%s).",
            settings.sentry_environment,
            settings.sentry_traces_sample_rate,
        )
        return True
    except Exception as exc:
        _SENTRY_ENABLED = False
        logger.warning("Failed to initialize Sentry: %s", exc)
        return False


def is_sentry_enabled() -> bool:
    """Check if Sentry tracking is currently active."""
    return _SENTRY_ENABLED


@contextmanager
def trace_span(op: str, description: str) -> Generator[Any, None, None]:
    """Context manager for tracing custom operations in RAG & LLM pipelines.

    Safe to use even if Sentry is not configured (graceful no-op).
    """
    if _SENTRY_ENABLED:
        try:
            with sentry_sdk.start_span(op=op, name=description) as span:
                yield span
                return
        except Exception:
            # If tracing fails for any reason, don't break business logic
            pass
    yield None
