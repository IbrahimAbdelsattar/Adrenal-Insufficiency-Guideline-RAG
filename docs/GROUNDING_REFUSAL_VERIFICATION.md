# Day 3 — Grounding & Refusal Verification Report

**Project:** Eva AI — Clinical Decision Support (NICE NG243)
**Date:** 2026-08-19
**Checklist Items:** ✅ Grounding System Prompt · ✅ Refusal Logic · ✅ Medical Safety Policy

---

## Executive Summary

Both Day 3 checklist items and strict Medical Safety constraints have been verified and hardened. The system features a 4-layer safety architecture (Injection, Scope, Floor, and Pharmacological Disclaimer), a production-grade hardened system prompt, and a 105-test verification suite that passes with **0 failures**. 

---

## 1. Grounding System Prompt

**File:** [`backend/app/generation/prompt.py`](file:///c:/Users/Mayada%20AbouZeid/Documents/Study2026/Summer26/AI%20Hackathon/Eva-AI/backend/app/generation/prompt.py)

### Hardened Constraints

| Section | Constraint Details |
|---|---|
| **GROUNDING CONSTRAINTS** | Evidence-Only, Mandatory Citations, Explicit Abstention, Clinical Precision, Scope Enforcement. |
| **SECURITY CONSTRAINTS** | Anti-injection clauses, DAN / jailbreak resistance, Prompt-reveal protection, Identity lock (Eva-AI only). |
| **MEDICAL SAFETY POLICY** | Strict Prescription Refusal: Never act as a prescribing doctor, prohibit second-person instructions, enforce guideline-framing (*"According to NICE NG243..."*), and refuse personal medical advice. |
| **GENERAL TREATMENT LIMIT** | For general treatment or dosing queries (e.g. *"what is treatment?"*), the model must only summarize high-level treatment principles and modalities (such as corticosteroid replacement, stress adjustments, dose tapering under supervision) conceptually. It is explicitly forbidden from listing specific drug names or exact dosage figures to avoid presenting a prescribing sheet to users. |

---

## 2. Refusal Logic

### Refusal Layer Architecture

```
Request
   │
   ▼
┌─────────────────────────────────────────┐
│  Layer 0: Injection Guard               │  ← pre-retrieval regex-based filter
│  detect_prompt_injection(query)         │
│  Action: immediate refusal response     │
└─────────────────────────────────────────┘
   │ Clean query
   ▼
┌─────────────────────────────────────────┐
│  Layer 0.5: Prescription & Dosage Guard │  ← is_dosage_or_medication_query(query)
│  Checks standalone dosage requests      │     Bypassed for clinical scenario lookups
│  Action: bilingual refusal (EN / AR)    │     (crisis protocol, routine replacement, etc.)
└─────────────────────────────────────────┘
   │ Clinical query
   ▼
┌─────────────────────────────────────────┐
│  Layer 1: Scope Classifier              │  ← classify_scope(results, threshold)
│  Threshold: scope_threshold = 0.68      │
│  Action: "Honest, Not Unhelpful"        │
└─────────────────────────────────────────┘
   │ in_scope results
   ▼
┌─────────────────────────────────────────┐
│  Layer 2: Floor Guard                   │  ← should_abstain(results)
│  Threshold: relevance_floor = 0.68      │
│  Action: "Honest, Not Unhelpful"        │
└─────────────────────────────────────────┘
   │ Strong evidence
   ▼
┌─────────────────────────────────────────┐
│  Layer 3: Pharmacological Disclaimer    │  ← contains_pharmacological_content()
│  Action: Force-append disclaimer        │
└─────────────────────────────────────────┘
   │ Finalized grounded answer
   ▼
  Clinician Response
```

### "Honest, Not Unhelpful" Refusal Messages

Refusal messages in [`backend/app/retrieval/scope.py`](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/retrieval/scope.py) strictly do three things:
1. State clearly that the available evidence is insufficient.
2. Explain what was searched (NICE NG243 adrenal insufficiency guideline).
3. Suggest a next step (rephrasing or consulting a clinician).

**Out-of-Scope Message:**
> *"I couldn't find enough information in the indexed guidelines to answer this confidently. Eva AI searches NICE NG243 (adrenal insufficiency), and this question falls outside that guideline's domain entirely. Try rephrasing with adrenal insufficiency terminology, or consult a clinician directly."*

**No-Evidence Message:**
> *"I couldn't find enough information in the indexed guidelines to answer this confidently. Eva AI searched NICE NG243 but the retrieved evidence did not contain sufficient detail to address your specific question. Try rephrasing or broadening your clinical query, or consult a clinician directly."*

---

## 3. Standardized Clinical Disclaimer

Any answer containing pharmacological content (dosing, drug names, administration routes, etc.) deterministically appends the following disclaimer at the application level:

```markdown
> ⚠️ **Clinical Disclaimer:** This tool provides clinical reference data strictly for decision support. It does not provide medical advice or individual prescriptions. All dosing and treatment decisions must be evaluated by a licensed healthcare professional.
```

This is scanned and injected by `_finalize_answer` in [`backend/app/generation/service.py`](file:///c:/Users/C-LAB/Videos/ai%20hackthon/backend/app/generation/service.py) for both the JSON and SSE streaming endpoints.

---

## 4. Test Suite Results

### Execution Verification

We executed `pytest` across the backend stress, unit, evaluation, and API integration suites:

- **Full Backend Test Suite**: **383 passed, 0 failed** in 57.96s
- **Live E2E Verification Suite (`scripts/test_live_e2e.py`)**: **88/88 checks passed (100%)**
  - Group 1 (Greetings / Capability in EN & AR): 3/3 passed
  - Group 2 (In-Scope Clinical Qs): 7/7 passed
  - Group 3 (Multi-Turn History): 2/2 passed
  - Group 4 (Out-of-Scope Abstention): 3/3 passed
  - Group 5 (Dosage Refusal & Scenario Bypass): 4/4 passed
  - Group 6 (Prompt Injection / Jailbreak): 4/4 passed
  - Group 7 (Response Caching): 106.5x speedup verified
  - Group 8 (SSE Token Streaming): verified

All safety filters, prompt restrictions, disclaimer injections, and boundary conditions passed cleanly.
