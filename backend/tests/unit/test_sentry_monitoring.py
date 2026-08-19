"""Unit tests for Sentry error tracking, initialization, and PHI data scrubbing."""

from __future__ import annotations

from unittest.mock import patch

from backend.app.config import Settings
from backend.app.monitoring.sentry import (
    init_sentry,
    is_sentry_enabled,
    sanitize_sentry_breadcrumb,
    sanitize_sentry_event,
    trace_span,
)


def test_sentry_init_disabled_when_dsn_empty():
    """When SENTRY_DSN is empty, init_sentry returns False and does not crash."""
    settings = Settings(SENTRY_DSN="")
    with patch("sentry_sdk.init") as mock_init:
        result = init_sentry(settings)
        assert result is False
        assert is_sentry_enabled() is False
        mock_init.assert_not_called()


def test_sentry_init_enabled_when_dsn_provided():
    """When SENTRY_DSN is provided, sentry_sdk.init is called with appropriate parameters."""
    test_dsn = "https://public_key@sentry.io/123456"
    # These fields are alias-keyed to their env var names, so an override must
    # use the alias -- by field name it is dropped and the real .env wins.
    settings = Settings(
        SENTRY_DSN=test_dsn,
        SENTRY_ENVIRONMENT="test-env",
        SENTRY_TRACES_SAMPLE_RATE=0.5,
    )
    with patch("sentry_sdk.init") as mock_init:
        result = init_sentry(settings)
        assert result is True
        assert is_sentry_enabled() is True
        mock_init.assert_called_once()
        kwargs = mock_init.call_args.kwargs
        assert kwargs["dsn"] == test_dsn
        assert kwargs["environment"] == "test-env"
        assert kwargs["traces_sample_rate"] == 0.5
        assert kwargs["send_default_pii"] is True
        assert kwargs["before_send"] == sanitize_sentry_event


def test_sanitize_sentry_event_strips_sensitive_headers():
    """Authorization headers, cookies, and API keys are removed from event."""
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer super-secret-token",
                "Cookie": "session_id=abcdef123",
                "X-Api-Key": "sk-12345",
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            "url": "https://api.example.com/search?api_key=secret123",
        },
        "message": "Error occurred while fetching data",
    }

    sanitized = sanitize_sentry_event(event, {})
    headers = sanitized["request"]["headers"]

    assert "Authorization" not in headers
    assert "Cookie" not in headers
    assert "X-Api-Key" not in headers
    assert headers["User-Agent"] == "Mozilla/5.0"
    assert headers["Accept"] == "application/json"
    assert "secret123" not in sanitized["request"]["url"]


def test_sanitize_sentry_event_scrubs_phi_and_pii():
    """Emails, phone numbers, SSNs, and MRN patterns are redacted in message and exception."""
    event = {
        "message": "Patient john.doe@hospital.org with phone +1-555-123-4567 and SSN 123-45-6789 reported fever.",
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "Failed processing MRN-987654321 for patient mary.smith@clinic.com",
                }
            ]
        },
    }

    sanitized = sanitize_sentry_event(event, {})

    assert "john.doe@hospital.org" not in sanitized["message"]
    assert "[REDACTED_EMAIL]" in sanitized["message"]
    assert "[REDACTED_PHONE]" in sanitized["message"]
    assert "[REDACTED_SSN]" in sanitized["message"]

    exc_val = sanitized["exception"]["values"][0]["value"]
    assert "mary.smith@clinic.com" not in exc_val
    assert "[REDACTED_EMAIL]" in exc_val
    assert "[REDACTED_MRN]" in exc_val or "[REDACTED_PHI]" in exc_val


def test_sanitize_sentry_breadcrumb():
    """Breadcrumbs with sensitive patterns or auth keywords are sanitized."""
    crumb = {
        "category": "http",
        "message": "Calling https://omniroute.dawrly.space with Bearer eyJhbGciOi...",
        "data": {"email": "doctor@hospital.org"},
    }
    sanitized = sanitize_sentry_breadcrumb(crumb, {})
    assert "[REDACTED_EMAIL]" in sanitized["data"]["email"]
    assert "Bearer eyJhbGciOi..." not in sanitized["message"]


def test_trace_span_context_manager():
    """trace_span operates cleanly as a context manager regardless of Sentry status."""
    with trace_span(op="rag.test", description="Testing span execution"):
        pass
