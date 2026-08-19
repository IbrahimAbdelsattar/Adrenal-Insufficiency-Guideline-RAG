"""Unit and API integration tests for Sentry diagnostic endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_sentry_test_endpoint_without_error_param():
    """GET /api/health/sentry-test returns diagnostic status."""
    with patch("backend.app.monitoring.sentry.sentry_sdk.capture_message") as mock_msg:
        response = client.get("/api/health/sentry-test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "sentry_enabled" in data
        assert data["message"] == "Sentry test diagnostic triggered successfully."


def test_sentry_test_endpoint_triggers_test_exception():
    """GET /api/health/sentry-test?trigger_error=true captures an exception and returns error diagnostic."""
    with patch("backend.app.monitoring.sentry.sentry_sdk.capture_exception") as mock_exc:
        response = client.get("/api/health/sentry-test?trigger_error=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "test_exception_captured"
        assert data["error_type"] == "SentryTestException"
        assert "Manual test exception triggered for Sentry verification" in data["detail"]


def test_sentry_debug_zero_division_raises():
    """GET /sentry-debug triggers ZeroDivisionError for Sentry onboarding verification."""
    with pytest.raises(ZeroDivisionError):
        client.get("/sentry-debug")
