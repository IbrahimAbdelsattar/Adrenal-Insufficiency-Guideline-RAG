"""Unit tests for RAG/LLM logging, latency tracing, and the metrics registry."""

from __future__ import annotations

import json
import logging

import pytest

from backend.app.config import Settings
from backend.app.monitoring.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    TextFormatter,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from backend.app.monitoring.metrics import (
    REGISTRY,
    MetricsRegistry,
    RagTrace,
    estimate_tokens,
    safe_query,
    stage_timer,
)

# --------------------------------------------------------------- registry


def test_registry_summarizes_durations():
    registry = MetricsRegistry()
    for value in (10.0, 20.0, 30.0, 40.0):
        registry.observe("rag.retrieval", value)

    stats = registry.snapshot()["stages"]["rag.retrieval"]
    assert stats["count"] == 4
    assert stats["avg_ms"] == 25.0
    assert stats["max_ms"] == 40.0
    assert stats["p50_ms"] <= stats["p95_ms"] <= stats["max_ms"]


def test_registry_window_is_bounded():
    """A long-lived worker must not grow the registry without limit."""
    registry = MetricsRegistry(window=5)
    for value in range(100):
        registry.observe("stage", float(value))

    assert registry.snapshot()["stages"]["stage"]["count"] == 5


def test_registry_counters_and_reset():
    registry = MetricsRegistry()
    registry.increment("llm.calls")
    registry.increment("llm.calls")
    registry.increment("llm.total_tokens", 250)

    counters = registry.snapshot()["counters"]
    assert counters["llm.calls"] == 2
    assert counters["llm.total_tokens"] == 250

    registry.reset()
    assert registry.snapshot()["counters"] == {}


def test_snapshot_omits_stages_with_no_observations():
    registry = MetricsRegistry()
    registry.increment("only.a.counter")
    assert registry.snapshot()["stages"] == {}


# ------------------------------------------------------------ query safety


def test_safe_query_scrubs_and_truncates():
    # Settings fields are alias-keyed, so construct with the env-var names.
    settings = Settings(LOG_QUERY_MAX_CHARS=40)
    scrubbed = safe_query("contact bob@example.com about MRN: A12345 " + "x" * 100, settings)

    assert "bob@example.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert scrubbed.endswith("...")


def test_safe_query_can_be_disabled_entirely():
    """LOG_QUERY_TEXT=false must drop the text, keeping only its length."""
    settings = Settings(LOG_QUERY_TEXT=False)
    assert safe_query("possible PHI in here", settings) == "<redacted len=20>"


def test_estimate_tokens_is_proportional_to_length():
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 400) == 100


# --------------------------------------------------------------- stage_timer


def test_stage_timer_logs_duration_and_records_it(caplog):
    log = logging.getLogger("test.stage_timer")
    with caplog.at_level(logging.DEBUG, logger="test.stage_timer"):
        with stage_timer("unit.stage", log, hits=3) as span:
            span["extra_field"] = "value"

    record = next(r for r in caplog.records if getattr(r, "stage", None) == "unit.stage")
    assert record.ok is True
    assert record.duration_ms >= 0
    assert record.hits == 3
    assert record.extra_field == "value"
    # The duration is also queryable via GET /api/metrics.
    assert REGISTRY.snapshot()["stages"]["unit.stage"]["count"] >= 1


def test_stage_timer_reraises_and_marks_failure(caplog):
    log = logging.getLogger("test.stage_timer.error")
    with caplog.at_level(logging.DEBUG, logger="test.stage_timer.error"):
        with pytest.raises(ValueError):
            with stage_timer("unit.failing", log):
                raise ValueError("boom")

    record = next(r for r in caplog.records if getattr(r, "stage", None) == "unit.failing")
    assert record.ok is False
    assert record.levelno == logging.WARNING


# ------------------------------------------------------------------ RagTrace


def _trace(**kwargs) -> RagTrace:
    log = logging.getLogger("test.ragtrace")
    return RagTrace("generate", log=log, settings=Settings(), **kwargs)


def test_ragtrace_times_each_stage_and_emits_a_summary(caplog):
    with caplog.at_level(logging.DEBUG, logger="test.ragtrace"):
        trace = _trace(query="adrenal crisis dose", top_k=3)
        with trace.stage("retrieval") as span:
            span["results"] = 3
        with trace.stage("llm") as span:
            span["model"] = "eva-ai"
        trace.set(cache_hit=False)
        total_ms = trace.emit(status="ok")

    assert total_ms >= 0
    assert set(trace.stages) == {"retrieval", "llm"}

    summary = next(r for r in caplog.records if getattr(r, "event", None) == "rag.trace")
    assert summary.status == "ok"
    assert summary.endpoint == "generate"
    assert summary.cache_hit is False
    assert summary.query == "adrenal crisis dose"
    assert set(summary.stages_ms) == {"retrieval", "llm"}
    # Total must account for the stages plus whatever was not instrumented.
    assert summary.total_ms >= 0
    assert summary.overhead_ms >= 0


def test_ragtrace_stage_failure_does_not_swallow_the_exception(caplog):
    trace = _trace(query="q")
    with caplog.at_level(logging.DEBUG, logger="test.ragtrace"):
        with pytest.raises(RuntimeError):
            with trace.stage("llm"):
                raise RuntimeError("gateway down")

    # The stage is still timed, so a failed call's cost stays visible.
    assert "llm" in trace.stages
    record = next(r for r in caplog.records if getattr(r, "stage", None) == "llm")
    assert record.ok is False


def test_ragtrace_record_retrieval_captures_score_spread(caplog):
    from backend.app.models import Chunk, RetrievalResult

    def result(rank: int, score: float, below: bool) -> RetrievalResult:
        chunk = Chunk(
            chunk_id=f"c{rank}",
            text="Adrenal insufficiency guidance.",
            doc_id="nice_ng243",
            document_name="NICE NG243",
            source_url="https://nice.org.uk/ng243",
            document_type="guideline",
            publication_year=2024,
            requires_caution=False,
            page_number=rank,
        )
        return RetrievalResult(
            chunk=chunk, score=score, rank=rank, below_floor=below, dense_score=score
        )

    trace = _trace(query="q")
    trace.record_retrieval([result(1, 0.8, False), result(2, 0.4, True)])

    assert trace.fields["results"] == 2
    assert trace.fields["above_floor"] == 1
    assert trace.fields["top_relevance"] == 0.8
    assert trace.fields["chunk_ids"] == ["c1", "c2"]


def test_ragtrace_handles_no_results():
    trace = _trace(query="q")
    trace.record_retrieval([])
    assert trace.fields["results"] == 0
    assert trace.fields["top_score"] == 0.0
    assert trace.fields["retriever_mode"] == "none"


# --------------------------------------------------------------- formatters


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="backend.app.rag",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="latency %d",
        args=(42,),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_extras_as_fields():
    record = _record(request_id="abc123", stage="llm", duration_ms=12.5)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "latency 42"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "abc123"
    assert payload["stage"] == "llm"
    assert payload["duration_ms"] == 12.5


def test_text_formatter_appends_extras():
    record = _record(request_id="abc123", stage="llm", duration_ms=12.5)
    line = TextFormatter().format(record)

    assert "[abc123]" in line
    assert "stage=llm" in line
    assert "duration_ms=12.5" in line


def test_request_id_filter_stamps_the_current_context():
    token = set_request_id("deadbeef")
    try:
        record = _record()
        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "deadbeef"
        assert get_request_id() == "deadbeef"
    finally:
        reset_request_id(token)

    assert get_request_id() == "-"


def test_set_request_id_generates_one_when_absent():
    token = set_request_id(None)
    try:
        assert get_request_id() != "-"
        assert len(get_request_id()) == 12
    finally:
        reset_request_id(token)


# ------------------------------------------------------- endpoint + middleware


def test_metrics_endpoint_reports_config_and_stages():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    # No lifespan: /api/metrics must answer without a warmed index.
    body = TestClient(app).get("/api/metrics").json()

    assert body["status"] == "ok"
    assert "retriever_type" in body["config"]
    assert "generation_model" in body["config"]
    assert isinstance(body["stages"], dict)
    assert isinstance(body["counters"], dict)


def test_middleware_returns_correlation_and_timing_headers():
    from fastapi.testclient import TestClient

    from backend.app.main import app

    response = TestClient(app).get("/api/metrics")

    assert response.headers["X-Request-ID"]
    assert float(response.headers["X-Response-Time-ms"]) >= 0


def test_middleware_honours_an_inbound_request_id():
    """A caller-supplied id lets one trace span frontend and backend."""
    from fastapi.testclient import TestClient

    from backend.app.main import app

    response = TestClient(app).get("/api/metrics", headers={"X-Request-ID": "trace-me-123"})

    assert response.headers["X-Request-ID"] == "trace-me-123"
