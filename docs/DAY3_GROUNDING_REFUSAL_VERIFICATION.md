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
┌─────────────────────────────────────┐
│  Layer 0: Injection Guard           │  ← pre-retrieval regex-based filter
│  detect_prompt_injection(query)     │
│  Action: immediate refusal response │
└─────────────────────────────────────┘
   │ Clean query
   ▼
┌─────────────────────────────────────┐
│  Layer 1: Scope Classifier          │  ← classify_scope(results, threshold)
│  Threshold: scope_threshold = 0.005 │
│  Action: "Honest, Not Unhelpful"    │
└─────────────────────────────────────┘
   │ in_scope results
   ▼
┌─────────────────────────────────────┐
│  Layer 2: Floor Guard               │  ← should_abstain(results)
│  Threshold: relevance_floor = 0.30  │
│  Action: "Honest, Not Unhelpful"    │
└─────────────────────────────────────┘
   │ Strong evidence
   ▼
┌─────────────────────────────────────┐
│  Layer 3: Pharmacological Disclaimer │  ← contains_pharmacological_content()
│  Action: Force-append disclaimer   │
└─────────────────────────────────────┘
   │ Finalized grounded answer
   ▼
 Gp / Clinician Response
```

### "Honest, Not Unhelpful" Refusal Messages

Refusal messages in [`scope.py`](file:///c:/Users/Mayada%20AbouZeid/Documents/Study2026/Summer26/AI%20Hackathon/Eva-AI/backend/app/retrieval/scope.py) strictly do three things:
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

This is scanned and injected by `_finalize_answer` in [`service.py`](file:///c:/Users/Mayada%20AbouZeid/Documents/Study2026/Summer26/AI%20Hackathon/Eva-AI/backend/app/generation/service.py) for both the JSON and SSE streaming endpoints.

---

## 4. Test Suite Results

### Execution Verification

We executed `pytest` across the backend stress, unit, and API integration suites.

- **`test_grounding_stress.py`**: **98/98 PASS**
- **`test_sectioner.py`**: **13/13 PASS**
- **`test_generate_api.py`**: **7/7 PASS**

All safety filters, prompt restrictions, disclaimer injections, and boundary conditions passed cleanly.
