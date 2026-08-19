# Full-Stack Error & Bug Tracking Design with Sentry

**Date:** 2026-08-19  
**Status:** Approved  
**Target:** Eva AI Clinical Decision Support (FastAPI backend + Next.js frontend)

---

## 1. Executive Summary & Goals

This specification outlines the end-to-end integration of **Sentry** for full-stack error tracking, crash reporting, performance tracing, and pipeline diagnostics across the Eva AI Clinical Decision Support platform.

### Key Goals:
1. **Uncaught Error & Exception Tracking**: Automatically capture unhandled backend exceptions, 5xx server responses, client-side React rendering/hydration errors, and unhandled promise rejections.
2. **RAG / LLM Pipeline Tracing**: Measure span latency and monitor execution failures across ChromaDB vector queries, BM25 indexing, CrossEncoder reranking, and OpenRouter / Anthropic LLM completions.
3. **Data Scrubbing & PHI/PII Protection**: Enforce strict sanitization before event transmission (stripping auth tokens, API keys, cookies, and scrubbing potential medical records/patient identifiers).
4. **Environment-Aware Graceful Fallback**: If `SENTRY_DSN` is unset (such as in offline local dev without credentials), Sentry remains inert without raising errors or blocking startup.
5. **Verification & Observability**: Provide dedicated test triggers (`/api/health/sentry-test` backend endpoint and dev client utilities) for automated and manual verification.

---

## 2. Architecture & Components

### 2.1 Backend Architecture (FastAPI + Python)
- **Dependency**: `sentry-sdk[fastapi]>=2.8.0` in `requirements.txt`.
- **Config**: Extended `backend/app/config.py` Settings model:
  - `sentry_dsn: str = ""`
  - `sentry_environment: str = "development"`
  - `sentry_traces_sample_rate: float = 1.0` (or 0.1 in production)
- **Initialization Module**: `backend/app/monitoring/sentry.py`:
  - Configures `sentry_sdk.init` with `FastApiIntegration`, `HttpxIntegration`, and `LoggingIntegration`.
  - Implements custom `before_send` hook for PHI/PII and secret sanitization.
- **RAG / LLM Instrumentation**:
  - Traced spans using `sentry_sdk.start_span(op="...", description="...")` inside:
    - `backend/app/retrieval/chroma.py` (ChromaDB vector queries)
    - `backend/app/retrieval/hybrid.py` (Hybrid BM25 + Vector fusion)
    - `backend/app/retrieval/reranker.py` (CrossEncoder reranker model)
    - `backend/app/generation/claude.py` (LLM generation calls)
- **Verification Endpoint**:
  - `GET /api/health/sentry-test` in `backend/app/api/search.py` (or a dedicated monitoring router) which captures an intentional test event/message or raises a handled test error when called with a diagnostic parameter.

### 2.2 Frontend Architecture (Next.js 15 + TypeScript)
- **Dependency**: `@sentry/nextjs` in `frontend/package.json`.
- **Config Files**:
  - `frontend/sentry.client.config.ts`: Client browser runtime configuration with `beforeSend` sanitization.
  - `frontend/sentry.server.config.ts`: Node.js server component / SSR runtime configuration.
  - `frontend/sentry.edge.config.ts`: Edge runtime configuration.
  - `frontend/next.config.ts`: Wrapped with `withSentryConfig` to enable bundle analysis, source maps, and error boundaries.
- **Client Test Utility**:
  - Exposes an error boundary test component or a dev-only trigger to verify client-side Sentry event generation.

---

## 3. Data Sanitization & PHI / HIPAA Compliance

Given the clinical context of Eva AI:
1. `send_default_pii = False` in both Python and Next.js Sentry initializations.
2. `before_send` filtering:
   - Header stripping: `Authorization`, `Cookie`, `X-Api-Key`, `Proxy-Authorization`.
   - Payload masking: Regex-based masking for emails, phone numbers, SSNs, and identifiable 10-digit medical record patterns in error strings and breadcrumbs.
   - Query sanitization: Truncate and mask raw user prompt payloads if an exception occurs during evaluation or generation.

---

## 4. Environment Variables Specification

| Variable Name | Type | Default | Description |
|---|---|---|---|
| `SENTRY_DSN` | `str` | `""` | Sentry Data Source Name for backend Python service. If empty, SDK is disabled. |
| `NEXT_PUBLIC_SENTRY_DSN` | `str` | `""` | Sentry DSN for frontend Next.js application. |
| `SENTRY_ENVIRONMENT` | `str` | `"development"` | Environment tag (`development`, `staging`, `production`). |
| `SENTRY_TRACES_SAMPLE_RATE` | `float` | `1.0` | Sample rate for performance transactions (1.0 = 100%, 0.1 = 10%). |

---

## 5. Verification & Testing Strategy

1. **Unit & Integration Tests**:
   - Test Sentry initialization with valid DSN (mocks `sentry_sdk.init`).
   - Test graceful fallback when DSN is empty (verifies no exceptions thrown).
   - Test `before_send` sanitization function with test fixtures containing Bearer tokens, cookies, emails, and sensitive patterns.
   - Test `/api/health/sentry-test` endpoint returns appropriate status and triggers `capture_exception` / `capture_message`.
2. **End-to-End Verification**:
   - Run backend test suite via `pytest`.
   - Verify frontend compiles/builds with `@sentry/nextjs` without TypeScript errors.
