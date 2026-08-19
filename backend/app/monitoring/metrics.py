"""RAG / LLM latency instrumentation.

Two things live here:

``RagTrace``
    Per-request stopwatch. Each pipeline stage (retrieval, scope, graph
    expansion, cache, prompt build, LLM, citations) is timed inside a
    ``with trace.stage(...)`` block that logs its own line, opens a matching
    Sentry span, and records the duration into the registry. ``emit()`` then
    writes one summary line with the whole breakdown, so a single grep for
    ``rag.trace`` gives every request's end-to-end cost profile.

``MetricsRegistry``
    Process-local rolling window of stage durations and counters, surfaced by
    ``GET /api/metrics``. Deliberately in-memory and bounded: this is a live
    latency read-out for one worker, not a metrics backend.

Query text is scrubbed and truncated before it reaches a log line — clinical
queries can carry PHI, and Constitution safety rules apply to logs too.
"""

from __future__ import annotations

import logging
import statistics
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock
from typing import Any

from backend.app.config import Settings, get_settings
from backend.app.monitoring.logging_config import get_request_id
from backend.app.monitoring.sentry import scrub_text, set_rag_context, trace_span

logger = logging.getLogger("backend.app.rag")

# Rolling window per stage. Bounded so a long-lived worker cannot grow this
# without limit; wide enough that p95 over it is meaningful.
_WINDOW = 512


class MetricsRegistry:
    """Thread-safe rolling latency window + counters for one worker process."""

    def __init__(self, window: int = _WINDOW) -> None:
        self._window = window
        self._lock = Lock()
        self._durations: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._counters: dict[str, int] = defaultdict(int)

    def observe(self, stage: str, duration_ms: float) -> None:
        with self._lock:
            self._durations[stage].append(duration_ms)

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def reset(self) -> None:
        with self._lock:
            self._durations.clear()
            self._counters.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            durations = {stage: list(values) for stage, values in self._durations.items()}
            counters = dict(self._counters)

        stages = {
            stage: _summarize(values) for stage, values in sorted(durations.items()) if values
        }
        return {
            "window": self._window,
            "counters": dict(sorted(counters.items())),
            "stages": stages,
        }


def _summarize(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "avg_ms": round(statistics.fmean(ordered), 2),
        "p50_ms": round(_percentile(ordered, 0.50), 2),
        "p95_ms": round(_percentile(ordered, 0.95), 2),
        "max_ms": round(ordered[-1], 2),
    }


def _percentile(ordered: list[float], q: float) -> float:
    """Nearest-rank percentile over an already-sorted list."""
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round(q * len(ordered) + 0.5)) - 1))
    return ordered[index]


REGISTRY = MetricsRegistry()


def safe_query(query: str, settings: Settings | None = None) -> str:
    """Scrub and truncate a user query so it is safe to put in a log line."""
    settings = settings or get_settings()
    if not settings.log_query_text:
        return f"<redacted len={len(query)}>"
    cleaned = scrub_text(query.strip().replace("\n", " "))
    limit = settings.log_query_max_chars
    if len(cleaned) > limit:
        cleaned = cleaned[:limit] + "..."
    return cleaned


def estimate_tokens(text: str) -> int:
    """Rough token count (~4 chars/token) for prompt-size logging.

    Good enough to spot a prompt that has doubled in size; not a billing
    figure. The provider's own usage numbers are logged when it returns them.
    """
    return max(0, len(text) // 4)


def _annotate_span(span: Any, duration_ms: float, ok: bool, fields: dict[str, Any]) -> None:
    """Copy the stage's measurements onto its Sentry span.

    Without this the Sentry trace view shows only op + duration, while the log
    line carries the numbers that explain the duration.
    """
    if span is None:
        return
    try:
        span.set_data("duration_ms", round(duration_ms, 2))
        for key, value in fields.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                span.set_data(key, value)
        if not ok:
            span.set_status("internal_error")
    except Exception:
        # Telemetry must never break the request it is describing.
        pass


@contextmanager
def stage_timer(
    name: str,
    log: logging.Logger | None = None,
    level: int = logging.DEBUG,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    """Time a block, log its duration, and record it in the registry.

    Use inside retrieval/generation internals that are not tied to a request
    trace. Mutate the yielded dict to attach fields to the emitted line.

        with stage_timer("retrieval.dense.embed", logger) as span:
            span["dims"] = len(vector)
    """
    log = log or logger
    extra: dict[str, Any] = dict(fields)
    started = time.perf_counter()
    failed = False
    # The annotate/log work happens inside the span context so the span is
    # still open and can be given the measurements it describes.
    with trace_span(op=name, description=name) as span:
        try:
            yield extra
        except Exception:
            failed = True
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            REGISTRY.observe(name, duration_ms)
            if failed:
                REGISTRY.increment(f"{name}.error")
            _annotate_span(span, duration_ms, not failed, extra)
            log.log(
                logging.WARNING if failed else level,
                "%s %s in %.1f ms",
                name,
                "failed" if failed else "completed",
                duration_ms,
                extra={
                    "stage": name,
                    "duration_ms": round(duration_ms, 2),
                    "ok": not failed,
                    **extra,
                },
            )


class RagTrace:
    """Per-request stopwatch over the RAG pipeline.

    Stages are timed in order; ``emit()`` writes the summary line. The trace is
    also the place request-level facts (scope status, cache hit, evidence
    count, token usage) are accumulated so they land in one greppable record.
    """

    def __init__(
        self,
        endpoint: str,
        query: str = "",
        top_k: int | None = None,
        settings: Settings | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._log = log or logger
        self.endpoint = endpoint
        self.trace_id = get_request_id()
        if self.trace_id == "-":
            self.trace_id = uuid.uuid4().hex[:12]
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}
        self.fields: dict[str, Any] = {
            "endpoint": endpoint,
            "query": safe_query(query, self._settings),
            "query_chars": len(query),
        }
        if top_k is not None:
            self.fields["top_k"] = top_k

    # --- accumulation -----------------------------------------------------

    def set(self, **fields: Any) -> None:
        """Attach request-level facts to the trace summary."""
        self.fields.update(fields)

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    @contextmanager
    def stage(self, name: str, level: int = logging.INFO, **fields: Any) -> Iterator[dict[str, Any]]:
        """Time one pipeline stage. Mutate the yielded dict to add fields."""
        extra: dict[str, Any] = dict(fields)
        started = time.perf_counter()
        failed = False
        with trace_span(op=f"rag.{name}", description=f"{self.endpoint}:{name}") as span:
            try:
                yield extra
            except Exception:
                failed = True
                raise
            finally:
                duration_ms = (time.perf_counter() - started) * 1000
                qualified = f"{self.endpoint}.{name}"
                self.stages[name] = round(duration_ms, 2)
                REGISTRY.observe(qualified, duration_ms)
                if failed:
                    REGISTRY.increment(f"{qualified}.error")
                _annotate_span(span, duration_ms, not failed, extra)
                self._log.log(
                    logging.WARNING if failed else level,
                    "rag.stage %s %s in %.1f ms",
                    name,
                    "failed" if failed else "ok",
                    duration_ms,
                    extra={
                        "event": "rag.stage",
                        "endpoint": self.endpoint,
                        "stage": name,
                        "duration_ms": round(duration_ms, 2),
                        "ok": not failed,
                        **extra,
                    },
                )

    # --- record retrieval + generation detail -----------------------------

    def record_retrieval(self, results: list[Any]) -> None:
        """Summarize a result set: counts, score spread, and the chunks used."""
        self.set(
            results=len(results),
            above_floor=sum(1 for r in results if not r.below_floor),
            top_score=round(results[0].score, 4) if results else 0.0,
            top_relevance=round(results[0].absolute_relevance, 4) if results else 0.0,
            retriever_mode=results[0].retriever_mode if results else "none",
            chunk_ids=[r.chunk.chunk_id for r in results[:10]],
        )
        if results and self._log.isEnabledFor(logging.DEBUG):
            for r in results:
                self._log.debug(
                    "rag.evidence rank=%d score=%.4f relevance=%.4f chunk=%s",
                    r.rank,
                    r.score,
                    r.absolute_relevance,
                    r.chunk.chunk_id,
                    extra={
                        "event": "rag.evidence",
                        "rank": r.rank,
                        "score": round(r.score, 4),
                        "relevance": round(r.absolute_relevance, 4),
                        "dense_score": r.dense_score,
                        "bm25_score": r.bm25_score,
                        "rerank_score": r.rerank_score,
                        "below_floor": r.below_floor,
                        "chunk_id": r.chunk.chunk_id,
                        "document": r.chunk.document_name,
                        "page": r.chunk.page_number,
                        "section": r.chunk.section_title,
                    },
                )

    # --- emission ---------------------------------------------------------

    def emit(self, status: str = "ok", level: int = logging.INFO) -> int:
        """Write the one-line summary. Returns total latency in ms."""
        total_ms = self.elapsed_ms
        REGISTRY.observe(f"{self.endpoint}.total", float(total_ms))
        REGISTRY.increment(f"{self.endpoint}.requests")
        REGISTRY.increment(f"{self.endpoint}.status.{status}")

        accounted = sum(self.stages.values())

        # Make the transaction searchable in Sentry by the things that explain
        # it: which guardrail fired, whether the cache saved the LLM call.
        set_rag_context(
            {
                "trace_id": self.trace_id,
                "status": status,
                "total_ms": total_ms,
                "stages_ms": dict(self.stages),
                **{k: v for k, v in self.fields.items() if not isinstance(v, (dict, list))},
            },
            tags={
                "rag.endpoint": self.endpoint,
                "rag.status": status,
                "rag.scope_status": self.fields.get("scope_status"),
                "rag.cache_hit": self.fields.get("cache_hit"),
                "rag.model": self.fields.get("model"),
            },
        )

        self._log.log(
            level,
            "rag.trace %s status=%s total=%dms stages=%s",
            self.endpoint,
            status,
            total_ms,
            self.stages,
            extra={
                "event": "rag.trace",
                "trace_id": self.trace_id,
                "status": status,
                "total_ms": total_ms,
                "overhead_ms": round(max(0.0, total_ms - accounted), 2),
                "stages_ms": dict(self.stages),
                **self.fields,
            },
        )
        return total_ms
