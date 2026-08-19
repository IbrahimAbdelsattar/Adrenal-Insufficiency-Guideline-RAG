# Eva AI - Chatbot Responsiveness and Conversation Context

## 1. Executive Summary

Eva AI now handles conversational capability questions as a first-class interaction. A question such as “How can you help me?” returns an immediate scope-aware introduction instead of being misclassified as an out-of-scope clinical query. Multi-turn chat history is also sent to both JSON and SSE generation endpoints so follow-up questions can use the active conversation context.

## 2. Architectural Changes & Key Components

- `backend/app/generation/guardrails.py`
  - Expands capability-intent matching to cover optional pronouns and normalizes whitespace before matching.
  - Preserves the clinical boundary: “Can you help me manage suspected adrenal crisis?” continues to retrieval and evidence validation.
- `frontend/lib/api.ts`
  - Adds typed `ChatHistoryMessage` payloads to JSON generation and streaming requests.
- `frontend/components/ChatView.tsx`
  - Sends prior non-empty user and assistant turns with each request.
  - Keeps SSE rendering live and renders assistant Markdown safely.
- `frontend/components/AnswerCard.tsx`
  - Renders headings, lists, emphasis, links, tables, code, and quotations instead of exposing Markdown punctuation.

## 3. Performance & Latency Benchmarks

Capability questions are handled before retrieval and LLM invocation. The targeted API regression verifies the immediate path for both JSON and SSE endpoints; no production latency benchmark was recorded in this change.

## 4. Safety, Guardrails & Error Tracking

- Capability routing does not broaden clinical scope or answer medical questions without evidence.
- Prompt-injection detection remains before retrieval and generation.
- Clinical questions that are not capability intents continue through relevance thresholds, abstention, citations, and the existing decision-support disclaimer.

## 5. Verification & Testing Evidence

| Check | Result |
| --- | --- |
| `python -m pytest backend/tests/unit/test_greeting_guardrail.py backend/tests/integration/test_generate_api.py -q` | **10 passed** |
| `npm run typecheck` in `frontend/` | **Passed** |
| Capability query through `/api/generate` and `/api/generate/stream` | **Verified; retrieval is bypassed** |
| `npm run build` in `frontend/` | Timed out after 180 seconds without a compiler error; workspace had many concurrent Node processes |
