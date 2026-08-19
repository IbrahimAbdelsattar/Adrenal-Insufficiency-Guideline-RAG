# Sentry Error & Bug Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate full-stack Sentry error tracking, performance tracing, and PHI-safe data scrubbing for FastAPI backend and Next.js frontend with deep RAG/LLM pipeline instrumentation.

**Architecture:** Initialize Sentry with graceful fallback if no DSN is provided, sanitize sensitive PHI/PII and auth headers in `before_send` hooks, instrument FastAPI middleware and RAG spans (Chroma, BM25, CrossEncoder, LLM generation), and configure Next.js Sentry SDK.

**Tech Stack:** Python 3.11+, FastAPI, `sentry-sdk[fastapi]>=2.8.0`, Next.js 15, `@sentry/nextjs`, TypeScript.

## Global Constraints
- Do not break existing tests or startup when `SENTRY_DSN` is empty or missing.
- Enforce strict PHI/PII masking (`send_default_pii=False` + regex sanitization of headers and payloads).
- Maintain compatibility with Next.js 15 App router and existing static export / proxy architecture.

---

### Task 1: Backend Dependencies and Configuration

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Consumes: `pydantic_settings.BaseSettings`
- Produces: `Settings.sentry_dsn`, `Settings.sentry_environment`, `Settings.sentry_traces_sample_rate`

- [ ] **Step 1: Write test for Sentry config settings**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add `sentry-sdk[fastapi]>=2.8.0` to requirements and update `backend/app/config.py`**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 2: Sentry Initialization and PHI Sanitization Module

**Files:**
- Create: `backend/app/monitoring/__init__.py`
- Create: `backend/app/monitoring/sentry.py`
- Test: `backend/tests/test_sentry_monitoring.py`

**Interfaces:**
- Consumes: `backend.app.config.Settings`
- Produces: `init_sentry(settings: Settings) -> bool`, `sanitize_sentry_event(event, hint) -> dict | None`, `is_sentry_enabled() -> bool`

- [ ] **Step 1: Write failing test for Sentry initialization and PHI/header sanitization**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Implement `backend/app/monitoring/sentry.py` with PHI scrubbing and graceful init**
- [ ] **Step 4: Run test to verify all sanitization and init tests pass**

---

### Task 3: FastAPI Lifecycle Integration & Test Verification Endpoint

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/search.py` (or create `backend/app/api/monitoring.py`)
- Test: `backend/tests/test_sentry_endpoint.py`

**Interfaces:**
- Consumes: `backend.app.monitoring.sentry.init_sentry`
- Produces: `GET /api/health/sentry-test` endpoint for integration diagnostics

- [ ] **Step 1: Write failing test for `/api/health/sentry-test` endpoint**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Integrate `init_sentry` in `backend/app/main.py` and register the test route**
- [ ] **Step 4: Run test to verify endpoint succeeds**

---

### Task 4: RAG & LLM Pipeline Tracing Instrumentation

**Files:**
- Modify: `backend/app/retrieval/chroma.py`
- Modify: `backend/app/retrieval/hybrid.py`
- Modify: `backend/app/retrieval/reranker.py`
- Modify: `backend/app/generation/claude.py`
- Test: `backend/tests/test_sentry_spans.py`

**Interfaces:**
- Consumes: `backend.app.monitoring.sentry.trace_span` or `sentry_sdk.start_span`
- Produces: Custom span metrics for `rag.chroma.query`, `rag.bm25.search`, `rag.rerank`, `llm.generate`

- [ ] **Step 1: Write test verifying custom span wrappers are executed during retrieval and generation**
- [ ] **Step 2: Run test to verify failure**
- [ ] **Step 3: Add span tracing across retrieval and generation pipelines**
- [ ] **Step 4: Run test to verify spans are safely created without side effects**

---

### Task 5: Frontend Next.js Sentry Setup

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/sentry.client.config.ts`
- Create: `frontend/sentry.server.config.ts`
- Create: `frontend/sentry.edge.config.ts`
- Modify: `frontend/next.config.ts`
- Create: `frontend/components/SentryTestButton.tsx`

**Interfaces:**
- Consumes: `NEXT_PUBLIC_SENTRY_DSN`
- Produces: Client & Server Sentry configuration and dev test trigger component

- [ ] **Step 1: Add `@sentry/nextjs` to `frontend/package.json` and install dependencies**
- [ ] **Step 2: Create Sentry client, server, and edge config files with PHI sanitization**
- [ ] **Step 3: Update `frontend/next.config.ts` with `withSentryConfig`**
- [ ] **Step 4: Create `frontend/components/SentryTestButton.tsx`**

---

### Task 6: Comprehensive Verification & Audit

**Files:**
- Test: Full pytest suite
- Test: Frontend build & typecheck

- [ ] **Step 1: Run complete backend pytest suite**
- [ ] **Step 2: Run frontend typecheck/lint**
- [ ] **Step 3: Produce Walkthrough documentation**
